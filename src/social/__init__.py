"""
Social Media Integration Module for POSSE.

This module provides base classes and common functionality for social media integrations.
"""

from .base_client import SocialMediaClient
from .filters import matches_filters, get_matching_accounts

__all__ = ['SocialMediaClient', 'matches_filters', 'get_matching_accounts']
