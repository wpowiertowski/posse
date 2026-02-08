"""
Webmention reply handling.

Provides validation, storage, rendering, and sending of webmention replies
submitted through the reply form. Replies are stored in SQLite and served
as h-entry pages so that webmention.io can verify them.

Usage:
    >>> from indieweb.reply import validate_reply, store_and_send_reply
    >>> errors = validate_reply(data, allowed_origins=["https://blog.example.com"])
    >>> if not errors:
    ...     reply_id = store_and_send_reply(data, store, origin_url)
"""

import hashlib
import html
import logging
import os
import secrets
import string
from datetime import datetime
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import requests

from indieweb.webmention import send_webmention, WebmentionResult


logger = logging.getLogger(__name__)

# Reply ID: 16 URL-safe characters
_ID_ALPHABET = string.ascii_letters + string.digits
_ID_LENGTH = 16

# Validation limits
MAX_AUTHOR_NAME_LENGTH = 100
MAX_AUTHOR_URL_LENGTH = 500
MAX_CONTENT_LENGTH = 2000
MIN_CONTENT_LENGTH = 2

# Rate limiting for replies: separate from the general request rate limit
REPLY_RATE_LIMIT = 5
REPLY_RATE_WINDOW_SECONDS = 3600  # 1 hour

# Turnstile verification URL
TURNSTILE_VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"


def generate_reply_id() -> str:
    """Generate a random reply ID."""
    return "".join(secrets.choice(_ID_ALPHABET) for _ in range(_ID_LENGTH))


def hash_ip(ip: str) -> str:
    """Hash an IP address for storage (privacy-preserving)."""
    salted = f"{ip}:webmention-reply-salt".encode()
    return hashlib.sha256(salted).hexdigest()[:16]


def sanitize_text(text: str, max_length: int) -> str:
    """Strip and truncate text. Does NOT escape HTML (that's for rendering)."""
    return text.strip()[:max_length]


def validate_url(url_str: str) -> Optional[str]:
    """Validate and normalize a URL. Returns the URL or None if invalid."""
    url_str = url_str.strip()[:MAX_AUTHOR_URL_LENGTH]
    if not url_str:
        return None
    try:
        parsed = urlparse(url_str)
        if parsed.scheme not in ("http", "https"):
            return None
        if not parsed.netloc:
            return None
        return parsed.geturl()
    except Exception:
        return None


def validate_reply(
    data: Dict[str, Any],
    allowed_origins: List[str],
) -> List[str]:
    """Validate a reply submission.

    Args:
        data: The submitted form data.
        allowed_origins: List of allowed target URL origins.

    Returns:
        List of error messages. Empty list means valid.
    """
    errors = []

    # Honeypot check - return empty errors to silently accept
    # (caller handles this specially)
    if data.get("website"):
        return []

    author_name = (data.get("author_name") or "").strip()
    if not author_name:
        errors.append("Name is required.")
    elif len(author_name) > MAX_AUTHOR_NAME_LENGTH:
        errors.append(f"Name must be {MAX_AUTHOR_NAME_LENGTH} characters or less.")

    content = (data.get("content") or "").strip()
    if not content:
        errors.append("Reply content is required.")
    elif len(content) < MIN_CONTENT_LENGTH:
        errors.append("Reply is too short.")
    elif len(content) > MAX_CONTENT_LENGTH:
        errors.append(f"Reply must be {MAX_CONTENT_LENGTH} characters or less.")

    target = (data.get("target") or "").strip()
    if not target:
        errors.append("Target URL is required.")
    else:
        try:
            parsed = urlparse(target)
            origin = f"{parsed.scheme}://{parsed.netloc}"
            if origin not in allowed_origins:
                errors.append("Target URL is not from an allowed site.")
        except Exception:
            errors.append("Invalid target URL.")

    author_url = (data.get("author_url") or "").strip()
    if author_url:
        if validate_url(author_url) is None:
            errors.append("Invalid website URL.")

    return errors


