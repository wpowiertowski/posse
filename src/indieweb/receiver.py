"""
Webmention receiver: async verification of incoming webmentions.

When a webmention is received (POST /webmention with source + target),
it is stored as pending and verified asynchronously. Verification fetches
the source URL, confirms it links to the target, and extracts metadata
(author, content, mention type) from microformats2 markup.

References:
    - W3C Webmention: https://www.w3.org/TR/webmention/
    - Microformats2: https://microformats.org/wiki/microformats2
"""

import logging
from datetime import datetime, timezone
from html.parser import HTMLParser
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qsl, urljoin, urlparse

import mf2py

from indieweb.content_sanitizer import sanitize_content_html, sanitize_content_text
from indieweb.webmention import (
    _build_session,
    _checked_get,
    _is_private_or_loopback,
    _read_bounded_response,
    MAX_DISCOVERY_RESPONSE_BYTES,
)

logger = logging.getLogger(__name__)

# Maximum lengths for stored fields to prevent database bloat
_MAX_NAME_LENGTH = 200
_MAX_URL_LENGTH = 2048
_MAX_CONTENT_LENGTH = 10_000


def verify_webmention(source_url: str, target_url: str, store: Any, timeout: float = 30.0) -> Optional[Dict[str, Any]]:
    """Fetch the source URL, verify it links to the target, and extract metadata.

    Updates the webmention record in storage with verification results.
    If the source returns 404 or 410, the webmention is deleted from storage.

    Returns the verified metadata dict (including 'status' and 'mention_type') on
    successful verification, or None for rejections, deletions, and fetch errors.

    Args:
        source_url: The URL that allegedly mentions the target.
        target_url: The target URL being mentioned.
        store: InteractionDataStore instance.
        timeout: HTTP request timeout in seconds.
    """
    # SSRF protection
    if _is_private_or_loopback(source_url):
        logger.warning(f"Webmention verification blocked: private/loopback source {source_url}")
        store.update_webmention_verification(
            source=source_url, target=target_url, status="rejected",
            verified_at=datetime.now(timezone.utc).isoformat(),
        )
        return

    session = _build_session()
    try:
        # _checked_get re-validates every redirect hop against the SSRF guard, so
        # an attacker-controlled redirect can't steer the fetch to an internal
        # address after the initial source_url passed the check above.
        response = _checked_get(
            session,
            source_url,
            headers={"Accept": "text/html"},
            timeout=timeout,
            stream=True,
        )
    except Exception as e:
        logger.error(f"Webmention verification fetch failed: source={source_url}, error={e}")
        store.update_webmention_verification(
            source=source_url, target=target_url, status="rejected",
            verified_at=datetime.now(timezone.utc).isoformat(),
        )
        return

    # Source gone or not found: remove the webmention
    if response.status_code in (404, 410):
        logger.info(f"Source returned {response.status_code}, deleting webmention: {source_url}")
        response.close()
        store.delete_received_webmention(source_url, target_url)
        return

    if not response.ok:
        logger.warning(f"Source returned {response.status_code}: {source_url}")
        response.close()
        store.update_webmention_verification(
            source=source_url, target=target_url, status="rejected",
            verified_at=datetime.now(timezone.utc).isoformat(),
        )
        return

    # Read body with size limit
    body = _read_bounded_response(response, MAX_DISCOVERY_RESPONSE_BYTES)

    encoding = response.encoding or "utf-8"
    try:
        html_body = body.decode(encoding, errors="replace")
    except (LookupError, UnicodeDecodeError):
        html_body = body.decode("utf-8", errors="replace")

    # Verify source actually links to target
    if not _source_links_to_target(html_body, target_url, base_url=source_url):
        logger.info(f"Source does not link to target: source={source_url}, target={target_url}")
        store.update_webmention_verification(
            source=source_url, target=target_url, status="rejected",
            verified_at=datetime.now(timezone.utc).isoformat(),
        )
        return

    # Parse microformats2 and extract metadata
    metadata = _extract_hentry_metadata(html_body, source_url, target_url)

    now = datetime.now(timezone.utc).isoformat()
    store.update_webmention_verification(
        source=source_url,
        target=target_url,
        status="verified",
        mention_type=metadata.get("mention_type", "mention"),
        author_name=metadata.get("author_name", "")[:_MAX_NAME_LENGTH],
        author_url=metadata.get("author_url", "")[:_MAX_URL_LENGTH],
        author_photo=metadata.get("author_photo", "")[:_MAX_URL_LENGTH],
        content_html=metadata.get("content_html", "")[:_MAX_CONTENT_LENGTH],
        content_text=metadata.get("content_text", "")[:_MAX_CONTENT_LENGTH],
        verified_at=now,
    )
    logger.info(
        f"Webmention verified: source={source_url}, target={target_url}, "
        f"type={metadata.get('mention_type', 'mention')}"
    )
    return {"status": "verified", **metadata}


class _LinkHrefExtractor(HTMLParser):
    """Collect href values from real <a>/<link> elements.

    Using an HTML parser (rather than a regex over the raw markup) means hrefs
    that appear only inside comments, <script>, or <template> blocks are not
    treated as links to the target — those don't constitute a visible mention.
    """

    def __init__(self) -> None:
        super().__init__()
        self.hrefs: List[str] = []

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        if tag in ("a", "link"):
            for name, value in attrs:
                if name == "href" and value:
                    self.hrefs.append(value)


