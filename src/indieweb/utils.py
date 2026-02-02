"""
IndieWeb utilities.

This module provides utility functions for IndieWeb integration,
including tag checking and other helper functions.

Usage:
    >>> from indieweb.utils import has_indieweb_tag
    >>> tags = [{"name": "tech", "slug": "tech"}, {"name": "IndieWebNews", "slug": "indiewebnews"}]
    >>> if has_indieweb_tag(tags):
    ...     print("This post should be submitted to IndieWeb News")
"""

import logging
from typing import List, Dict, Optional


logger = logging.getLogger(__name__)


# Default tag slug for IndieWeb News submission
DEFAULT_INDIEWEB_TAG = "indiewebnews"


def has_indieweb_tag(
    tags: Optional[List[Dict[str, str]]],
    tag_slug: str = DEFAULT_INDIEWEB_TAG
) -> bool:
    """Check if post has the IndieWeb News tag.

    This function checks if a post's tags include the IndieWeb News tag,
    which indicates that the post should be submitted to IndieWeb News
    via webmention.

    Args:
        tags: List of tag dictionaries from Ghost webhook payload.
              Each tag dict should have 'slug' and optionally 'name' keys.
        tag_slug: The tag slug to match (default: "indiewebnews").
                  Matching is case-insensitive.

    Returns:
        True if the IndieWeb News tag is present, False otherwise.

    Example:
        >>> tags = [
        ...     {"name": "Technology", "slug": "technology"},
        ...     {"name": "IndieWebNews", "slug": "indiewebnews"}
        ... ]
        >>> has_indieweb_tag(tags)
        True

        >>> tags = [{"name": "Personal", "slug": "personal"}]
        >>> has_indieweb_tag(tags)
        False

        >>> has_indieweb_tag(None)
        False
    """
    if not tags:
        return False

    tag_slug_lower = tag_slug.lower()

    for tag in tags:
        if not isinstance(tag, dict):
            continue

        # Check slug field (primary match)
        slug = tag.get("slug", "")
        if slug and slug.lower() == tag_slug_lower:
            logger.debug(f"Found IndieWeb tag by slug: {slug}")
            return True

        # Also check name field for flexibility
        name = tag.get("name", "")
        if name and name.lower() == tag_slug_lower:
            logger.debug(f"Found IndieWeb tag by name: {name}")
            return True

    return False


def get_indieweb_config(config: Dict) -> Dict:
    """Extract IndieWeb configuration from main config.

    Args:
        config: Main configuration dictionary from config.yml

    Returns:
        IndieWeb-specific configuration dictionary with defaults applied.

    Example:
        >>> config = load_config()
        >>> indieweb_config = get_indieweb_config(config)
        >>> if indieweb_config["enabled"]:
        ...     print(f"IndieWeb enabled with tag: {indieweb_config['news']['tag']}")
    """
    indieweb = config.get("indieweb", {})

    # Apply defaults
    return {
        "enabled": indieweb.get("enabled", False),
        "news": {
            "endpoint": indieweb.get("news", {}).get(
                "endpoint", "https://news.indieweb.org/en/webmention"
            ),
            "target": indieweb.get("news", {}).get(
                "target", "https://news.indieweb.org/en"
            ),
            "tag": indieweb.get("news", {}).get("tag", DEFAULT_INDIEWEB_TAG),
            "timeout": indieweb.get("news", {}).get("timeout", 30),
        }
    }
