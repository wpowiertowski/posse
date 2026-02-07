"""
Interaction Sync Scheduler for POSSE.

This module provides a background scheduler that periodically syncs
interactions for syndicated posts.
"""
import logging
import threading
import time
from typing import Optional, List, Any, Dict
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from interactions.interaction_sync import InteractionSyncService
from interactions.storage import InteractionDataStore

logger = logging.getLogger(__name__)


class InteractionScheduler:
    """
    Scheduler for periodically syncing social media interactions.

    This scheduler runs in a background thread and syncs interactions
    for all posts with syndication mappings, using a smart strategy
    that syncs recent posts more frequently.

    When a Ghost API client is provided, the scheduler uses the Ghost
    Content API to discover recent posts and syncs only those posts
    that exist in both Ghost and have syndication mappings.

    Attributes:
        sync_service: InteractionSyncService instance
        sync_interval_minutes: Base sync interval in minutes
        max_post_age_days: Maximum age of posts to sync (in days)
        enabled: Whether the scheduler is enabled
        ghost_api_client: Optional Ghost Content API client
    """

    def __init__(
        self,
        sync_service: InteractionSyncService,
        sync_interval_minutes: int = 30,
        max_post_age_days: int = 30,
        enabled: bool = True,
        ghost_api_client: Optional[Any] = None,
        timezone_name: str = "UTC",
    ):
        """
        Initialize the interaction scheduler.

        Args:
            sync_service: InteractionSyncService instance
            sync_interval_minutes: Base interval for syncing in minutes
            max_post_age_days: Maximum age of posts to sync (default: 30 days)
            enabled: Whether scheduler is enabled (default: True)
            ghost_api_client: Optional Ghost Content API client for post discovery
            timezone_name: IANA timezone name used for scheduler time calculations
        """
        self.sync_service = sync_service
        self.sync_interval_minutes = sync_interval_minutes
        self.max_post_age_days = max_post_age_days
        self.enabled = enabled
        self.ghost_api_client = ghost_api_client
        self.timezone_name = self._normalize_timezone_name(timezone_name)
        self.timezone = ZoneInfo(self.timezone_name)
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        # Cache for Ghost posts to reduce API calls
        self._ghost_posts_cache: Dict[str, Dict[str, Any]] = {}
        self._ghost_posts_cache_time: Optional[datetime] = None
        self._ghost_posts_cache_ttl_minutes = 60  # Cache for 1 hour

        ghost_status = "enabled" if ghost_api_client and ghost_api_client.enabled else "disabled"
        logger.info(
            f"InteractionScheduler initialized: "
            f"interval={sync_interval_minutes}min, "
            f"max_age={max_post_age_days}days, "
            f"enabled={enabled}, "
            f"ghost_api={ghost_status}, "
            f"timezone={self.timezone_name}"
        )

    @staticmethod
    def _normalize_timezone_name(timezone_name: str) -> str:
        """Return a valid timezone name, falling back to UTC."""
        if not isinstance(timezone_name, str) or not timezone_name.strip():
            return "UTC"
        candidate = timezone_name.strip()
        try:
            ZoneInfo(candidate)
        except ZoneInfoNotFoundError:
            logger.warning(f"Unknown timezone '{candidate}' for scheduler, falling back to UTC")
            return "UTC"
        return candidate

    def _now(self) -> datetime:
        """Return current datetime in scheduler timezone."""
        return datetime.now(self.timezone)

    def start(self) -> None:
        """Start the scheduler in a background thread."""
        if not self.enabled:
            logger.info("InteractionScheduler is disabled, not starting")
            return

        if self._thread and self._thread.is_alive():
            logger.warning("InteractionScheduler is already running")
            return

        logger.info("Starting InteractionScheduler")
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self, timeout: int = 30) -> None:
        """
        Stop the scheduler.

        Args:
            timeout: Maximum time to wait for scheduler to stop (seconds)
        """
        if not self._thread or not self._thread.is_alive():
            logger.info("InteractionScheduler is not running")
            return

        logger.info("Stopping InteractionScheduler")
        self._stop_event.set()
        self._thread.join(timeout=timeout)

        if self._thread.is_alive():
            logger.warning("InteractionScheduler did not stop within timeout")
        else:
            logger.info("InteractionScheduler stopped")

    def _run(self) -> None:
        """Main scheduler loop (runs in background thread)."""
        logger.info("InteractionScheduler started")

        while not self._stop_event.is_set():
            try:
                self._sync_all_posts()
            except Exception as e:
                logger.error(f"Error in scheduler sync cycle: {e}", exc_info=True)

            # Sleep for the interval (check stop event periodically)
            for _ in range(self.sync_interval_minutes * 60):
                if self._stop_event.is_set():
                    break
                time.sleep(1)

        logger.info("InteractionScheduler stopped")

    def _sync_all_posts(self) -> None:
        """
        Sync interactions for all posts with syndication mappings.

        If a Ghost API client is configured, uses the Ghost Content API to
        discover recent posts and validates that posts still exist in Ghost
        before syncing.

        Uses a smart strategy that syncs posts based on age:
        - Posts < 2 days old: sync every cycle (most active period)
        - Posts 2-7 days old: sync every other cycle
        - Posts 7-30 days old: sync every 4th cycle
        - Posts > max_post_age_days: skip
        """
        mappings = InteractionDataStore(self.sync_service.storage_path).list_syndication_mappings()
        if not mappings:
            logger.debug("No syndication mappings found")
            return

        logger.info(f"Found {len(mappings)} posts with syndication mappings")

        # If Ghost API is available, refresh the posts cache
        ghost_posts = self._get_ghost_posts_cache()
        if ghost_posts:
            logger.debug(f"Ghost API returned {len(ghost_posts)} recent posts")

        # Track sync statistics
        synced = 0
        skipped = 0
        skipped_not_in_ghost = 0
        failed = 0

        for mapping in mappings:
            ghost_post_id = str(mapping.get("ghost_post_id", ""))
            if not ghost_post_id:
                logger.warning("Skipping syndication mapping with missing ghost_post_id")
                failed += 1
                continue

            try:
                # If Ghost API is available, check if post still exists in Ghost
                if ghost_posts:
                    if not self._is_post_in_ghost(ghost_post_id, mapping, ghost_posts):
                        logger.debug(
                            f"Skipping {ghost_post_id}: not found in recent Ghost posts"
                        )
                        skipped_not_in_ghost += 1
                        continue

                    # Use Ghost post data for more accurate age calculation
                    post_age_days = self._get_post_age_from_ghost(ghost_post_id, mapping, ghost_posts)
                else:
                    # Fall back to syndication timestamp for age
                    post_age_days = self._get_post_age_days(mapping)

                # Check if post is too old
                if post_age_days > self.max_post_age_days:
                    logger.debug(
                        f"Skipping {ghost_post_id}: too old ({post_age_days:.1f} days)"
                    )
                    skipped += 1
                    continue

                # Apply smart sync strategy based on age
                if not self._should_sync_now(post_age_days):
                    logger.debug(
                        f"Skipping {ghost_post_id}: not due for sync "
                        f"(age={post_age_days:.1f} days)"
                    )
                    skipped += 1
                    continue

                # Sync interactions
                logger.debug(f"Syncing interactions for {ghost_post_id}")
                self.sync_service.sync_post_interactions(ghost_post_id)
                synced += 1

            except Exception as e:
                logger.error(
                    f"Failed to sync interactions for {ghost_post_id}: {e}",
                    exc_info=True
                )
                failed += 1

        log_msg = f"Sync cycle complete: synced={synced}, skipped={skipped}, failed={failed}"
        if ghost_posts:
            log_msg += f", not_in_ghost={skipped_not_in_ghost}"
        logger.info(log_msg)

    def _get_post_age_days(self, mapping: dict) -> float:
        """
        Calculate post age in days from syndication timestamp.

        Args:
            mapping: Syndication mapping dictionary

        Returns:
            Age of post in days (fractional)
        """
        try:
            syndicated_at_str = mapping.get("syndicated_at", "")
            if not syndicated_at_str:
                # If no timestamp, assume it's recent
                return 0.0

            syndicated_at = datetime.fromisoformat(syndicated_at_str.replace('Z', '+00:00'))
            now = self._now()
            age = now - syndicated_at
            return age.total_seconds() / 86400  # Convert to days

        except Exception as e:
            logger.error(f"Failed to calculate post age: {e}")
            return 0.0  # Assume recent if we can't determine age

    def _should_sync_now(self, post_age_days: float) -> bool:
        """
        Determine if a post should be synced in this cycle based on its age.

        Strategy:
        - Posts < 2 days old: sync every cycle (most engagement)
        - Posts 2-7 days old: sync every 2nd cycle (moderate engagement)
        - Posts 7-30 days old: sync every 4th cycle (low engagement)

        Uses a deterministic approach based on current time to ensure
        posts eventually get synced even if scheduler restarts.

        Args:
            post_age_days: Age of post in days

        Returns:
            True if post should be synced in this cycle
        """
        if post_age_days < 2:
            # Sync every cycle for recent posts
            return True
        elif post_age_days < 7:
            # Sync every 2nd cycle for posts 2-7 days old
            # Use hour of day to determine if we should sync
            return self._now().hour % 2 == 0
        else:
            # Sync every 4th cycle for posts 7-30 days old
            # Use hour of day to determine if we should sync
            return self._now().hour % 4 == 0

    def trigger_manual_sync(self, ghost_post_id: str) -> None:
        """
        Manually trigger a sync for a specific post (bypasses age checks).

        Args:
            ghost_post_id: Ghost post ID to sync

        Example:
            >>> scheduler.trigger_manual_sync("abc123")
        """
        logger.info(f"Manual sync triggered for post: {ghost_post_id}")
        try:
            self.sync_service.sync_post_interactions(ghost_post_id)
            logger.info(f"Manual sync completed for post: {ghost_post_id}")
        except Exception as e:
            logger.error(f"Manual sync failed for post {ghost_post_id}: {e}", exc_info=True)

    def _get_ghost_posts_cache(self) -> Dict[str, Dict[str, Any]]:
        """
        Get cached Ghost posts, refreshing if necessary.

        Returns a dictionary mapping post IDs to post data for quick lookup.

        Returns:
            Dictionary mapping ghost post IDs to post data
        """
        if not self.ghost_api_client or not self.ghost_api_client.enabled:
            return {}

        now = self._now()

        # Check if cache is still valid
        if (self._ghost_posts_cache_time and
            (now - self._ghost_posts_cache_time).total_seconds() < self._ghost_posts_cache_ttl_minutes * 60):
            return self._ghost_posts_cache

        # Refresh cache from Ghost API
        try:
            posts = self.ghost_api_client.get_recent_posts(
                max_age_days=self.max_post_age_days,
                max_posts=200
            )

            # Build lookup dictionary by ID and slug
            self._ghost_posts_cache = {}
            for post in posts:
                post_id = post.get("id")
                post_slug = post.get("slug")
                post_url = post.get("url", "")

                if post_id:
                    self._ghost_posts_cache[post_id] = post
                if post_slug:
                    # Also index by slug for legacy mappings
                    self._ghost_posts_cache[f"slug:{post_slug}"] = post
                # Also index by URL for URL-based lookups
                if post_url:
                    self._ghost_posts_cache[f"url:{post_url}"] = post

            self._ghost_posts_cache_time = now
            logger.debug(f"Refreshed Ghost posts cache with {len(posts)} posts")

        except Exception as e:
            logger.error(f"Failed to refresh Ghost posts cache: {e}")
            # Return existing cache if refresh failed
            pass

        return self._ghost_posts_cache

    def _is_post_in_ghost(
        self,
        ghost_post_id: str,
        mapping: Dict[str, Any],
        ghost_posts: Dict[str, Dict[str, Any]]
    ) -> bool:
        """
        Check if a post exists in the Ghost posts cache.

        Attempts to match by:
        1. Direct post ID
        2. Post URL from mapping
        3. Slug extracted from URL

        Args:
            ghost_post_id: Ghost post ID from syndication mapping
            mapping: Syndication mapping data
            ghost_posts: Ghost posts cache dictionary

        Returns:
            True if post is found in Ghost, False otherwise
        """
        # Check by direct ID
        if ghost_post_id in ghost_posts:
            return True

        # Check by URL
        ghost_post_url = mapping.get("ghost_post_url", "")
        if ghost_post_url and f"url:{ghost_post_url}" in ghost_posts:
            return True

        # Check by slug extracted from URL
        if ghost_post_url:
            # Extract slug from URL: https://blog.com/my-post-slug/ -> my-post-slug
            slug = ghost_post_url.rstrip('/').split('/')[-1]
            if slug and f"slug:{slug}" in ghost_posts:
                return True

        return False

    def _get_post_age_from_ghost(
        self,
        ghost_post_id: str,
        mapping: Dict[str, Any],
        ghost_posts: Dict[str, Dict[str, Any]]
    ) -> float:
        """
        Get post age from Ghost API data.

        Attempts to find the post in the Ghost cache and return its age
        based on the published_at timestamp.

        Args:
            ghost_post_id: Ghost post ID
            mapping: Syndication mapping data
            ghost_posts: Ghost posts cache dictionary

        Returns:
            Age of post in days, or fallback to syndication timestamp age
        """
        ghost_post = None

        # Try to find by direct ID
        if ghost_post_id in ghost_posts:
            ghost_post = ghost_posts[ghost_post_id]

        # Try by URL
        if not ghost_post:
            ghost_post_url = mapping.get("ghost_post_url", "")
            if ghost_post_url and f"url:{ghost_post_url}" in ghost_posts:
                ghost_post = ghost_posts[f"url:{ghost_post_url}"]

        # Try by slug
        if not ghost_post and mapping.get("ghost_post_url"):
            slug = mapping["ghost_post_url"].rstrip('/').split('/')[-1]
            if slug and f"slug:{slug}" in ghost_posts:
                ghost_post = ghost_posts[f"slug:{slug}"]

        if ghost_post and ghost_post.get("published_at"):
            try:
                published_at_str = ghost_post["published_at"]
                published_at = datetime.fromisoformat(published_at_str.replace('Z', '+00:00'))
                now = self._now()
                age = now - published_at
                return age.total_seconds() / 86400
            except Exception as e:
                logger.debug(f"Failed to parse Ghost published_at: {e}")

        # Fall back to syndication timestamp
        return self._get_post_age_days(mapping)