def _normalize_for_link_match(url: str) -> Optional[Tuple[str, str, tuple]]:
    """Normalize a URL into a comparison key, or None if it can't be parsed.

    Ignores differences that shouldn't defeat verification: the scheme
    (http vs https), a trailing slash, the fragment, and a ``ref`` query
    parameter (POSSE appends ``?ref=<platform>`` to its own syndicated links).
    """
    try:
        parsed = urlparse(url)
    except ValueError:
        return None
    netloc = parsed.netloc.lower()
    if not netloc:
        return None
    path = parsed.path.rstrip("/") or "/"
    query = tuple(sorted(
        (k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True) if k != "ref"
    ))
    return (netloc, path, query)


def _source_links_to_target(html_body: str, target_url: str, base_url: str = "") -> bool:
    """Check whether the HTML body contains a visible link to the target URL."""
    target_key = _normalize_for_link_match(target_url)
    if target_key is None:
        return False

    parser = _LinkHrefExtractor()
    try:
        parser.feed(html_body)
    except Exception as e:
        logger.debug(f"HTML parse failed while verifying link to target: {e}")
        return False

    for href in parser.hrefs:
        # Resolve relative hrefs against the source page when we know its URL.
        resolved = urljoin(base_url, href) if base_url else href
        if _normalize_for_link_match(resolved) == target_key:
            return True
    return False


def _extract_hentry_metadata(
    html_body: str, source_url: str, target_url: str
) -> Dict[str, str]:
    """Extract metadata from microformats2 h-entry in the source HTML.

    Returns a dict with keys: mention_type, author_name, author_url,
    author_photo, content_html, content_text.
    """
    result: Dict[str, str] = {
        "mention_type": "mention",
        "author_name": "",
        "author_url": "",
        "author_photo": "",
        "content_html": "",
        "content_text": "",
    }

    try:
        parsed = mf2py.parse(html_body, url=source_url)
    except Exception as e:
        logger.debug(f"Microformats parsing failed for {source_url}: {e}")
        return result

    # Find the first h-entry
    hentry = _find_first_hentry(parsed.get("items", []))
    if not hentry:
        return result

    properties = hentry.get("properties", {})

    # Extract author
    authors = properties.get("author", [])
    if authors:
        author = authors[0]
        if isinstance(author, dict):
            author_props = author.get("properties", {})
            result["author_name"] = _first_str(author_props.get("name", []))
            result["author_url"] = _first_str(author_props.get("url", []))
            result["author_photo"] = _first_str(author_props.get("photo", []))
        elif isinstance(author, str):
            result["author_name"] = author

    # Extract content. The HTML is sanitized to an allowlist of safe
    # formatting tags before storage so that consumers of the API don't
    # have to trust arbitrary remote markup, and so that mf2py's
    # occasional over-extraction (e.g. JSON-LD from <script>) doesn't
    # leak into rendered replies.
    content_list = properties.get("content", [])
    if content_list:
        content = content_list[0]
        if isinstance(content, dict):
            result["content_html"] = sanitize_content_html(content.get("html", ""))
            result["content_text"] = sanitize_content_text(content.get("value", ""))
        elif isinstance(content, str):
            result["content_text"] = sanitize_content_text(content)

    # Determine mention type from properties
    target_normalized = target_url.rstrip("/")
    result["mention_type"] = _determine_mention_type(properties, target_normalized)

    return result


def _find_first_hentry(items: list) -> Optional[Dict[str, Any]]:
    """Recursively find the first h-entry in parsed microformats items."""
    for item in items:
        types = item.get("type", [])
        if "h-entry" in types:
            return item
        # Check children
        children = item.get("children", [])
        found = _find_first_hentry(children)
        if found:
            return found
    return None


def _determine_mention_type(properties: Dict[str, Any], target_normalized: str) -> str:
    """Determine the webmention type based on h-entry properties."""
    # Check in-reply-to
    for url in properties.get("in-reply-to", []):
        if _url_matches_target(url, target_normalized):
            return "reply"

    # Check like-of
    for url in properties.get("like-of", []):
        if _url_matches_target(url, target_normalized):
            return "like"

    # Check repost-of
    for url in properties.get("repost-of", []):
        if _url_matches_target(url, target_normalized):
            return "repost"

    # Check bookmark-of
    for url in properties.get("bookmark-of", []):
        if _url_matches_target(url, target_normalized):
            return "bookmark"

    return "mention"


def _url_matches_target(url_or_obj: Any, target_normalized: str) -> bool:
    """Check if a URL (string or h-cite dict) matches the target."""
    if isinstance(url_or_obj, str):
        return url_or_obj.rstrip("/") == target_normalized
    if isinstance(url_or_obj, dict):
        props = url_or_obj.get("properties", {})
        urls = props.get("url", [])
        return any(u.rstrip("/") == target_normalized for u in urls if isinstance(u, str))
    return False


def _first_str(values: list) -> str:
    """Return the first string value from a list, or empty string."""
    for v in values:
        if isinstance(v, str):
            return v
    return ""
