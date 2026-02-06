import json
import subprocess
import sys

from interactions.storage import InteractionDataStore


def test_consistency_script_passes_for_matching_json_and_db(tmp_path):
    ghost_post_id = "507f1f77bcf86cd799439120"
    mappings_path = tmp_path / "syndication_mappings"
    storage_path = tmp_path / "interactions"
    mappings_path.mkdir()
    storage_path.mkdir()

    mapping = {
        "ghost_post_id": ghost_post_id,
        "ghost_post_url": "https://blog.example.com/post/",
        "syndicated_at": "2026-01-01T00:00:00Z",
        "platforms": {
            "mastodon": {
                "personal": {
                    "status_id": "42",
                    "post_url": "https://mastodon.social/@user/42",
                }
            }
        },
    }

    (mappings_path / f"{ghost_post_id}.json").write_text(json.dumps(mapping))
    store = InteractionDataStore(str(storage_path))
    store.put_syndication_mapping(ghost_post_id, mapping)

    result = subprocess.run(
        [
            sys.executable,
            "scripts/validate_syndication_mapping_consistency.py",
            "--mappings-path",
            str(mappings_path),
            "--storage-path",
            str(storage_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "Consistency check passed" in result.stdout


def test_consistency_script_fails_on_mismatch(tmp_path):
    ghost_post_id = "507f1f77bcf86cd799439121"
    mappings_path = tmp_path / "syndication_mappings"
    storage_path = tmp_path / "interactions"
    mappings_path.mkdir()
    storage_path.mkdir()

    json_mapping = {
        "ghost_post_id": ghost_post_id,
        "ghost_post_url": "https://blog.example.com/post/",
        "syndicated_at": "2026-01-01T00:00:00Z",
        "platforms": {
            "mastodon": {
                "personal": {
                    "status_id": "42",
                    "post_url": "https://mastodon.social/@user/42",
                }
            }
        },
    }

    db_mapping = {
        **json_mapping,
        "platforms": {
            "mastodon": {
                "personal": {
                    "status_id": "43",
                    "post_url": "https://mastodon.social/@user/43",
                }
            }
        },
    }

    (mappings_path / f"{ghost_post_id}.json").write_text(json.dumps(json_mapping))
    store = InteractionDataStore(str(storage_path))
    store.put_syndication_mapping(ghost_post_id, db_mapping)

    result = subprocess.run(
        [
            sys.executable,
            "scripts/validate_syndication_mapping_consistency.py",
            "--mappings-path",
            str(mappings_path),
            "--storage-path",
            str(storage_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    assert "Payload mismatch" in result.stdout
