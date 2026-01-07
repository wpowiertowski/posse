"""
Post Filtering Module for POSSE.

This module provides functionality to filter Ghost posts based on
account-specific filter criteria. Filters can match on tags, visibility,
featured status, and other post attributes.

Filter Criteria:
    - tags: List of tag slugs to include (OR logic - post matches if ANY tag matches)
    - exclude_tags: List of tag slugs to exclude (takes precedence over tags)
    - visibility: List of visibility values to include ("public", "members", "paid")
    - featured: Boolean to filter featured/non-featured posts
    - status: List of status values to include ("draft", "published", "scheduled")

Usage:
    >>> filters = {
    ...     "tags": ["tech", "programming"],
    ...     "exclude_tags": ["draft"],
    ...     "visibility": ["public"],
    ...     "featured": True
    ... }
    >>> if matches_filters(ghost_post, filters):
    ...     # Post matches, send to this account
"""
import logging
from typing import Dict, Any, List, Optional


logger = logging.getLogger(__name__)


def _extract_tag_slugs(post_data: Dict[str, Any]) -> List[str]:
    """Extract tag slugs from Ghost post data.
    
    Helper function to avoid code duplication when extracting tags.
    
    Args:
        post_data: Ghost post current data dictionary
        
    Returns:
        List of tag slugs from the post
    """
    return [tag['slug'] for tag in post_data.get('tags', [])]


def matches_filters(ghost_post: Dict[str, Any], filters: Dict[str, Any]) -> bool:
    """Check if a Ghost post matches the specified filters.
    
    This function evaluates a Ghost post against filter criteria to determine
    if it should be syndicated to a particular account. An empty filter dict
    matches all posts.
    
    Filter Logic:
        - Empty filters ({}) match all posts
        - exclude_tags takes precedence over tags
        - All specified filter criteria must match (AND logic)
        - Within tags filter, ANY tag can match (OR logic)
    
    Args:
        ghost_post: Ghost webhook payload dictionary
        filters: Dictionary of filter criteria
        
    Returns:
        True if the post matches all filter criteria, False otherwise
        
    Example:
        >>> post = {
        ...     "post": {
        ...         "current": {
        ...             "tags": [{"slug": "tech"}],
        ...             "visibility": "public",
        ...             "featured": True,
        ...             "status": "published"
        ...         }
        ...     }
        ... }
        >>> filters = {"tags": ["tech"], "visibility": ["public"]}
        >>> matches_filters(post, filters)
        True
    """
    # Empty filters match all posts
    if not filters:
        return True
    
    # Extract post data from Ghost webhook structure
    post_data = ghost_post.get('post', {}).get('current', {})
    
    # Extract tags once if needed for tag-based filters
    post_tags = None
    if 'exclude_tags' in filters or 'tags' in filters:
        post_tags = _extract_tag_slugs(post_data)
    
    # Check exclude_tags first (takes precedence)
    exclude_tags = filters.get('exclude_tags', [])
    if exclude_tags:
        if any(tag in post_tags for tag in exclude_tags):
            logger.debug(f"Post excluded by exclude_tags filter: {exclude_tags}")
            return False
    
    # Check tags filter (OR logic - any tag matches)
    tags_filter = filters.get('tags', [])
    if tags_filter:
        if not any(tag in post_tags for tag in tags_filter):
            logger.debug(f"Post does not match tags filter: {tags_filter}")
            return False
    
    # Check visibility filter
    visibility_filter = filters.get('visibility', [])
    if visibility_filter:
        post_visibility = post_data.get('visibility')
        if post_visibility not in visibility_filter:
            logger.debug(f"Post visibility '{post_visibility}' not in filter: {visibility_filter}")
            return False
    
    # Check featured filter
    if 'featured' in filters:
        featured_filter = filters['featured']
        post_featured = post_data.get('featured', False)
        if post_featured != featured_filter:
            logger.debug(f"Post featured status '{post_featured}' does not match filter: {featured_filter}")
            return False
    
    # Check status filter
    status_filter = filters.get('status', [])
    if status_filter:
        post_status = post_data.get('status')
        if post_status not in status_filter:
            logger.debug(f"Post status '{post_status}' not in filter: {status_filter}")
            return False
    
    # All filters passed
    logger.debug(f"Post matches all filters")
    return True


def get_matching_accounts(
    ghost_post: Dict[str, Any],
    accounts_config: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """Get list of accounts that match filters for a given Ghost post.
    
    This function evaluates a Ghost post against all configured accounts
    and returns only those accounts whose filters match the post.
    
    Args:
        ghost_post: Ghost webhook payload dictionary
        accounts_config: List of account configuration dictionaries
        
    Returns:
        List of account configurations that match the post
        
    Example:
        >>> post = {"post": {"current": {"tags": [{"slug": "tech"}]}}}
        >>> accounts = [
        ...     {"name": "personal", "filters": {"tags": ["tech"]}},
        ...     {"name": "work", "filters": {"tags": ["business"]}}
        ... ]
        >>> matching = get_matching_accounts(post, accounts)
        >>> [acc["name"] for acc in matching]
        ['personal']
    """
    matching = []
    
    for account in accounts_config:
        account_name = account.get('name', 'unnamed')
        filters = account.get('filters', {})
        
        if matches_filters(ghost_post, filters):
            logger.info(f"Post matches account '{account_name}' filters")
            matching.append(account)
        else:
            logger.debug(f"Post does not match account '{account_name}' filters")
    
    return matching