def is_honeypot_filled(data: Dict[str, Any]) -> bool:
    """Check if the honeypot field was filled (indicates bot)."""
    return bool(data.get("website"))


def verify_turnstile(token: str, client_ip: str, secret_key: str) -> bool:
    """Verify a Cloudflare Turnstile CAPTCHA token.

    Args:
        token: The cf-turnstile-response token from the form.
        client_ip: The client's IP address.
        secret_key: The Turnstile secret key.

    Returns:
        True if verification succeeded.
    """
    try:
        response = requests.post(
            TURNSTILE_VERIFY_URL,
            json={
                "secret": secret_key,
                "response": token,
                "remoteip": client_ip,
            },
            timeout=10,
        )
        data = response.json()
        return data.get("success") is True
    except Exception as e:
        logger.error(f"Turnstile verification failed: {e}")
        return False


def build_reply_record(data: Dict[str, Any], client_ip: str, timezone_name: str = "UTC") -> Dict[str, Any]:
    """Build a reply record ready for storage.

    Args:
        data: Validated form data.
        client_ip: Client IP address (will be hashed).

    Returns:
        Reply dict with id, author_name, author_url, content, target,
        ip_hash, and created_at fields.
    """
    if not isinstance(timezone_name, str) or not timezone_name.strip():
        timezone_name = "UTC"
    else:
        timezone_name = timezone_name.strip()
    try:
        tzinfo = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        logger.warning(f"Unknown timezone '{timezone_name}' for webmention replies, falling back to UTC")
        tzinfo = ZoneInfo("UTC")

    return {
        "id": generate_reply_id(),
        "author_name": sanitize_text(data.get("author_name", ""), MAX_AUTHOR_NAME_LENGTH),
        "author_url": validate_url(data.get("author_url", "")) or "",
        "content": sanitize_text(data.get("content", ""), MAX_CONTENT_LENGTH),
        "target": data["target"].strip(),
        "ip_hash": hash_ip(client_ip),
        "created_at": datetime.now(tzinfo).isoformat(),
    }


