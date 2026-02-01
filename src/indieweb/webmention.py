"""
IndieWeb News webmention sender.

Sends webmentions to IndieWeb News for posts tagged with 'indiewebnews'.
The Ghost theme must include the u-syndication link to news.indieweb.org
for the webmention to be accepted.

Webmention is a W3C standard for notifying a URL when you link to it.
The protocol is simple:

    POST {webmention-endpoint}
    Content-Type: application/x-www-form-urlencoded

    source={your-post-url}&target={linked-url}

For IndieWeb News, the endpoint is https://news.indieweb.org/webmention.

Usage:
    >>> from indieweb.webmention import IndieWebNewsClient
    >>> client = IndieWebNewsClient()
    >>> result = client.send_webmention("https://blog.example.com/my-post")
    >>> if result.success:
    ...     print("Webmention accepted")

Expected Responses:
    - Success (HTTP 200/201/202): Webmention accepted
    - Error - No Link Found (HTTP 400): u-syndication link missing from post
    - Error - Source Not Found (HTTP 400): Post URL returned 404

References:
    - W3C Webmention: https://www.w3.org/TR/webmention/
    - IndieWeb News: https://news.indieweb.org/
"""

import logging
from dataclasses import dataclass
from typing import Optional, Dict, Any

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
    DEFAULT_ENDPOINT = "https://news.indieweb.org/webmention"
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
