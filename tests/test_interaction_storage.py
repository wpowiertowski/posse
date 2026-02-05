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


def test_interaction_store_returns_none_when_record_missing(tmp_path):
    store = InteractionDataStore(str(tmp_path))

    loaded = store.get("507f1f77bcf86cd799439011")

    assert loaded is None
