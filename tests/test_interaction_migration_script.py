import json
import sqlite3
import subprocess
import sys


def test_migration_script_moves_json_to_sqlite(tmp_path):
    post_id = "507f1f77bcf86cd799439012"
    payload = {
        "ghost_post_id": post_id,
        "updated_at": "2026-01-01T00:00:00Z",
        "platforms": {"mastodon": {}, "bluesky": {}},
        "syndication_links": {"mastodon": {}, "bluesky": {}},
    }
    (tmp_path / f"{post_id}.json").write_text(json.dumps(payload))

    result = subprocess.run(
        [
            sys.executable,
            "scripts/migrate_interactions_to_sqlite.py",
            "--storage-path",
            str(tmp_path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )

    assert "Migrated: 1" in result.stdout

    conn = sqlite3.connect(tmp_path / "interactions.db")
    row = conn.execute(
        "SELECT payload FROM interaction_data WHERE ghost_post_id = ?",
        (post_id,),
    ).fetchone()
    conn.close()

    assert row is not None
    assert json.loads(row[0])["ghost_post_id"] == post_id


def test_migration_script_skips_invalid_payloads(tmp_path):
    valid_id = "507f1f77bcf86cd799439013"
    valid_payload = {
        "ghost_post_id": valid_id,
        "updated_at": "2026-01-01T00:00:00Z",
        "platforms": {"mastodon": {}, "bluesky": {}},
        "syndication_links": {"mastodon": {}, "bluesky": {}},
    }
    invalid_payload = {
                "updated_at": "2026-01-01T00:00:00Z",
        "platforms": {"mastodon": {}, "bluesky": {}},
    }

    (tmp_path / f"{valid_id}.json").write_text(json.dumps(valid_payload))
    (tmp_path / "invalid.json").write_text(json.dumps(invalid_payload))

    result = subprocess.run(
        [
            sys.executable,
            "scripts/migrate_interactions_to_sqlite.py",
            "--storage-path",
            str(tmp_path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )

    assert "Migrated: 1" in result.stdout
    assert "Skipped: 1" in result.stdout

    conn = sqlite3.connect(tmp_path / "interactions.db")
    rows = conn.execute("SELECT ghost_post_id FROM interaction_data").fetchall()
    conn.close()

    assert rows == [(valid_id,)]
