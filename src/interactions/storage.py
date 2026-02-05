"""SQLite-backed storage for syndicated interaction data."""

from __future__ import annotations

import json
import logging
import os
import sqlite3
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class InteractionDataStore:
    """Persistent interaction storage with SQLite primary and JSON fallback."""

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
        except sqlite3.Error as e:
            logger.error(f"Failed to initialize interactions database {self.db_path}: {e}")

    def get(self, ghost_post_id: str) -> Optional[Dict[str, Any]]:
        """Get interaction payload by post ID, with legacy JSON fallback."""
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

        return self._read_legacy_json(ghost_post_id)

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
        """Check whether interaction data exists in SQLite or legacy JSON storage."""
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

        legacy_file = os.path.join(self.storage_path, f"{ghost_post_id}.json")
        return os.path.exists(legacy_file)

    def _read_legacy_json(self, ghost_post_id: str) -> Optional[Dict[str, Any]]:
        """Read data from legacy per-post JSON file and backfill into SQLite."""
        interaction_file = os.path.join(self.storage_path, f"{ghost_post_id}.json")
        if not os.path.exists(interaction_file):
            return None

        try:
            with open(interaction_file, "r") as f:
                payload = json.load(f)

            self.put(ghost_post_id, payload)
            return payload
        except (OSError, json.JSONDecodeError) as e:
            logger.error(f"Failed to read legacy interaction JSON {interaction_file}: {e}")
            return None
