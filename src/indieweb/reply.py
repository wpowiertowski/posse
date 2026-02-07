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


def build_reply_record(data: Dict[str, Any], client_ip: str) -> Dict[str, Any]:
    """Build a reply record ready for storage.

    Args:
        data: Validated form data.
        client_ip: Client IP address (will be hashed).

    Returns:
        Reply dict with id, author_name, author_url, content, target,
        ip_hash, and created_at fields.
    """
    return {
        "id": generate_reply_id(),
        "author_name": sanitize_text(data.get("author_name", ""), MAX_AUTHOR_NAME_LENGTH),
        "author_url": validate_url(data.get("author_url", "")) or "",
        "content": sanitize_text(data.get("content", ""), MAX_CONTENT_LENGTH),
        "target": data["target"].strip(),
        "ip_hash": hash_ip(client_ip),
        "created_at": datetime.utcnow().isoformat() + "Z",
    }


def render_reply_hentry(reply: Dict[str, Any], blog_name: str = "Blog") -> str:
    """Render a reply as an h-entry HTML page.

    The generated page contains microformats2 markup (h-entry, h-card,
    u-in-reply-to) that webmention.io can parse to extract the reply.

    Args:
        reply: Reply record from storage.
        blog_name: Display name for the blog.

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
        author_link = f'<a class="p-name u-url" href="{escaped_url}" rel="nofollow noopener">{escaped_name}</a>'
    else:
        author_link = f'<span class="p-name">{escaped_name}</span>'

    created = reply["created_at"]
    try:
        dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
        display_date = dt.strftime("%B %d, %Y")
    except Exception:
        display_date = created

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Reply by {escaped_name}</title>
  <meta name="robots" content="noindex, nofollow">
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, sans-serif; max-width: 600px; margin: 2rem auto; padding: 0 1rem; background: #1a1a2e; color: #e0e0e0; }}
    .h-entry {{ background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.1); border-radius: 8px; padding: 1.5rem; }}
    .p-author {{ font-weight: 600; margin-bottom: 0.5rem; }}
    .p-author a {{ color: #7c7cff; text-decoration: none; }}
    .e-content {{ line-height: 1.6; margin: 1rem 0; white-space: pre-wrap; }}
    .meta {{ font-size: 0.8rem; color: #888; }}
    .meta a {{ color: #7c7cff; text-decoration: none; }}
    .u-in-reply-to {{ word-break: break-all; }}
  </style>
</head>
<body>
  <article class="h-entry">
    <div class="p-author h-card">
      {author_link}
    </div>
    <div class="e-content p-name">{escaped_content}</div>
    <div class="meta">
      <time class="dt-published" datetime="{created}">{display_date}</time>
      &middot; In reply to <a class="u-in-reply-to" href="{escaped_target}">{escaped_target}</a>
    </div>
  </article>
  <p style="margin-top:1rem;font-size:0.8rem;color:#666;">
    This reply was submitted via the webmention reply form on {escaped_blog}.
  </p>
</body>
</html>"""
