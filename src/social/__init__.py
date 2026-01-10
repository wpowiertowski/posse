"""
Social Media Integration Module for POSSE.

This module provides base classes and common functionality for social media integrations.
"""

from .base_client import SocialMediaClient
from .mastodon_client import MastodonClient
from .bluesky_client import BlueskyClient

__all__ = ["SocialMediaClient", "MastodonClient", "BlueskyClient"]
