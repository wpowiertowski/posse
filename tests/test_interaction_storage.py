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


def test_syndication_mapping_store_put_get(tmp_path):
    store = InteractionDataStore(str(tmp_path))
    mapping = {
        "ghost_post_id": "507f1f77bcf86cd799439099",
        "ghost_post_url": "https://blog.example.com/post/",
        "syndicated_at": "2026-01-01T00:00:00Z",
        "platforms": {"mastodon": {"personal": {"status_id": "1", "post_url": "https://masto/1"}}},
    }

    store.put_syndication_mapping(mapping["ghost_post_id"], mapping)

    loaded = store.get_syndication_mapping(mapping["ghost_post_id"])
    assert loaded == mapping


def test_syndication_mapping_store_returns_none_when_record_missing(tmp_path):
    store = InteractionDataStore(str(tmp_path))

    loaded = store.get_syndication_mapping("507f1f77bcf86cd799439098")

    assert loaded is None
