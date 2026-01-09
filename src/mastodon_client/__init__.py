"""
Mastodon Integration Module for POSSE.

This module provides functionality for posting content to Mastodon 
from Ghost blog posts.

The module handles:
- Credential management via Docker secrets
- Post creation and publishing

Usage:
    >>> from config import load_config
    >>> config = load_config()
    >>> client = MastodonClient.from_config(config)
    >>> if client.enabled:
    ...     client.post_status("Hello from POSSE!")
"""

from .mastodon_client import MastodonClient

__all__ = ["MastodonClient"]
