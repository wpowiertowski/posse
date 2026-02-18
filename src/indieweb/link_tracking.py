"""
Webmention link tracking and re-sending for post updates and deletes.

Extracts outbound links from Ghost post HTML, diffs against previously
sent webmentions, and re-sends as needed per W3C Webmention spec:
- On update: re-send to all current links + previously-linked (removed) URLs
- On delete: re-send to all previously-notified URLs

References:
    - W3C Webmention: https://www.w3.org/TR/webmention/ (Section 4: Sending)
"""

import logging
import re
from html.parser import HTMLParser
from typing import List, Optional, Set
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# Maximum HTML size to parse for link extraction (5 MB).
# Ghost posts are typically much smaller, but this guards against
# pathological inputs without being too restrictive.
MAX_HTML_PARSE_BYTES = 5_242_880


class LinkExtractor(HTMLParser):
    """HTML parser that extracts href URLs from <a> tags."""

    def __init__(self):
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag == "a":
            attrs_dict = dict(attrs)
            href = attrs_dict.get("href")
            if href:
                self.links.append(href)


def extract_outbound_links(html_content: str, source_origin: str) -> Set[str]:
    """Extract unique external HTTP(S) links from HTML content.

    Filters out:
    - Links to the same origin as the source (self-references)
    - Non-HTTP(S) links (mailto:, javascript:, etc.)
    - Fragment-only links (#section)
    - Empty hrefs

    Args:
        html_content: The HTML body of the post.
        source_origin: The origin (scheme://host) of the post itself,
                       used to filter out self-links.

    Returns:
        Set of unique absolute external URLs.
    """
    if not html_content:
        return set()

    # Guard against pathologically large HTML content
    if len(html_content) > MAX_HTML_PARSE_BYTES:
        logger.warning(
            f"HTML content too large for link extraction ({len(html_content)} bytes), "
            f"truncating to {MAX_HTML_PARSE_BYTES} bytes"
        )
        html_content = html_content[:MAX_HTML_PARSE_BYTES]

    parser = LinkExtractor()
    try:
        parser.feed(html_content)
    except Exception as e:
        logger.warning(f"Failed to parse HTML for link extraction: {e}")
        return set()

    source_origin_lower = source_origin.lower().rstrip("/")
    links = set()

    for href in parser.links:
        href = href.strip()
        if not href or href.startswith("#"):
            continue

        try:
            parsed = urlparse(href)
        except Exception:
            continue

        if parsed.scheme not in ("http", "https"):
            continue

        if not parsed.netloc:
            continue

        link_origin = f"{parsed.scheme}://{parsed.netloc}".lower().rstrip("/")
        if link_origin == source_origin_lower:
            continue

        # Normalize: strip fragment, keep query params
        normalized = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
        if parsed.query:
            normalized += f"?{parsed.query}"

        links.add(normalized)

    return links


def compute_webmention_diff(
    current_links: Set[str],
    previously_sent: Set[str],
) -> tuple[Set[str], Set[str]]:
    """Compute which URLs need webmentions sent on a post update.

    Per the W3C spec, when content changes:
    - All current links should receive a webmention (update notification)
    - URLs that were previously linked but are now removed should also
      receive a webmention (so receivers can detect the link was removed)

    Args:
        current_links: Links extracted from the current version of the post.
        previously_sent: Target URLs from previously sent webmentions.

    Returns:
        Tuple of (targets_to_send, removed_targets):
        - targets_to_send: all URLs that should receive a webmention
        - removed_targets: subset that were removed (for logging purposes)
    """
    removed = previously_sent - current_links
    targets_to_send = current_links | removed
    return targets_to_send, removed
