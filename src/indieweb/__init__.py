"""
IndieWeb Module for POSSE.

This module provides IndieWeb integration, including webmention sending
for automatic submission to IndieWeb News when posts are tagged appropriately.

The module follows the W3C Webmention protocol to notify IndieWeb News
when a blog post should be syndicated there.

Features:
    - Webmention sending to IndieWeb News
    - Tag-based filtering for IndieWeb News submission
    - Configurable endpoints and target URLs

Usage:
    >>> from indieweb import IndieWebNewsClient, has_indieweb_tag
    >>>
    >>> # Check if post should be submitted
    >>> if has_indieweb_tag(post_tags):
    ...     client = IndieWebNewsClient()
    ...     result = client.send_webmention(post_url)
    ...     if result.success:
    ...         print("Submitted to IndieWeb News")

Configuration (config.yml):
    indieweb:
      enabled: true
      news:
        endpoint: "https://news.indieweb.org/en/webmention"
        target: "https://news.indieweb.org/en"
        tag: "indiewebnews"
"""

from indieweb.webmention import IndieWebNewsClient, WebmentionResult, send_to_indieweb_news
from indieweb.utils import has_indieweb_tag

__all__ = [
    "IndieWebNewsClient",
    "WebmentionResult",
    "send_to_indieweb_news",
    "has_indieweb_tag",
]
