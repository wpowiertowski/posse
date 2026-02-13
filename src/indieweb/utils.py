"""
IndieWeb utilities.

This module provides utility functions for IndieWeb integration,
including tag checking and configuration helpers.

Usage:
    >>> from indieweb.utils import has_tag
    >>> tags = [{"name": "tech", "slug": "tech"}, {"name": "IndieWebNews", "slug": "indiewebnews"}]
    >>> if has_tag(tags, "indiewebnews"):
    ...     print("This post matches the tag")
"""

import logging
from typing import List, Dict, Optional


logger = logging.getLogger(__name__)


def has_tag(
    tags: Optional[List[Dict[str, str]]],
    tag_slug: str,
) -> bool:
    """Check if a post has a given tag.

    This function checks if a post's tags include the specified tag,
    matching case-insensitively against both slug and name fields.

    Args:
        tags: List of tag dictionaries from Ghost webhook payload.
              Each tag dict should have 'slug' and optionally 'name' keys.
        tag_slug: The tag slug to match. Matching is case-insensitive.

    Returns:
        True if the tag is present, False otherwise.

    Example:
        >>> tags = [
        ...     {"name": "Technology", "slug": "technology"},
        ...     {"name": "IndieWebNews", "slug": "indiewebnews"}
        ... ]
        >>> has_tag(tags, "indiewebnews")
        True

        >>> tags = [{"name": "Personal", "slug": "personal"}]
        >>> has_tag(tags, "indiewebnews")
        False

        >>> has_tag(None, "anything")
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
            logger.debug(f"Found tag by slug: {slug}")
            return True

        # Also check name field for flexibility
        name = tag.get("name", "")
        if name and name.lower() == tag_slug_lower:
            logger.debug(f"Found tag by name: {name}")
            return True

    return False


def get_webmention_config(config: Dict) -> Dict:
    """Extract webmention configuration from main config.

    Args:
        config: Main configuration dictionary from config.yml

    Returns:
        Webmention-specific configuration dictionary with defaults applied.

    Example:
        >>> config = load_config()
        >>> wm_config = get_webmention_config(config)
        >>> if wm_config["enabled"]:
        ...     print(f"Webmention enabled with {len(wm_config['targets'])} targets")
    """
    wm = config.get("webmention", {})

    return {
        "enabled": wm.get("enabled", False),
        "targets": wm.get("targets", []),
    }
