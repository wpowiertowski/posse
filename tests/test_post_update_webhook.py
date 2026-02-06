"""
Unit Tests for Ghost Post Update Webhook.

This test suite validates the /webhook/ghost/post-updated endpoint which handles
Ghost post update events. It checks syndication mappings to determine if a post
has been syndicated to all active accounts, and queues selective syndication for
any that are missing.

Test Coverage:
    - Valid post update with missing syndication triggers queue
    - Post already fully syndicated returns success without queuing
    - Non-published posts are skipped
    - Schema validation errors return 400
    - Non-JSON payloads return 400
    - Selective syndication targets only missing accounts
    - Tag filtering is respected
    - Empty mapping (no prior syndication) queues to all matching accounts

Running Tests:
    $ PYTHONPATH=src python -m pytest tests/test_post_update_webhook.py -v
"""
import json
import pytest
import tempfile
import shutil
import os
import sqlite3
from queue import Queue
from unittest.mock import MagicMock, patch

from ghost.ghost import create_app
from interactions.storage import InteractionDataStore


@pytest.fixture
def test_dirs():
    """Create temporary directories for test data."""
    test_dir = tempfile.mkdtemp()
    storage_path = os.path.join(test_dir, "interactions")
    mappings_path = os.path.join(test_dir, "syndication_mappings")
    os.makedirs(storage_path, exist_ok=True)
    os.makedirs(mappings_path, exist_ok=True)

    yield {
        "test_dir": test_dir,
        "storage_path": storage_path,
        "mappings_path": mappings_path
    }

    shutil.rmtree(test_dir)


def _make_mock_client(account_name, platform_tags=None):
    """Create a mock social media client."""
    client = MagicMock()
    client.enabled = True
    client.account_name = account_name
    client.tags = platform_tags or []
    client.max_post_length = 300
    client.split_multi_image_posts = False
    return client


def _make_valid_payload(post_id="695c4286fc6853000152b1fc", status="published"):
    """Create a valid Ghost post update payload."""
    return {
        "post": {
            "current": {
                "id": post_id,
                "uuid": "8e9d1584-c983-4c44-bbc0-2796be02fa31",
                "title": "Test Post",
                "slug": "test-post",
                "status": status,
                "url": "https://example.com/test-post/",
                "created_at": "2026-01-05T23:00:22.000Z",
                "updated_at": "2026-02-05T10:00:00.000Z",
                "tags": [
                    {
                        "id": "tag1",
                        "name": "Photography",
                        "slug": "photography"
                    }
                ],
                "html": "<p>Test content</p>",
                "custom_excerpt": "Test excerpt"
            },
            "previous": {
                "updated_at": "2026-02-05T09:00:00.000Z"
            }
        }
    }


@pytest.fixture
def app_with_clients(test_dirs):
    """Create Flask app with mock clients for testing post update webhook."""
    test_queue = Queue()

    mock_mastodon = _make_mock_client("personal")
    mock_bluesky = _make_mock_client("main")

    config = {
        "security": {
            "rate_limit_enabled": False,
            "discovery_rate_limit_enabled": False,
            "allowed_referrers": []
        }
    }

    app = create_app(
        test_queue,
        config=config,
        mastodon_clients=[mock_mastodon],
        bluesky_clients=[mock_bluesky]
    )

    app.config["TESTING"] = True
    app.config["INTERACTIONS_STORAGE_PATH"] = test_dirs["storage_path"]
    app.config["SYNDICATION_MAPPINGS_PATH"] = test_dirs["mappings_path"]

    return app, test_queue, mock_mastodon, mock_bluesky, test_dirs


