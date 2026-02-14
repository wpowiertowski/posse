"""
Webmention protocol implementation.

Provides both generic W3C Webmention sending (with endpoint discovery)
and a configurable client for sending webmentions to one or more targets
when a post is tagged appropriately.

Webmention is a W3C standard for notifying a URL when you link to it.
The protocol is simple:

    POST {webmention-endpoint}
    Content-Type: application/x-www-form-urlencoded

    source={your-post-url}&target={linked-url}

Usage:
    >>> from indieweb.webmention import send_webmention, WebmentionClient
    >>> # Generic webmention with endpoint discovery
    >>> result = send_webmention("https://reply.example.com/reply/abc", "https://blog.example.com/post")
    >>> # Tag-triggered webmention to configured targets
    >>> client = WebmentionClient.from_config(config)
    >>> results = client.send_for_post("https://blog.example.com/my-post", ["indiewebnews"])

References:
    - W3C Webmention: https://www.w3.org/TR/webmention/
"""

import logging
import re
from dataclasses import dataclass
from typing import Optional, Dict, Any, List
from urllib.parse import urljoin

import requests


logger = logging.getLogger(__name__)


@dataclass
class WebmentionResult:
    """Result of a webmention send attempt.

    Attributes:
        success: Whether the webmention was accepted
        status_code: HTTP status code from the response (0 for connection errors)
        message: Human-readable status message
        location: Optional status URL returned by some endpoints
        endpoint: Optional webmention endpoint URL used for this send
        target_name: Optional human-readable name of the target
    """
    success: bool
    status_code: int
    message: str
    location: Optional[str] = None
    endpoint: Optional[str] = None
    target_name: Optional[str] = None


@dataclass
class WebmentionTarget:
    """A webmention target: a destination that should receive webmentions for matching posts.

    Attributes:
        name: Human-readable name for this target (e.g. "IndieWeb News EN")
        endpoint: Webmention endpoint URL to POST to
        target: Target URL sent as the 'target' parameter in the webmention
        tag: Tag slug that triggers sending to this target
        timeout: Request timeout in seconds
    """
    name: str
    endpoint: str
    target: str
    tag: str
    timeout: float = 30.0


class WebmentionClient:
    """Client for sending webmentions to configured targets.

    Sends webmentions to one or more targets based on post tags.
    Each target specifies a tag that triggers sending, an endpoint
    URL, and a target URL.

    Example:
        >>> client = WebmentionClient([
        ...     WebmentionTarget(
        ...         name="IndieWeb News",
        ...         endpoint="https://news.indieweb.org/en/webmention",
        ...         target="https://news.indieweb.org/en",
        ...         tag="indiewebnews",
        ...     )
        ... ])
        >>> results = client.send_for_post("https://blog.example.com/post", ["indiewebnews"])
    """

    def __init__(self, targets: Optional[List[WebmentionTarget]] = None):
        """Initialize the webmention client.

        Args:
            targets: List of webmention targets to send to.
        """
        self.targets = targets or []

    @classmethod
    def from_config(cls, config: Dict[str, Any]) -> "WebmentionClient":
        """Create client from configuration dictionary.

        Supports both the current ``webmention:`` config key and the legacy
        ``indieweb:`` key.  When the legacy key is detected, the single
        IndieWeb News target is converted into the new multi-target format.

        Args:
            config: Configuration dictionary from config.yml

        Returns:
            Initialized WebmentionClient instance

        Example:
            >>> config = load_config()
            >>> client = WebmentionClient.from_config(config)
        """
        from indieweb.utils import get_webmention_config

        wm_config = get_webmention_config(config)
        targets_config = wm_config.get("targets", [])

        targets = []
        for t in targets_config:
            targets.append(WebmentionTarget(
                name=t.get("name", ""),
                endpoint=t["endpoint"],
                target=t["target"],
                tag=t.get("tag", ""),
                timeout=t.get("timeout", 30.0),
            ))

        return cls(targets=targets)

    def send_for_post(
        self, source_url: str, post_tags: List[str]
    ) -> List[WebmentionResult]:
        """Send webmentions to all targets whose tag matches the post's tags.

        Args:
            source_url: The full URL of the published post.
            post_tags: List of tag slugs on the post (lowercase).

        Returns:
            List of WebmentionResult for each matching target.
        """
        post_tags_lower = {t.lower() for t in post_tags}
        results = []

        for target in self.targets:
            if target.tag.lower() not in post_tags_lower:
                continue

            result = self._send_webmention(source_url, target)
            results.append(result)

        return results

    def _send_webmention(
        self, source_url: str, target: WebmentionTarget
    ) -> WebmentionResult:
        """Send a webmention to a single target.

        Args:
            source_url: The full URL of the published post.
            target: The webmention target to send to.

        Returns:
            WebmentionResult with success status and details.
        """
        payload = {
            "source": source_url,
            "target": target.target,
        }

        target_label = target.name or target.target
        logger.info(
            f"Sending webmention to {target_label}: source={source_url}, target={target.target}"
        )

        try:
            response = requests.post(
                target.endpoint,
                data=payload,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=target.timeout
            )

            if response.ok:
                location = response.headers.get("Location")
                logger.info(
                    f"Webmention accepted by {target_label}: "
                    f"source={source_url}, status_code={response.status_code}, location={location}"
                )
                return WebmentionResult(
                    success=True,
                    status_code=response.status_code,
                    message="Webmention accepted",
                    location=location,
                    endpoint=target.endpoint,
                    target_name=target.name,
                )

            error_msg = _parse_error_response(response)
            logger.warning(
                f"Webmention rejected by {target_label}: "
                f"source={source_url}, status_code={response.status_code}, error={error_msg}"
            )
            return WebmentionResult(
                success=False,
                status_code=response.status_code,
                message=error_msg,
                endpoint=target.endpoint,
                target_name=target.name,
            )

        except requests.exceptions.Timeout:
            logger.error(f"Webmention request timed out: target={target_label}, source={source_url}")
            return WebmentionResult(
                success=False,
                status_code=0,
                message="Request timed out",
                endpoint=target.endpoint,
                target_name=target.name,
            )
        except requests.exceptions.RequestException as e:
            logger.error(
                f"Webmention request failed: target={target_label}, source={source_url}, error={str(e)}"
            )
            return WebmentionResult(
                success=False,
                status_code=0,
                message=f"Request failed: {e}",
                endpoint=target.endpoint,
                target_name=target.name,
            )


