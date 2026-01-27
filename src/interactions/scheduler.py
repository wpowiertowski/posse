"""
Interaction Sync Scheduler for POSSE.

This module provides a background scheduler that periodically syncs
interactions for syndicated posts.
"""
import logging
import os
import json
import threading
import time
from typing import Optional, List
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from interactions.interaction_sync import InteractionSyncService

logger = logging.getLogger(__name__)


class InteractionScheduler:
    """
    Scheduler for periodically syncing social media interactions.

    This scheduler runs in a background thread and syncs interactions
    for all posts with syndication mappings, using a smart strategy
    that syncs recent posts more frequently.

    Attributes:
        sync_service: InteractionSyncService instance
        sync_interval_minutes: Base sync interval in minutes
        max_post_age_days: Maximum age of posts to sync (in days)
        enabled: Whether the scheduler is enabled
    """

    def __init__(
        self,
        sync_service: InteractionSyncService,
        sync_interval_minutes: int = 30,
        max_post_age_days: int = 30,
        enabled: bool = True
    ):
        """
        Initialize the interaction scheduler.

        Args:
            sync_service: InteractionSyncService instance
            sync_interval_minutes: Base interval for syncing in minutes
            max_post_age_days: Maximum age of posts to sync (default: 30 days)
            enabled: Whether scheduler is enabled (default: True)
        """
        self.sync_service = sync_service
        self.sync_interval_minutes = sync_interval_minutes
        self.max_post_age_days = max_post_age_days
        self.enabled = enabled
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

        logger.info(
            f"InteractionScheduler initialized: "
            f"interval={sync_interval_minutes}min, "
            f"max_age={max_post_age_days}days, "
            f"enabled={enabled}"
        )

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

        Uses a smart strategy that syncs posts based on age:
        - Posts < 2 days old: sync every cycle (most active period)
        - Posts 2-7 days old: sync every other cycle
        - Posts 7-30 days old: sync every 4th cycle
        - Posts > max_post_age_days: skip
        """
        mappings_path = self.sync_service.mappings_path

        if not os.path.exists(mappings_path):
            logger.debug(f"Mappings directory does not exist: {mappings_path}")
            return

        # Get all mapping files
        mapping_files = [
            f for f in os.listdir(mappings_path)
            if f.endswith('.json')
        ]

        if not mapping_files:
            logger.debug("No syndication mappings found")
            return

        logger.info(f"Found {len(mapping_files)} posts with syndication mappings")

        # Track sync statistics
        synced = 0
        skipped = 0
        failed = 0

        for mapping_file in mapping_files:
            ghost_post_id = mapping_file.replace('.json', '')

            try:
                # Load mapping to check age
                mapping = self._load_mapping(os.path.join(mappings_path, mapping_file))
                if not mapping:
                    logger.warning(f"Could not load mapping for {ghost_post_id}")
                    failed += 1
                    continue

                # Check if post is too old
                post_age_days = self._get_post_age_days(mapping)
                if post_age_days > self.max_post_age_days:
                    logger.debug(
                        f"Skipping {ghost_post_id}: too old ({post_age_days} days)"
                    )
                    skipped += 1
                    continue

                # Apply smart sync strategy based on age
                if not self._should_sync_now(post_age_days):
                    logger.debug(
                        f"Skipping {ghost_post_id}: not due for sync "
                        f"(age={post_age_days} days)"
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

        logger.info(
            f"Sync cycle complete: synced={synced}, skipped={skipped}, failed={failed}"
        )

    def _load_mapping(self, mapping_file: str) -> Optional[dict]:
        """Load a syndication mapping file."""
        try:
            with open(mapping_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load mapping {mapping_file}: {e}")
            return None

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
            now = datetime.now(ZoneInfo("UTC"))
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
            return datetime.now(ZoneInfo("UTC")).hour % 2 == 0
        else:
            # Sync every 4th cycle for posts 7-30 days old
            # Use hour of day to determine if we should sync
            return datetime.now(ZoneInfo("UTC")).hour % 4 == 0

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
