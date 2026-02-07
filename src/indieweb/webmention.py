"""
Webmention protocol implementation.

Provides both generic W3C Webmention sending (with endpoint discovery)
and the IndieWeb News-specific client.

Webmention is a W3C standard for notifying a URL when you link to it.
The protocol is simple:

    POST {webmention-endpoint}
    Content-Type: application/x-www-form-urlencoded

    source={your-post-url}&target={linked-url}

Usage:
    >>> from indieweb.webmention import send_webmention, IndieWebNewsClient
    >>> # Generic webmention with endpoint discovery
    >>> result = send_webmention("https://reply.example.com/reply/abc", "https://blog.example.com/post")
    >>> # IndieWeb News specific
    >>> client = IndieWebNewsClient()
    >>> result = client.send_webmention("https://blog.example.com/my-post")

References:
    - W3C Webmention: https://www.w3.org/TR/webmention/
    - IndieWeb News: https://news.indieweb.org/
"""

import logging
import re
from dataclasses import dataclass
from typing import Optional, Dict, Any
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
    """
    success: bool
    status_code: int
    message: str
    location: Optional[str] = None


class IndieWebNewsClient:
    """Client for sending webmentions to IndieWeb News.

    This client implements the W3C Webmention protocol for submitting
    blog posts to IndieWeb News for syndication.

    Attributes:
        endpoint: Webmention endpoint URL
        target: Target URL for the webmention (IndieWeb News page)
        timeout: Request timeout in seconds

    Example:
        >>> client = IndieWebNewsClient()
        >>> result = client.send_webmention("https://blog.example.com/post")
        >>> print(f"Success: {result.success}, Status: {result.status_code}")
    """

    # Default IndieWeb News endpoints
    DEFAULT_ENDPOINT = "https://news.indieweb.org/en/webmention"
    DEFAULT_TARGET = "https://news.indieweb.org/en"
    DEFAULT_TIMEOUT = 30.0

    def __init__(
        self,
        endpoint: Optional[str] = None,
        target: Optional[str] = None,
        timeout: Optional[float] = None
    ):
        """Initialize the IndieWeb News client.

        Args:
            endpoint: Webmention endpoint URL (default: IndieWeb News endpoint)
            target: Target URL for webmentions (default: IndieWeb News EN page)
            timeout: Request timeout in seconds (default: 30)
        """
        self.endpoint = endpoint or self.DEFAULT_ENDPOINT
        self.target = target or self.DEFAULT_TARGET
        self.timeout = timeout or self.DEFAULT_TIMEOUT

    @classmethod
    def from_config(cls, config: Dict[str, Any]) -> "IndieWebNewsClient":
        """Create client from configuration dictionary.

        Args:
            config: Configuration dictionary from config.yml

        Returns:
            Initialized IndieWebNewsClient instance

        Example:
            >>> config = load_config()
            >>> client = IndieWebNewsClient.from_config(config)
        """
        indieweb_config = config.get("indieweb", {})
        news_config = indieweb_config.get("news", {})

        return cls(
            endpoint=news_config.get("endpoint"),
            target=news_config.get("target"),
            timeout=news_config.get("timeout")
        )

    def send_webmention(self, source_url: str) -> WebmentionResult:
        """Send a webmention to IndieWeb News.

        This method sends a webmention to notify IndieWeb News that
        a blog post at source_url should be syndicated.

        Args:
            source_url: The full URL of the published post.

        Returns:
            WebmentionResult with success status and details.

        Example:
            >>> result = client.send_webmention("https://blog.example.com/post")
            >>> if result.success:
            ...     print(f"Accepted! Status URL: {result.location}")
            ... else:
            ...     print(f"Failed: {result.message}")
        """
        payload = {
            "source": source_url,
            "target": self.target,
        }

        logger.info(
            f"Sending webmention to IndieWeb News: source={source_url}, target={self.target}"
        )

        try:
            response = requests.post(
                self.endpoint,
                data=payload,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=self.timeout
            )

            # Webmention spec: 2xx = accepted
            if response.ok:
                location = response.headers.get("Location")
                logger.info(
                    f"Webmention accepted by IndieWeb News: "
                    f"source={source_url}, status_code={response.status_code}, location={location}"
                )
                return WebmentionResult(
                    success=True,
                    status_code=response.status_code,
                    message="Webmention accepted",
                    location=location,
                )

            # Handle specific error cases
            error_msg = self._parse_error(response)
            logger.warning(
                f"Webmention rejected by IndieWeb News: "
                f"source={source_url}, status_code={response.status_code}, error={error_msg}"
            )
            return WebmentionResult(
                success=False,
                status_code=response.status_code,
                message=error_msg,
            )

        except requests.exceptions.Timeout:
            logger.error(f"Webmention request timed out: source={source_url}")
            return WebmentionResult(
                success=False,
                status_code=0,
                message="Request timed out",
            )
        except requests.exceptions.RequestException as e:
            logger.error(
                f"Webmention request failed: source={source_url}, error={str(e)}"
            )
            return WebmentionResult(
                success=False,
                status_code=0,
                message=f"Request failed: {e}",
            )

    def _parse_error(self, response: requests.Response) -> str:
        """Parse error message from response.

        Args:
            response: HTTP response object

        Returns:
            Human-readable error message
        """
        try:
            # Try JSON error response
            data = response.json()
            if "error" in data:
                return data.get("error_description", data["error"])
        except Exception:
            pass

        # Try to get meaningful text from response body
        try:
            text = response.text.strip()
            if text and len(text) < 200:
                return f"HTTP {response.status_code}: {text}"
        except Exception:
            pass

        # Fall back to status text
        return f"HTTP {response.status_code}: {response.reason}"


def send_to_indieweb_news(post_url: str, config: Optional[Dict[str, Any]] = None) -> WebmentionResult:
    """Convenience function to send a webmention to IndieWeb News.

    Args:
        post_url: The full URL of the published post.
        config: Optional configuration dictionary for custom endpoints.

    Returns:
        WebmentionResult with success status and details.

    Example:
        >>> result = send_to_indieweb_news("https://blog.example.com/my-post")
        >>> if result.success:
        ...     print("Submitted to IndieWeb News!")
    """
    if config:
        client = IndieWebNewsClient.from_config(config)
    else:
        client = IndieWebNewsClient()

    return client.send_webmention(post_url)


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
        )

    except requests.exceptions.Timeout:
        logger.error(f"Webmention request timed out: endpoint={endpoint}")
        return WebmentionResult(success=False, status_code=0, message="Request timed out")
    except requests.exceptions.RequestException as e:
        logger.error(f"Webmention request failed: endpoint={endpoint}, error={e}")
        return WebmentionResult(success=False, status_code=0, message=f"Request failed: {e}")


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