# =========================================================================
# Generic W3C Webmention: endpoint discovery + sending
# =========================================================================

def discover_webmention_endpoint(target_url: str, timeout: float = 30.0) -> Optional[str]:
    """Discover the webmention endpoint for a target URL.

    Follows the W3C Webmention discovery algorithm:
    1. Check HTTP Link header for rel="webmention"
    2. Parse HTML for <link rel="webmention"> or <a rel="webmention">

    Args:
        target_url: The URL to discover the webmention endpoint for.
        timeout: Request timeout in seconds.

    Returns:
        The absolute webmention endpoint URL, or None if not found.
    """
    try:
        response = requests.get(
            target_url,
            headers={"Accept": "text/html"},
            timeout=timeout,
            allow_redirects=True,
        )
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to fetch target for webmention discovery: {target_url}, error={e}")
        return None

    # 1. Check Link header
    link_header = response.headers.get("Link", "")
    if link_header:
        # Match: <URL>; rel="webmention"  or  <URL>; rel=webmention
        match = re.search(r'<([^>]+)>;\s*rel="?webmention"?', link_header)
        if match:
            return urljoin(target_url, match.group(1))

    # 2. Parse HTML for <link> or <a> with rel="webmention"
    html = response.text
    # <link rel="webmention" href="...">
    pattern1 = re.search(
        r'<link[^>]+rel=["\']?webmention["\']?[^>]+href=["\']([^"\']+)["\']',
        html, re.IGNORECASE,
    )
    if pattern1:
        return urljoin(target_url, pattern1.group(1))

    # <link href="..." rel="webmention">
    pattern2 = re.search(
        r'<link[^>]+href=["\']([^"\']+)["\'][^>]+rel=["\']?webmention["\']?',
        html, re.IGNORECASE,
    )
    if pattern2:
        return urljoin(target_url, pattern2.group(1))

    # <a rel="webmention" href="...">
    pattern3 = re.search(
        r'<a[^>]+rel=["\']?webmention["\']?[^>]+href=["\']([^"\']+)["\']',
        html, re.IGNORECASE,
    )
    if pattern3:
        return urljoin(target_url, pattern3.group(1))

    logger.info(f"No webmention endpoint found for: {target_url}")
    return None


def send_webmention(source_url: str, target_url: str, timeout: float = 30.0) -> WebmentionResult:
    """Send a webmention from source to target with automatic endpoint discovery.

    Discovers the webmention endpoint from the target URL, then sends
    the webmention per W3C spec.

    Args:
        source_url: The URL of the page that mentions the target.
        target_url: The URL being mentioned (the blog post).
        timeout: Request timeout in seconds.

    Returns:
        WebmentionResult with success status and details.

    Example:
        >>> result = send_webmention(
        ...     "https://reply.example.com/reply/abc123",
        ...     "https://blog.example.com/my-post"
        ... )
        >>> if result.success:
        ...     print("Webmention sent!")
    """
    # Discover endpoint
    endpoint = discover_webmention_endpoint(target_url, timeout=timeout)
    if not endpoint:
        return WebmentionResult(
            success=False,
            status_code=0,
            message=f"No webmention endpoint found for {target_url}",
            endpoint=None,
        )

    logger.info(f"Sending webmention: source={source_url}, target={target_url}, endpoint={endpoint}")

    try:
        response = requests.post(
            endpoint,
            data={"source": source_url, "target": target_url},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=timeout,
        )

        if response.ok:
            location = response.headers.get("Location")
            logger.info(
                f"Webmention accepted: source={source_url}, target={target_url}, "
                f"status_code={response.status_code}, location={location}"
            )
            return WebmentionResult(
                success=True,
                status_code=response.status_code,
                message="Webmention accepted",
                location=location,
                endpoint=endpoint,
            )

        # Parse error
        error_msg = _parse_error_response(response)
        logger.warning(
            f"Webmention rejected: source={source_url}, target={target_url}, "
            f"status_code={response.status_code}, error={error_msg}"
        )
        return WebmentionResult(
            success=False,
            status_code=response.status_code,
            message=error_msg,
            endpoint=endpoint,
        )

    except requests.exceptions.Timeout:
        logger.error(f"Webmention request timed out: endpoint={endpoint}")
        return WebmentionResult(success=False, status_code=0, message="Request timed out", endpoint=endpoint)
    except requests.exceptions.RequestException as e:
        logger.error(f"Webmention request failed: endpoint={endpoint}, error={e}")
        return WebmentionResult(success=False, status_code=0, message=f"Request failed: {e}", endpoint=endpoint)


def _parse_error_response(response: requests.Response) -> str:
    """Parse error message from an HTTP response."""
    try:
        data = response.json()
        if "error" in data:
            return data.get("error_description", data["error"])
    except Exception:
        pass
    try:
        text = response.text.strip()
        if text and len(text) < 200:
            return f"HTTP {response.status_code}: {text}"
    except Exception:
        pass
    return f"HTTP {response.status_code}: {response.reason}"
