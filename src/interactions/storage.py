"""SQLite-backed storage for syndicated interaction data."""

from __future__ import annotations

import json
import logging
import os
import sqlite3
from typing import Any, Dict, Optional

from jsonschema import ValidationError, validate
from schema import INTERACTION_DATA_PAYLOAD_SCHEMA, SYNDICATION_MAPPING_PAYLOAD_SCHEMA

logger = logging.getLogger(__name__)


def _normalize_interaction_payload(data: Dict[str, Any]) -> Dict[str, Any]:
    normalized = dict(data)
    platforms = normalized.get("platforms")
    if not isinstance(platforms, dict):
        platforms = {}
    normalized["platforms"] = {
        "mastodon": platforms.get("mastodon", {}),
        "bluesky": platforms.get("bluesky", {}),
    }

    links = normalized.get("syndication_links")
    if not isinstance(links, dict):
        links = {}
    normalized["syndication_links"] = {
        "mastodon": links.get("mastodon", {}),
        "bluesky": links.get("bluesky", {}),
    }
    return normalized


def _normalize_syndication_mapping_payload(mapping: Dict[str, Any]) -> Dict[str, Any]:
    normalized = dict(mapping)
    platforms = normalized.get("platforms")
    if not isinstance(platforms, dict):
        platforms = {}
    normalized["platforms"] = {
        "mastodon": platforms.get("mastodon", {}),
        "bluesky": platforms.get("bluesky", {}),
    }
    return normalized


