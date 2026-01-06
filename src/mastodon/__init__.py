"""
Mastodon Integration Module for POSSE.

This module provides functionality for authenticating with Mastodon instances
and posting content from Ghost blog posts.

The module handles:
- Mastodon app registration
- User authentication via OAuth
- Credential management via Docker secrets
- Post creation and publishing

Usage:
    >>> from config import load_config
    >>> config = load_config()
    >>> client = MastodonClient.from_config(config)
    >>> if client.enabled:
    ...     client.post_status("Hello from POSSE!")
"""

from .mastodon import MastodonClient

__all__ = ['MastodonClient']
