"""
Webmention Receiver Endpoint.

Implements a W3C Webmention receiving endpoint that accepts incoming
webmentions (replies, likes, mentions) for Ghost blog posts.

The endpoint only accepts webmentions where the target URL belongs to
the configured Ghost blog, restricting mentions to replies to actual
Ghost posts.

W3C Webmention Spec: https://www.w3.org/TR/webmention/

Receiving flow:
    1. Receive POST with source and target parameters
    2. Validate that target is a Ghost post URL
    3. Verify that source links to target
    4. Store the webmention for later retrieval

Widget integration:
    The Ghost theme interactions widget can submit webmentions by POSTing
    to /webmention with source (user's URL) and target (current post URL).
    The endpoint supports both application/x-www-form-urlencoded and
    application/json content types. CORS is handled by Flask-CORS globally.

    The widget should auto-fill the target parameter with the current
    Ghost post's canonical URL (window.location.href or a data attribute).

Usage:
    The receiver is registered as a Flask route in ghost.py via
    register_webmention_routes(app, config).
"""

import logging
import re
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import requests

logger = logging.getLogger(__name__)

# Validation constants
MAX_URL_LENGTH = 2048
SOURCE_FETCH_TIMEOUT = 10
# User agent for source verification requests
USER_AGENT = "POSSE Webmention Receiver (https://github.com/wpowiertowski/posse)"


@dataclass
class ReceivedWebmention:
    """A received webmention entry.

    Attributes:
        source: The URL of the page that mentions the target
        target: The Ghost post URL being mentioned
        verified: Whether the source has been verified to link to the target
        verification_error: Error message if verification failed
        received_at: Unix timestamp when the webmention was received
    """
    source: str
    target: str
    verified: bool = False
    verification_error: Optional[str] = None
    received_at: float = field(default_factory=time.time)


class WebmentionStore:
    """In-memory store for received webmentions.

    Stores webmentions keyed by target URL. Thread-safe for reads/writes
    from Flask request handlers (single-process, GIL-protected).
    """

    def __init__(self):
        # {target_url: [ReceivedWebmention, ...]}
        self._mentions: Dict[str, List[ReceivedWebmention]] = {}

    def add(self, mention: ReceivedWebmention) -> None:
        """Add a webmention, replacing any existing one with the same source+target."""
        target = mention.target
        if target not in self._mentions:
            self._mentions[target] = []

        # Replace existing mention from same source (update semantics per spec)
        self._mentions[target] = [
            m for m in self._mentions[target] if m.source != mention.source
        ]
        self._mentions[target].append(mention)
        logger.debug(f"Stored webmention: source={mention.source} target={mention.target}")

    def get_for_target(self, target_url: str) -> List[ReceivedWebmention]:
        """Get all webmentions for a target URL."""
        return list(self._mentions.get(target_url, []))

    def get_all(self) -> Dict[str, List[ReceivedWebmention]]:
        """Get all stored webmentions."""
        return {k: list(v) for k, v in self._mentions.items()}

    def count(self) -> int:
        """Total number of stored webmentions."""
        return sum(len(v) for v in self._mentions.values())


def _is_valid_url(url: str) -> bool:
    """Check if a string is a valid HTTP(S) URL.

    Args:
        url: The URL string to validate

    Returns:
        True if valid HTTP or HTTPS URL, False otherwise
    """
    if not url or len(url) > MAX_URL_LENGTH:
        return False
    try:
        parsed = urlparse(url)
        return parsed.scheme in ("http", "https") and bool(parsed.netloc)
    except Exception:
        return False


