#!/usr/bin/env python3
"""One-time migration from per-post interaction JSON files to SQLite."""

import argparse
import json
import os
import sqlite3
from pathlib import Path


def ensure_schema(conn: sqlite3.Connection) -> None:
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


def migrate(storage_path: Path, dry_run: bool = False) -> tuple[int, int]:
    db_path = storage_path / "interactions.db"
    json_files = [
        p for p in storage_path.glob("*.json")
        if p.is_file()
    ]

    if dry_run:
        migrated = 0
        skipped = 0
        for path in json_files:
            try:
                with open(path, "r") as f:
                    payload = json.load(f)
                if payload.get("ghost_post_id"):
                    migrated += 1
                else:
                    skipped += 1
            except Exception:
                skipped += 1
        return migrated, skipped

    with sqlite3.connect(db_path) as conn:
        ensure_schema(conn)
        migrated = 0
        skipped = 0

        for path in json_files:
            try:
                with open(path, "r") as f:
                    payload = json.load(f)

                ghost_post_id = payload.get("ghost_post_id") or path.stem
                updated_at = str(payload.get("updated_at", ""))
                conn.execute(
                    """
                    INSERT INTO interaction_data (ghost_post_id, payload, updated_at)
                    VALUES (?, ?, ?)
                    ON CONFLICT(ghost_post_id) DO UPDATE SET
                        payload = excluded.payload,
                        updated_at = excluded.updated_at
                    """,
                    (ghost_post_id, json.dumps(payload), updated_at),
                )
                migrated += 1
            except Exception:
                skipped += 1

    return migrated, skipped


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--storage-path",
        default="./data/interactions",
        help="Directory containing legacy interaction JSON files",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview migration counts without writing to SQLite",
    )
    args = parser.parse_args()

    storage_path = Path(args.storage_path)
    if not storage_path.exists() or not storage_path.is_dir():
        print(f"Storage path not found or not a directory: {storage_path}")
        return 1

    migrated, skipped = migrate(storage_path, dry_run=args.dry_run)
    mode = "Dry run" if args.dry_run else "Migration"
    print(f"{mode} complete. Migrated: {migrated}, Skipped: {skipped}")
    if not args.dry_run:
        print(f"SQLite database: {os.path.join(args.storage_path, 'interactions.db')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
