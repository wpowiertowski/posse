"""
IndieWeb Module for POSSE.

This module provides IndieWeb integration, including webmention sending
to configurable targets when posts are tagged appropriately.

The module follows the W3C Webmention protocol to notify target URLs
when a blog post should be syndicated there.

Features:
    - Tag-triggered webmention sending to configurable targets
    - W3C Webmention endpoint discovery
    - Generic webmention sending with endpoint discovery

Usage:
    >>> from indieweb import WebmentionClient, WebmentionTarget, has_tag
    >>>
    >>> # Check if post should be submitted and send
    >>> client = WebmentionClient.from_config(config)
    >>> results = client.send_for_post(post_url, post_tag_slugs)

Configuration (config.yml):
    webmention:
      enabled: true
      targets:
        - name: "IndieWeb News"
          endpoint: "https://news.indieweb.org/en/webmention"
          target: "https://news.indieweb.org/en"
          tag: "indiewebnews"
"""

from indieweb.webmention import (
    WebmentionClient,
    WebmentionTarget,
    WebmentionResult,
    discover_webmention_endpoint,
    send_webmention,
    _is_private_or_loopback,
)
from indieweb.utils import has_tag

__all__ = [
    "WebmentionClient",
    "WebmentionTarget",
    "WebmentionResult",
    "discover_webmention_endpoint",
    "send_webmention",
    "_is_private_or_loopback",
    "has_tag",
]
