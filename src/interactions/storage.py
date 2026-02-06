"""SQLite-backed storage for syndicated interaction data."""

from __future__ import annotations

import json
import logging
import os
import sqlite3
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


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
