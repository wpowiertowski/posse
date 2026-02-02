"""
Interaction Sync Scheduler for POSSE.

This module provides an event-driven scheduler that syncs interactions
for syndicated posts based on push events rather than interval polling.

Event Types:
    - SYNC_POST: Sync a specific post immediately
    - SYNC_ALL: Sync all eligible posts (respects age-based strategy)
    - SHUTDOWN: Gracefully stop the scheduler

Events can be pushed from:
    - Post syndication (immediate sync after publishing)
    - Manual API triggers
    - Optional heartbeat for periodic sync (configurable)
"""
import logging
import os
import json
import threading
import time
from queue import Queue, Empty
from typing import Optional, Dict, Any
from dataclasses import dataclass
from enum import Enum
from datetime import datetime
from zoneinfo import ZoneInfo

from interactions.interaction_sync import InteractionSyncService

logger = logging.getLogger(__name__)


class InteractionEventType(Enum):
    """Types of interaction sync events."""
    SYNC_POST = "sync_post"      # Sync a specific post
    SYNC_ALL = "sync_all"        # Sync all eligible posts
    SHUTDOWN = "shutdown"        # Stop the scheduler


@dataclass
class InteractionEvent:
    """Event for the interaction sync queue.

    Attributes:
        event_type: Type of event (SYNC_POST, SYNC_ALL, SHUTDOWN)
        ghost_post_id: Optional post ID for SYNC_POST events
        priority: Event priority (lower = higher priority, default 5)
        metadata: Optional additional data for the event
    """
    event_type: InteractionEventType
    ghost_post_id: Optional[str] = None
    priority: int = 5
    metadata: Optional[Dict[str, Any]] = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class InteractionScheduler:
    """
    Event-driven scheduler for syncing social media interactions.

    This scheduler uses a push-based event queue instead of interval polling.
    Events are pushed to the queue from:
    - Post syndication (automatic sync after publishing)
    - Manual API triggers
    - Optional heartbeat thread for periodic sync

    Attributes:
        sync_service: InteractionSyncService instance
        max_post_age_days: Maximum age of posts to sync (in days)
        enabled: Whether the scheduler is enabled
        heartbeat_interval_minutes: Interval for heartbeat (0 to disable)
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
            sync_interval_minutes: Interval for heartbeat sync in minutes (0 to disable)
            max_post_age_days: Maximum age of posts to sync (default: 30 days)
            enabled: Whether scheduler is enabled (default: True)
        """
        self.sync_service = sync_service
        self.heartbeat_interval_minutes = sync_interval_minutes
        self.max_post_age_days = max_post_age_days
        self.enabled = enabled

        # Event queue for push-based sync
        self._events_queue: Queue[InteractionEvent] = Queue()
        self._stop_event = threading.Event()
        self._worker_thread: Optional[threading.Thread] = None
        self._heartbeat_thread: Optional[threading.Thread] = None

        logger.info(
            f"InteractionScheduler initialized: "
            f"heartbeat_interval={sync_interval_minutes}min, "
            f"max_age={max_post_age_days}days, "
            f"enabled={enabled}"
        )

    def start(self) -> None:
        """Start the scheduler worker and optional heartbeat threads."""
        if not self.enabled:
            logger.info("InteractionScheduler is disabled, not starting")
            return

        if self._worker_thread and self._worker_thread.is_alive():
            logger.warning("InteractionScheduler is already running")
            return

        logger.info("Starting InteractionScheduler (event-driven mode)")
        self._stop_event.clear()

        # Start the worker thread that processes events
        self._worker_thread = threading.Thread(
            target=self._event_worker,
            daemon=True,
            name="interaction-sync-worker"
        )
        self._worker_thread.start()

        # Start optional heartbeat thread for periodic sync
        if self.heartbeat_interval_minutes > 0:
            self._heartbeat_thread = threading.Thread(
                target=self._heartbeat_worker,
                daemon=True,
                name="interaction-sync-heartbeat"
            )
            self._heartbeat_thread.start()
            logger.info(
                f"Heartbeat thread started: interval={self.heartbeat_interval_minutes}min"
            )
        else:
            logger.info("Heartbeat disabled (interval=0)")

    def stop(self, timeout: int = 30) -> None:
        """
        Stop the scheduler gracefully.

        Args:
            timeout: Maximum time to wait for scheduler to stop (seconds)
        """
        if not self._worker_thread or not self._worker_thread.is_alive():
            logger.info("InteractionScheduler is not running")
            return

        logger.info("Stopping InteractionScheduler")

        # Push shutdown event to the queue
        self.push_event(InteractionEvent(
            event_type=InteractionEventType.SHUTDOWN,
            priority=0  # Highest priority
        ))

        self._stop_event.set()

        # Wait for threads to finish
        if self._worker_thread:
            self._worker_thread.join(timeout=timeout)
        if self._heartbeat_thread:
            self._heartbeat_thread.join(timeout=5)

        if self._worker_thread and self._worker_thread.is_alive():
            logger.warning("InteractionScheduler worker did not stop within timeout")
        else:
            logger.info("InteractionScheduler stopped")

    def push_event(self, event: InteractionEvent) -> None:
        """
        Push an event to the sync queue.

        This is the main method for triggering syncs from external sources.

        Args:
            event: InteractionEvent to process

        Example:
            >>> scheduler.push_event(InteractionEvent(
            ...     event_type=InteractionEventType.SYNC_POST,
            ...     ghost_post_id="abc123"
            ... ))
        """
        if not self.enabled:
            logger.debug(f"Scheduler disabled, ignoring event: {event.event_type}")
            return

        logger.debug(f"Pushing event to queue: {event.event_type.value}")
        self._events_queue.put(event)

    def push_sync_post(self, ghost_post_id: str, priority: int = 5, metadata: Optional[Dict[str, Any]] = None) -> None:
        """
        Convenience method to push a sync event for a specific post.

        Args:
            ghost_post_id: Ghost post ID to sync
            priority: Event priority (lower = higher, default 5)
            metadata: Optional metadata (e.g., source of trigger)

        Example:
            >>> scheduler.push_sync_post("abc123", priority=1, metadata={"source": "syndication"})
        """
        event = InteractionEvent(
            event_type=InteractionEventType.SYNC_POST,
            ghost_post_id=ghost_post_id,
            priority=priority,
            metadata=metadata or {}
        )
        self.push_event(event)
        logger.info(f"Queued sync event for post: {ghost_post_id}")

    def push_sync_all(self, priority: int = 10) -> None:
        """
        Convenience method to push a sync-all event.

        Args:
            priority: Event priority (default 10, lower than individual syncs)

        Example:
            >>> scheduler.push_sync_all()
        """
        event = InteractionEvent(
            event_type=InteractionEventType.SYNC_ALL,
            priority=priority
        )
        self.push_event(event)
        logger.debug("Queued sync-all event")

    def trigger_manual_sync(self, ghost_post_id: str) -> None:
        """
        Manually trigger a sync for a specific post (bypasses age checks).

        This method maintains backward compatibility with the previous API
        while using the new event-driven architecture.

        Args:
            ghost_post_id: Ghost post ID to sync

        Example:
            >>> scheduler.trigger_manual_sync("abc123")
        """
        logger.info(f"Manual sync triggered for post: {ghost_post_id}")
        self.push_sync_post(
            ghost_post_id,
            priority=1,  # High priority for manual triggers
            metadata={"source": "manual", "bypass_age_check": True}
        )

    def _event_worker(self) -> None:
        """Main event worker loop (runs in background thread)."""
        logger.info("InteractionScheduler event worker started")

        while not self._stop_event.is_set():
            try:
                # Block waiting for events with timeout to check stop event
                try:
                    event = self._events_queue.get(timeout=1.0)
                except Empty:
                    continue

                # Handle shutdown event
                if event.event_type == InteractionEventType.SHUTDOWN:
                    logger.info("Received shutdown event")
                    self._events_queue.task_done()
                    break

                # Process the event
                self._process_event(event)
                self._events_queue.task_done()

            except Exception as e:
                logger.error(f"Error in event worker: {e}", exc_info=True)

        logger.info("InteractionScheduler event worker stopped")

    def _heartbeat_worker(self) -> None:
        """Heartbeat thread that pushes periodic sync-all events."""
        logger.info("InteractionScheduler heartbeat worker started")

        # Initial delay before first heartbeat
        initial_delay_seconds = 60  # 1 minute initial delay
        for _ in range(initial_delay_seconds):
            if self._stop_event.is_set():
                break
            time.sleep(1)

        while not self._stop_event.is_set():
            try:
                # Push a sync-all event
                self.push_sync_all(priority=10)
                logger.debug("Heartbeat: pushed sync-all event")

            except Exception as e:
                logger.error(f"Error in heartbeat worker: {e}", exc_info=True)

            # Sleep for the interval (check stop event periodically)
            for _ in range(self.heartbeat_interval_minutes * 60):
                if self._stop_event.is_set():
                    break
                time.sleep(1)

        logger.info("InteractionScheduler heartbeat worker stopped")

    def _process_event(self, event: InteractionEvent) -> None:
        """
        Process a single sync event.

        Args:
            event: InteractionEvent to process
        """
        logger.debug(f"Processing event: {event.event_type.value}")

        try:
            if event.event_type == InteractionEventType.SYNC_POST:
                self._handle_sync_post(event)
            elif event.event_type == InteractionEventType.SYNC_ALL:
                self._handle_sync_all(event)
            else:
                logger.warning(f"Unknown event type: {event.event_type}")

        except Exception as e:
            logger.error(
                f"Error processing event {event.event_type.value}: {e}",
                exc_info=True
            )

    def _handle_sync_post(self, event: InteractionEvent) -> None:
        """
        Handle a sync-post event.

        Args:
            event: SYNC_POST event with ghost_post_id
        """
        ghost_post_id = event.ghost_post_id
        if not ghost_post_id:
            logger.warning("SYNC_POST event missing ghost_post_id")
            return

        # Check if we should bypass age check (for manual triggers)
        bypass_age_check = event.metadata.get("bypass_age_check", False)

        if not bypass_age_check:
            # Load mapping to check age
            mapping_file = os.path.join(
                self.sync_service.mappings_path,
                f"{ghost_post_id}.json"
            )
            if os.path.exists(mapping_file):
                mapping = self._load_mapping(mapping_file)
                if mapping:
                    post_age_days = self._get_post_age_days(mapping)
                    if post_age_days > self.max_post_age_days:
                        logger.debug(
                            f"Skipping {ghost_post_id}: too old ({post_age_days:.1f} days)"
                        )
                        return

        # Sync the post
        logger.info(f"Syncing interactions for post: {ghost_post_id}")
        try:
            self.sync_service.sync_post_interactions(ghost_post_id)
            logger.info(f"Successfully synced interactions for: {ghost_post_id}")
        except Exception as e:
            logger.error(f"Failed to sync {ghost_post_id}: {e}", exc_info=True)

    def _handle_sync_all(self, event: InteractionEvent) -> None:
        """
        Handle a sync-all event.

        Syncs all posts with syndication mappings, respecting age-based strategy.

        Args:
            event: SYNC_ALL event
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

        logger.info(f"Sync-all: found {len(mapping_files)} posts with mappings")

        # Track sync statistics
        synced = 0
        skipped = 0
        failed = 0

        for mapping_file in mapping_files:
            ghost_post_id = mapping_file.replace('.json', '')

            try:
                # Load mapping to check age
                mapping = self._load_mapping(
                    os.path.join(mappings_path, mapping_file)
                )
                if not mapping:
                    logger.warning(f"Could not load mapping for {ghost_post_id}")
                    failed += 1
                    continue

                # Check if post is too old
                post_age_days = self._get_post_age_days(mapping)
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

        logger.info(
            f"Sync-all complete: synced={synced}, skipped={skipped}, failed={failed}"
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

            syndicated_at = datetime.fromisoformat(
                syndicated_at_str.replace('Z', '+00:00')
            )
            now = datetime.now(ZoneInfo("UTC"))
            age = now - syndicated_at
            return age.total_seconds() / 86400  # Convert to days

        except Exception as e:
            logger.error(f"Failed to calculate post age: {e}")
            return 0.0  # Assume recent if we can't determine age

    def _should_sync_now(self, post_age_days: float) -> bool:
        """
        Determine if a post should be synced based on its age.

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
            return datetime.now(ZoneInfo("UTC")).hour % 2 == 0
        else:
            # Sync every 4th cycle for posts 7-30 days old
            return datetime.now(ZoneInfo("UTC")).hour % 4 == 0

    def get_queue_size(self) -> int:
        """
        Get the current number of events in the queue.

        Useful for monitoring and debugging.

        Returns:
            Number of pending events
        """
        return self._events_queue.qsize()

    def is_running(self) -> bool:
        """
        Check if the scheduler is currently running.

        Returns:
            True if worker thread is alive
        """
        return (
            self._worker_thread is not None
            and self._worker_thread.is_alive()
        )