def _is_ghost_post_url(url: str, blog_url: str) -> bool:
    """Check if a URL belongs to the configured Ghost blog.

    Validates that the target URL starts with the blog's base URL,
    ensuring webmentions are only accepted for actual blog posts.

    Args:
        url: The target URL to check
        blog_url: The Ghost blog base URL (e.g., "https://blog.example.com")

    Returns:
        True if the URL belongs to the Ghost blog
    """
    if not url or not blog_url:
        return False

    # Normalize: ensure blog_url ends without slash for comparison
    blog_base = blog_url.rstrip("/")
    url_clean = url.rstrip("/")

    # The target must start with the blog URL and have a path component
    # (not just the root domain itself)
    if not url_clean.lower().startswith(blog_base.lower()):
        return False

    # Extract the path after the blog base URL
    path_after_base = url_clean[len(blog_base):]

    # Must have a path (not just the root)
    if not path_after_base or path_after_base == "/":
        return False

    return True


def _verify_source_links_to_target(source_url: str, target_url: str) -> tuple[bool, Optional[str]]:
    """Verify that the source URL actually contains a link to the target.

    Per the W3C Webmention spec, the receiver SHOULD verify that the
    source document contains a link to the target URL.

    Args:
        source_url: The URL claiming to link to the target
        target_url: The target URL that should be linked

    Returns:
        Tuple of (verified: bool, error: Optional[str])
    """
    try:
        response = requests.get(
            source_url,
            timeout=SOURCE_FETCH_TIMEOUT,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "text/html, application/xhtml+xml, */*",
            },
            allow_redirects=True,
        )

        if response.status_code >= 400:
            return False, f"Source returned HTTP {response.status_code}"

        content = response.text

        # Check if the target URL appears in the source document
        # Normalize both for comparison (with and without trailing slash)
        target_normalized = target_url.rstrip("/")
        target_with_slash = target_normalized + "/"

        if target_normalized in content or target_with_slash in content:
            return True, None

        return False, "Source does not contain a link to the target URL"

    except requests.exceptions.Timeout:
        return False, "Timeout fetching source URL"
    except requests.exceptions.RequestException as e:
        return False, f"Error fetching source URL: {e}"