class InteractionDataStore:
    """Persistent interaction storage backed by SQLite."""

    def __init__(self, storage_path: str):
        self.storage_path = storage_path
        os.makedirs(self.storage_path, mode=0o755, exist_ok=True)
        self.db_path = os.path.join(self.storage_path, "interactions.db")
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self) -> None:
        try:
            with self._connect() as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS interaction_data (
                        ghost_post_id TEXT PRIMARY KEY,
                        payload TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    )
                    """
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_interaction_updated_at "
                    "ON interaction_data(updated_at)"
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS syndication_mappings (
                        ghost_post_id TEXT PRIMARY KEY,
                        payload TEXT NOT NULL,
                        syndicated_at TEXT NOT NULL
                    )
                    """
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_syndication_syndicated_at "
                    "ON syndication_mappings(syndicated_at)"
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS webmention_replies (
                        id TEXT PRIMARY KEY,
                        author_name TEXT NOT NULL,
                        author_url TEXT,
                        content TEXT NOT NULL,
                        target TEXT NOT NULL,
                        ip_hash TEXT,
                        created_at TEXT NOT NULL
                    )
                    """
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_replies_target "
                    "ON webmention_replies(target)"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_replies_created_at "
                    "ON webmention_replies(created_at)"
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS sent_webmentions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        source_url TEXT NOT NULL,
                        target_url TEXT NOT NULL,
                        post_id TEXT,
                        endpoint TEXT,
                        sent_at TEXT NOT NULL,
                        UNIQUE(source_url, target_url)
                    )
                    """
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_sent_wm_source "
                    "ON sent_webmentions(source_url)"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_sent_wm_post_id "
                    "ON sent_webmentions(post_id)"
                )
        except sqlite3.Error as e:
            logger.error(f"Failed to initialize interactions database {self.db_path}: {e}")

    def get(self, ghost_post_id: str) -> Optional[Dict[str, Any]]:
        """Get interaction payload by post ID from SQLite."""
        try:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT payload FROM interaction_data WHERE ghost_post_id = ?",
                    (ghost_post_id,),
                ).fetchone()
                if row:
                    return json.loads(row["payload"])
        except (sqlite3.Error, json.JSONDecodeError) as e:
            logger.error(f"Failed to read interaction data for {ghost_post_id} from SQLite: {e}")

        return None

    def put(self, ghost_post_id: str, data: Dict[str, Any]) -> None:
        """Upsert interaction payload by post ID."""
        data = _normalize_interaction_payload(data)
        try:
            validate(instance=data, schema=INTERACTION_DATA_PAYLOAD_SCHEMA)
        except ValidationError as e:
            logger.error(f"Invalid interaction payload for {ghost_post_id}: {e.message}")
            return

        updated_at = str(data.get("updated_at", ""))
        payload = json.dumps(data)

        try:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO interaction_data (ghost_post_id, payload, updated_at)
                    VALUES (?, ?, ?)
                    ON CONFLICT(ghost_post_id) DO UPDATE SET
                        payload = excluded.payload,
                        updated_at = excluded.updated_at
                    """,
                    (ghost_post_id, payload, updated_at),
                )
        except sqlite3.Error as e:
            logger.error(f"Failed to store interaction data for {ghost_post_id} in SQLite: {e}")

    def exists(self, ghost_post_id: str) -> bool:
        """Check whether interaction data exists in SQLite."""
        try:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT 1 FROM interaction_data WHERE ghost_post_id = ?",
                    (ghost_post_id,),
                ).fetchone()
                if row:
                    return True
        except sqlite3.Error as e:
            logger.error(f"Failed to check interaction data existence for {ghost_post_id}: {e}")

        return False

    def get_syndication_mapping(self, ghost_post_id: str) -> Optional[Dict[str, Any]]:
        """Get syndication mapping by post ID from SQLite."""
        try:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT payload FROM syndication_mappings WHERE ghost_post_id = ?",
                    (ghost_post_id,),
                ).fetchone()
                if row:
                    return json.loads(row["payload"])
        except (sqlite3.Error, json.JSONDecodeError) as e:
            logger.error(
                f"Failed to read syndication mapping for {ghost_post_id} from SQLite: {e}"
            )

        return None

    def put_syndication_mapping(self, ghost_post_id: str, mapping: Dict[str, Any]) -> None:
        """Upsert syndication mapping by post ID."""
        mapping = _normalize_syndication_mapping_payload(mapping)
        try:
            validate(instance=mapping, schema=SYNDICATION_MAPPING_PAYLOAD_SCHEMA)
        except ValidationError as e:
            logger.error(f"Invalid syndication mapping payload for {ghost_post_id}: {e.message}")
            return

        syndicated_at = str(mapping.get("syndicated_at", ""))
        payload = json.dumps(mapping)

        try:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO syndication_mappings (ghost_post_id, payload, syndicated_at)
                    VALUES (?, ?, ?)
                    ON CONFLICT(ghost_post_id) DO UPDATE SET
                        payload = excluded.payload,
                        syndicated_at = excluded.syndicated_at
                    """,
                    (ghost_post_id, payload, syndicated_at),
                )
        except sqlite3.Error as e:
            logger.error(
                f"Failed to store syndication mapping for {ghost_post_id} in SQLite: {e}"
            )

    def put_reply(self, reply: Dict[str, Any]) -> None:
        """Store a webmention reply."""
        try:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO webmention_replies (id, author_name, author_url, content, target, ip_hash, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        reply["id"],
                        reply["author_name"],
                        reply.get("author_url", ""),
                        reply["content"],
                        reply["target"],
                        reply.get("ip_hash", ""),
                        reply["created_at"],
                    ),
                )
        except sqlite3.Error as e:
            logger.error(f"Failed to store reply {reply.get('id')}: {e}")
            raise

    def get_reply(self, reply_id: str) -> Optional[Dict[str, Any]]:
        """Get a webmention reply by ID."""
        try:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT id, author_name, author_url, content, target, ip_hash, created_at "
                    "FROM webmention_replies WHERE id = ?",
                    (reply_id,),
                ).fetchone()
                if row:
                    return {
                        "id": row["id"],
                        "author_name": row["author_name"],
                        "author_url": row["author_url"],
                        "content": row["content"],
                        "target": row["target"],
                        "ip_hash": row["ip_hash"],
                        "created_at": row["created_at"],
                    }
        except sqlite3.Error as e:
            logger.error(f"Failed to read reply {reply_id}: {e}")
        return None

    def delete_reply(self, reply_id: str) -> bool:
        """Delete a webmention reply by ID."""
        try:
            with self._connect() as conn:
                cursor = conn.execute(
                    "DELETE FROM webmention_replies WHERE id = ?",
                    (reply_id,),
                )
                return cursor.rowcount > 0
        except sqlite3.Error as e:
            logger.error(f"Failed to delete reply {reply_id}: {e}")
            raise

    def list_syndication_mappings(self) -> list[Dict[str, Any]]:
        """Return all syndication mappings stored in SQLite."""
        mappings: list[Dict[str, Any]] = []
        try:
            with self._connect() as conn:
                rows = conn.execute(
                    "SELECT ghost_post_id, payload FROM syndication_mappings"
                ).fetchall()
            for row in rows:
                try:
                    mapping = json.loads(row["payload"])
                except json.JSONDecodeError:
                    logger.error(
                        f"Invalid syndication mapping payload JSON for {row['ghost_post_id']}"
                    )
                    continue
                mappings.append(mapping)
        except sqlite3.Error as e:
            logger.error(f"Failed to list syndication mappings from SQLite: {e}")
        return mappings

    # =====================================================================
    # Sent Webmentions tracking
    # =====================================================================

    # Maximum lengths for sent webmention fields to prevent database bloat
    _MAX_URL_LENGTH = 2048
    _MAX_POST_ID_LENGTH = 50

    def record_sent_webmention(
        self,
        source_url: str,
        target_url: str,
        post_id: str = "",
        endpoint: str = "",
        sent_at: str = "",
    ) -> None:
        """Record a successfully sent webmention.

        Upserts by (source_url, target_url) so re-sends update the timestamp.
        """
        # Validate and truncate inputs to prevent database bloat
        source_url = (source_url or "")[:self._MAX_URL_LENGTH]
        target_url = (target_url or "")[:self._MAX_URL_LENGTH]
        post_id = (post_id or "")[:self._MAX_POST_ID_LENGTH]
        endpoint = (endpoint or "")[:self._MAX_URL_LENGTH]

        if not source_url or not target_url:
            logger.warning("Skipping sent webmention record: missing source_url or target_url")
            return

        if not sent_at:
            from datetime import datetime, timezone
            sent_at = datetime.now(timezone.utc).isoformat()
        try:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO sent_webmentions (source_url, target_url, post_id, endpoint, sent_at)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(source_url, target_url) DO UPDATE SET
                        endpoint = excluded.endpoint,
                        sent_at = excluded.sent_at
                    """,
                    (source_url, target_url, post_id, endpoint, sent_at),
                )
        except sqlite3.Error as e:
            logger.error(f"Failed to record sent webmention: source={source_url}, target={target_url}: {e}")

    def get_sent_webmention_targets(self, source_url: str) -> list[str]:
        """Get all target URLs that received webmentions for a given source URL."""
        try:
            with self._connect() as conn:
                rows = conn.execute(
                    "SELECT target_url FROM sent_webmentions WHERE source_url = ?",
                    (source_url,),
                ).fetchall()
                return [row["target_url"] for row in rows]
        except sqlite3.Error as e:
            logger.error(f"Failed to list sent webmentions for {source_url}: {e}")
            return []

    def get_sent_webmention_targets_by_post_id(self, post_id: str) -> list[str]:
        """Get all target URLs that received webmentions for a given Ghost post ID."""
        try:
            with self._connect() as conn:
                rows = conn.execute(
                    "SELECT DISTINCT target_url FROM sent_webmentions WHERE post_id = ?",
                    (post_id,),
                ).fetchall()
                return [row["target_url"] for row in rows]
        except sqlite3.Error as e:
            logger.error(f"Failed to list sent webmentions for post {post_id}: {e}")
            return []

    def delete_sent_webmentions_for_post(self, post_id: str) -> int:
        """Delete all sent webmention records for a post. Returns count deleted."""
        try:
            with self._connect() as conn:
                cursor = conn.execute(
                    "DELETE FROM sent_webmentions WHERE post_id = ?",
                    (post_id,),
                )
                return cursor.rowcount
        except sqlite3.Error as e:
            logger.error(f"Failed to delete sent webmentions for post {post_id}: {e}")
            return 0