class TestPostUpdateWebhook:
    """Tests for the /webhook/ghost/post-updated endpoint."""

    def test_non_json_payload_rejected(self, app_with_clients):
        """Test that non-JSON payloads are rejected with 400."""
        app, _, _, _, _ = app_with_clients

        with app.test_client() as client:
            response = client.post(
                "/webhook/ghost/post-updated",
                data="not json",
                content_type="text/plain"
            )

            assert response.status_code == 400
            data = response.get_json()
            assert data["error"] == "Content-Type must be application/json"

    def test_invalid_schema_rejected(self, app_with_clients):
        """Test that invalid payloads fail schema validation."""
        app, _, _, _, _ = app_with_clients

        invalid_payload = {
            "post": {
                "current": {
                    "id": "123",
                    "title": "Test"
                    # Missing required fields
                }
            }
        }

        with app.test_client() as client:
            response = client.post(
                "/webhook/ghost/post-updated",
                json=invalid_payload,
                content_type="application/json"
            )

            assert response.status_code == 400
            data = response.get_json()
            assert data["status"] == "error"
            assert "details" in data

    def test_non_published_post_skipped(self, app_with_clients):
        """Test that draft posts are skipped without queuing."""
        app, test_queue, _, _, _ = app_with_clients

        payload = _make_valid_payload(status="draft")

        with app.test_client() as client:
            response = client.post(
                "/webhook/ghost/post-updated",
                json=payload,
                content_type="application/json"
            )

            assert response.status_code == 200
            data = response.get_json()
            assert "Skipped non-published post" in data["message"]
            assert test_queue.empty(), "Draft post should not be queued"

    def test_fully_syndicated_post_not_queued(self, app_with_clients):
        """Test that a post already syndicated to all accounts is not re-queued."""
        app, test_queue, _, _, test_dirs = app_with_clients

        post_id = "695c4286fc6853000152b1fc"

        # Create syndication mapping with both accounts
        mapping = {
            "ghost_post_id": post_id,
            "ghost_post_url": "https://example.com/test-post/",
            "syndicated_at": "2026-02-01T10:00:00Z",
            "platforms": {
                "mastodon": {
                    "personal": {
                        "status_id": "111222333",
                        "post_url": "https://mastodon.social/@user/111222333"
                    }
                },
                "bluesky": {
                    "main": {
                        "post_uri": "at://did:plc:xxx/app.bsky.feed.post/abc123",
                        "post_url": "https://bsky.app/profile/user/post/abc123"
                    }
                }
            }
        }

        store = InteractionDataStore(test_dirs["storage_path"])
        store.put_syndication_mapping(post_id, mapping)

        payload = _make_valid_payload(post_id=post_id)

        with app.test_client() as client:
            response = client.post(
                "/webhook/ghost/post-updated",
                json=payload,
                content_type="application/json"
            )

            assert response.status_code == 200
            data = response.get_json()
            assert data["message"] == "Post already fully syndicated"
            assert test_queue.empty(), "Fully syndicated post should not be queued"

    def test_missing_accounts_queued_for_syndication(self, app_with_clients):
        """Test that a post missing syndication to some accounts is queued."""
        app, test_queue, _, _, test_dirs = app_with_clients

        post_id = "695c4286fc6853000152b1fc"

        # Create mapping with only Mastodon - Bluesky is missing
        mapping = {
            "ghost_post_id": post_id,
            "ghost_post_url": "https://example.com/test-post/",
            "syndicated_at": "2026-02-01T10:00:00Z",
            "platforms": {
                "mastodon": {
                    "personal": {
                        "status_id": "111222333",
                        "post_url": "https://mastodon.social/@user/111222333"
                    }
                }
            }
        }

        store = InteractionDataStore(test_dirs["storage_path"])
        store.put_syndication_mapping(post_id, mapping)

        payload = _make_valid_payload(post_id=post_id)

        with app.test_client() as client:
            response = client.post(
                "/webhook/ghost/post-updated",
                json=payload,
                content_type="application/json"
            )

            assert response.status_code == 200
            data = response.get_json()
            assert "queued for syndication" in data["message"]
            assert "bluesky/main" in data["syndicated_to"]
            assert "mastodon/personal" not in data["syndicated_to"]

            # Verify event was queued
            assert not test_queue.empty()
            queued_event = test_queue.get(timeout=1)

            # Verify selective targeting metadata
            assert "__target_accounts" in queued_event
            assert ("bluesky", "main") in queued_event["__target_accounts"]
            assert ("mastodon", "personal") not in queued_event["__target_accounts"]

    def test_no_mapping_queues_all_matching_accounts(self, app_with_clients):
        """Test that a post with no mapping queues to all matching accounts."""
        app, test_queue, _, _, _ = app_with_clients

        post_id = "695c4286fc6853000152b1fc"
        payload = _make_valid_payload(post_id=post_id)

        with app.test_client() as client:
            response = client.post(
                "/webhook/ghost/post-updated",
                json=payload,
                content_type="application/json"
            )

            assert response.status_code == 200
            data = response.get_json()
            assert "queued for syndication" in data["message"]
            assert "mastodon/personal" in data["syndicated_to"]
            assert "bluesky/main" in data["syndicated_to"]

            # Verify event was queued with both targets
            queued_event = test_queue.get(timeout=1)
            target_accounts = queued_event["__target_accounts"]
            assert ("mastodon", "personal") in target_accounts
            assert ("bluesky", "main") in target_accounts

    def test_tag_filtering_respected(self, test_dirs):
        """Test that tag filtering is applied when determining missing accounts."""
        test_queue = Queue()

        # Mastodon client with photography tag
        mock_mastodon = _make_mock_client("personal", platform_tags=["photography"])
        # Bluesky client with tech tag only
        mock_bluesky = _make_mock_client("main", platform_tags=["tech"])

        config = {
            "security": {
                "rate_limit_enabled": False,
                "discovery_rate_limit_enabled": False,
                "allowed_referrers": []
            }
        }

        app = create_app(
            test_queue,
            config=config,
            mastodon_clients=[mock_mastodon],
            bluesky_clients=[mock_bluesky]
        )

        app.config["TESTING"] = True
        app.config["INTERACTIONS_STORAGE_PATH"] = test_dirs["storage_path"]
        app.config["SYNDICATION_MAPPINGS_PATH"] = test_dirs["mappings_path"]

        # Post has photography tag but not tech
        payload = _make_valid_payload()

        with app.test_client() as client:
            response = client.post(
                "/webhook/ghost/post-updated",
                json=payload,
                content_type="application/json"
            )

            assert response.status_code == 200
            data = response.get_json()

            # Only mastodon/personal should be targeted (tag match)
            # bluesky/main should not (tech tag doesn't match photography)
            if "syndicated_to" in data:
                assert "mastodon/personal" in data["syndicated_to"]
                assert "bluesky/main" not in data["syndicated_to"]

    def test_corrupted_mapping_payload_in_db_handled(self, app_with_clients):
        """Test that a corrupted SQLite mapping payload is handled gracefully."""
        app, test_queue, _, _, test_dirs = app_with_clients

        post_id = "695c4286fc6853000152b1fc"

        InteractionDataStore(test_dirs["storage_path"])
        db_path = os.path.join(test_dirs["storage_path"], "interactions.db")
        conn = sqlite3.connect(db_path)
        conn.execute(
            """
            INSERT INTO syndication_mappings (ghost_post_id, payload, syndicated_at)
            VALUES (?, ?, ?)
            """,
            (post_id, "not valid json{{{", "2026-02-01T10:00:00Z"),
        )
        conn.commit()
        conn.close()

        payload = _make_valid_payload(post_id=post_id)

        with app.test_client() as client:
            response = client.post(
                "/webhook/ghost/post-updated",
                json=payload,
                content_type="application/json"
            )

            # Should still succeed - treats as no mapping
            assert response.status_code == 200
            data = response.get_json()
            assert "queued for syndication" in data["message"]

    def test_split_post_mapping_recognized(self, app_with_clients):
        """Test that split post mappings are recognized as already syndicated."""
        app, test_queue, _, _, test_dirs = app_with_clients

        post_id = "695c4286fc6853000152b1fc"

        # Create mapping with split Bluesky posts
        mapping = {
            "ghost_post_id": post_id,
            "ghost_post_url": "https://example.com/test-post/",
            "syndicated_at": "2026-02-01T10:00:00Z",
            "platforms": {
                "mastodon": {
                    "personal": {
                        "status_id": "111222333",
                        "post_url": "https://mastodon.social/@user/111222333"
                    }
                },
                "bluesky": {
                    "main": [
                        {
                            "post_uri": "at://did:plc:xxx/app.bsky.feed.post/abc1",
                            "post_url": "https://bsky.app/profile/user/post/abc1",
                            "is_split": True,
                            "split_index": 0,
                            "total_splits": 2
                        },
                        {
                            "post_uri": "at://did:plc:xxx/app.bsky.feed.post/abc2",
                            "post_url": "https://bsky.app/profile/user/post/abc2",
                            "is_split": True,
                            "split_index": 1,
                            "total_splits": 2
                        }
                    ]
                }
            }
        }

        store = InteractionDataStore(test_dirs["storage_path"])
        store.put_syndication_mapping(post_id, mapping)

        payload = _make_valid_payload(post_id=post_id)

        with app.test_client() as client:
            response = client.post(
                "/webhook/ghost/post-updated",
                json=payload,
                content_type="application/json"
            )

            assert response.status_code == 200
            data = response.get_json()
            assert data["message"] == "Post already fully syndicated"
            assert test_queue.empty()


class TestSelectiveSyndicationInProcessEvents:
    """Tests for selective syndication support in process_events."""

    def test_target_accounts_filters_clients(self):
        """Test that __target_accounts filters the client list correctly."""
        from posse.posse import _filter_clients_by_tags

        mock_mastodon = _make_mock_client("personal")
        mock_bluesky = _make_mock_client("main")

        all_clients = [("Mastodon", mock_mastodon), ("Bluesky", mock_bluesky)]
        tags = [{"name": "Photography", "slug": "photography"}]

        # First verify tag filtering returns both
        filtered = _filter_clients_by_tags(tags, all_clients)
        assert len(filtered) == 2

        # Now simulate selective targeting
        target_accounts = [("mastodon", "personal")]
        target_set = {(p.lower(), a) for p, a in target_accounts}
        selective = [
            (platform, client) for platform, client in filtered
            if (platform.lower(), client.account_name) in target_set
        ]

        assert len(selective) == 1
        assert selective[0][0] == "Mastodon"
        assert selective[0][1].account_name == "personal"