def register_webmention_routes(app, config: Dict[str, Any]) -> None:
    """Register webmention receiver routes on the Flask app.

    Registers:
        - POST /webmention: Receive webmentions (W3C spec)
        - GET /webmention: Endpoint discovery info
        - GET /api/webmentions/<path>: Retrieve webmentions for a post

    Also adds a Link header to all responses for webmention endpoint
    discovery per the W3C spec (section 3.1.2).

    Args:
        app: Flask application instance
        config: Application configuration dictionary
    """
    from flask import request, jsonify, make_response

    # Extract blog URL from Ghost config
    ghost_config = config.get("ghost", {})
    content_api_config = ghost_config.get("content_api", {})
    blog_url = content_api_config.get("url", "")

    webmention_config = config.get("webmention", {})
    receiver_enabled = webmention_config.get("receiver_enabled", False)

    if not receiver_enabled:
        logger.info("Webmention receiver is disabled in configuration")
        return

    if not blog_url:
        logger.warning(
            "Webmention receiver enabled but no ghost.content_api.url configured. "
            "Cannot validate target URLs without a blog URL."
        )
        return

    blog_url = blog_url.rstrip("/")
    logger.info(f"Webmention receiver enabled for blog: {blog_url}")

    # Create the webmention store
    store = WebmentionStore()
    app.config["WEBMENTION_STORE"] = store

    # Add Link header for webmention endpoint discovery on all responses
    # Per W3C Webmention spec section 3.1.2: Sender discovers receiver's
    # webmention endpoint via Link header or <link> element.
    @app.after_request
    def add_webmention_link_header(response):
        """Add Link header advertising the webmention endpoint."""
        response.headers.setdefault(
            "Link",
            f'</webmention>; rel="webmention"'
        )
        return response

    @app.route("/webmention", methods=["POST"])
    def receive_webmention():
        """W3C Webmention receiving endpoint.

        Accepts POST requests with source and target parameters.
        Supports both application/x-www-form-urlencoded (W3C spec default)
        and application/json (for the Ghost interactions widget).

        The Ghost interactions widget submits webmentions by:
        1. Auto-filling target with the current post's canonical URL
        2. Accepting source URL input from the user
        3. POSTing to this endpoint as JSON

        Per the spec:
            - source: URL of the page that mentions the target
            - target: URL of the page being mentioned (must be a Ghost post)

        Returns:
            - 202 Accepted: Webmention accepted for processing
            - 400 Bad Request: Missing/invalid parameters
        """
        # Parse source and target from form data or JSON
        if request.content_type and "json" in request.content_type:
            data = request.get_json(silent=True) or {}
            source = data.get("source", "").strip()
            target = data.get("target", "").strip()
        else:
            source = request.form.get("source", "").strip()
            target = request.form.get("target", "").strip()

        # Validate required parameters
        if not source:
            return jsonify({
                "status": "error",
                "message": "Missing required parameter: source"
            }), 400

        if not target:
            return jsonify({
                "status": "error",
                "message": "Missing required parameter: target"
            }), 400

        # Validate URL formats
        if not _is_valid_url(source):
            return jsonify({
                "status": "error",
                "message": "Invalid source URL"
            }), 400

        if not _is_valid_url(target):
            return jsonify({
                "status": "error",
                "message": "Invalid target URL"
            }), 400

        # Source and target must be different
        if source.rstrip("/") == target.rstrip("/"):
            return jsonify({
                "status": "error",
                "message": "Source and target must be different URLs"
            }), 400

        # Restrict target to Ghost blog posts only
        if not _is_ghost_post_url(target, blog_url):
            logger.info(f"Rejected webmention: target {target} is not a post on {blog_url}")
            return jsonify({
                "status": "error",
                "message": "Target URL is not a valid post on this blog"
            }), 400

        logger.info(f"Received webmention: source={source}, target={target}")

        # Verify source links to target
        verified, error = _verify_source_links_to_target(source, target)

        mention = ReceivedWebmention(
            source=source,
            target=target,
            verified=verified,
            verification_error=error,
        )

        if verified:
            store.add(mention)
            logger.info(f"Webmention verified and stored: source={source}, target={target}")
        else:
            store.add(mention)
            logger.warning(
                f"Webmention stored but verification failed: source={source}, "
                f"target={target}, error={error}"
            )

        # Return 202 Accepted per W3C spec
        # Include verification_error so the widget can display feedback
        response_data = {
            "status": "accepted",
            "message": "Webmention received and verified" if verified else "Webmention received but verification failed",
            "source": source,
            "target": target,
            "verified": verified,
        }
        if not verified and error:
            response_data["verification_error"] = error

        return jsonify(response_data), 202

    @app.route("/webmention", methods=["GET"])
    def webmention_info():
        """Webmention endpoint discovery info.

        Returns information about the webmention endpoint and the blog
        it serves. The widget can use this to verify it's pointing at
        the correct POSSE instance.
        """
        return jsonify({
            "status": "ok",
            "message": "Webmention endpoint",
            "blog_url": blog_url,
            "total_webmentions": store.count(),
        }), 200

    @app.route("/api/webmentions/<path:target_path>", methods=["GET"])
    def get_webmentions(target_path: str):
        """Retrieve webmentions for a specific Ghost post.

        The widget can call this to display received webmentions
        alongside social media interactions.

        Args:
            target_path: The path portion of the Ghost post URL
                        (e.g., "my-post/" for https://blog.example.com/my-post/)

        Returns:
            JSON with webmentions for the target, each containing:
            - source: URL of the mentioning page
            - target: The Ghost post URL
            - verified: Whether the source was verified
            - received_at: Unix timestamp
        """
        # Reconstruct full target URL
        target_url = f"{blog_url}/{target_path}"

        mentions = store.get_for_target(target_url)
        # Also check without trailing slash
        if not mentions:
            alt_url = target_url.rstrip("/") if target_url.endswith("/") else target_url + "/"
            mentions = store.get_for_target(alt_url)

        return jsonify({
            "target": target_url,
            "webmentions": [asdict(m) for m in mentions],
            "count": len(mentions),
        }), 200