def render_reply_hentry(
    reply: Dict[str, Any],
    blog_name: str = "Blog",
    *,
    css_link: str = "",
    fonts_style: str = "",
    shared_style: str = "",
) -> str:
    """Render a stored reply as an h-entry page.

    The output keeps the same microformats2 data while matching the visual
    shell used by the /webmention page.

    Args:
        reply: Reply record from storage.
        blog_name: Display name for the blog.
        css_link: Optional stylesheet link tag injected by the Flask route.
        fonts_style: Optional @font-face style tag injected by the Flask route.
        shared_style: Optional shared style block copied from src/static/reply.html.

    Returns:
        Complete HTML page as a string.
    """
    escaped_name = html.escape(reply["author_name"])
    escaped_content = html.escape(reply["content"])
    escaped_target = html.escape(reply["target"])
    escaped_blog = html.escape(blog_name)

    author_url = reply.get("author_url", "")
    if author_url:
        escaped_url = html.escape(author_url)
        author_link = (
            f'<a class="p-name u-url" href="{escaped_url}" rel="nofollow noopener">{escaped_name}</a>'
        )
    else:
        author_link = f'<span class="p-name">{escaped_name}</span>'

    created = reply["created_at"]
    try:
        dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
        display_date = dt.strftime("%B %d, %Y")
    except Exception:
        display_date = created

    if not shared_style:
        shared_style = """<style>
        :root {
            --color-white: #fff;
            --color-gray-100: #f4f4f5;
            --color-gray-200: #e4e4e7;
            --color-gray-400: #a1a1aa;
            --color-gray-600: #52525b;
            --color-gray-800: #27272a;
            --color-gray-900: #18181b;
            --color-bg: var(--color-gray-900);
            --color-bg-muted: var(--color-gray-800);
            --color-text: #e4e4e7;
            --color-text-muted: var(--color-gray-400);
            --color-text-highlight: var(--color-white);
            --color-border: var(--color-gray-800);
            --color-primary: #7c7cff;
            --font-primary: 'Montserrat', 'Helvetica Neue', Helvetica, Arial, sans-serif;
        }
        html { font-family: var(--font-primary); font-size: 100%; }
        body {
            background: var(--color-bg);
            color: var(--color-text);
            min-height: 100vh;
            line-height: 1.5;
            margin: 0;
        }
        .reply-main { padding: 3rem 1rem; }
        .container { width: 100%; max-width: 760px; margin: 0 auto; }
        .reply-card {
            border: 1px solid var(--color-border);
            border-radius: 8px;
            padding: 1.5rem;
            background: var(--color-bg);
        }
        h1 {
            font-size: 1.125rem;
            margin: 0 0 1.25rem 0;
            color: var(--color-text-highlight);
            letter-spacing: 0.05em;
            text-transform: uppercase;
            font-weight: 700;
        }
        .subtitle {
            color: var(--color-text);
            font-size: 0.875rem;
            margin: 0 0 1.5rem 0;
            line-height: 1.5;
        }
        .target-info {
            background: var(--color-bg);
            border: 1px solid var(--color-border);
            border-radius: 8px;
            padding: 0.75rem 1rem;
        }
        label {
            display: block;
            margin-bottom: 0.5rem;
            font-size: 0.75rem;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            color: var(--color-text-muted);
        }
        .info-section {
            margin-top: 1.5rem;
            border-top: 1px solid var(--color-border);
            padding-top: 1rem;
            color: var(--color-text-muted);
            font-size: 0.8125rem;
        }
        </style>"""

    return f"""<!DOCTYPE html>
<html lang="en" class="dark-mode">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Reply by {escaped_name}</title>
  <meta name="robots" content="noindex, nofollow">
  {css_link}
  {fonts_style}
  {shared_style}
  <style>
    .reply-view {{ display: flex; flex-direction: column; gap: 1rem; }}
    .reply-view .target-info {{ margin-bottom: 0; }}
    .reply-view .p-author {{
        color: var(--color-text-highlight, #fff);
        font-weight: 600;
        line-height: 1.4;
    }}
    .reply-view .p-author a {{
        color: var(--color-primary, #7c7cff);
        text-decoration: none;
    }}
    .reply-view .p-author a:hover {{ text-decoration: underline; }}
    .reply-view .e-content {{
        color: var(--color-text-highlight, #fff);
        line-height: 1.6;
        white-space: pre-wrap;
    }}
    .reply-target-link {{
        display: block;
        color: var(--color-primary, #7c7cff);
        text-decoration: none;
        word-break: break-word;
    }}
    .reply-target-link:hover {{ text-decoration: underline; }}
    .reply-meta {{
        margin-top: 0.5rem;
        padding-top: 0.75rem;
        border-top: 1px solid var(--color-border, rgba(255,255,255,0.1));
    }}
    .reply-meta .dt-published {{ color: var(--color-text-muted, #a1a1aa); }}
  </style>
</head>
<body class="post-template">
  <main id="main" class="content outer reply-main">
    <div class="container">
      <article class="reply-card post-content h-entry">
        <h1>Webmention Reply</h1>
        <p class="subtitle">This published reply was sent via the webmention form on {escaped_blog}.</p>
        <div class="reply-view">
          <div class="target-info">
            <label>Author</label>
            <div class="p-author h-card">{author_link}</div>
          </div>
          <div class="target-info">
            <label>Reply</label>
            <div class="e-content p-name">{escaped_content}</div>
          </div>
          <div class="target-info">
            <label>In reply to</label>
            <a class="u-in-reply-to reply-target-link" href="{escaped_target}">{escaped_target}</a>
          </div>
        </div>
        <div class="info-section reply-meta">
          <time class="dt-published" datetime="{created}">{display_date}</time>
        </div>
      </article>
    </div>
  </main>
</body>
</html>"""
