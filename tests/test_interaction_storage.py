import json
from pathlib import Path

from interactions.storage import InteractionDataStore


def test_interaction_store_put_get(tmp_path):
    store = InteractionDataStore(str(tmp_path))
    payload = {
        "ghost_post_id": "507f1f77bcf86cd799439010",
        "updated_at": "2026-01-01T00:00:00Z",
        "platforms": {"mastodon": {}, "bluesky": {}},
        "syndication_links": {"mastodon": {}, "bluesky": {}},
    }

    store.put(payload["ghost_post_id"], payload)

    loaded = store.get(payload["ghost_post_id"])
    assert loaded == payload


def test_interaction_store_reads_legacy_json_and_backfills(tmp_path):
    post_id = "507f1f77bcf86cd799439011"
    payload = {
        "ghost_post_id": post_id,
        "updated_at": "2026-01-01T00:00:00Z",
        "platforms": {"mastodon": {}, "bluesky": {}},
        "syndication_links": {"mastodon": {}, "bluesky": {}},
    }
    legacy_file = Path(tmp_path) / f"{post_id}.json"
    legacy_file.write_text(json.dumps(payload))

    store = InteractionDataStore(str(tmp_path))

    loaded = store.get(post_id)
    assert loaded == payload

    # Ensure legacy read is persisted to SQLite for subsequent reads
    legacy_file.unlink()
    loaded_again = store.get(post_id)
    assert loaded_again == payload
