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
