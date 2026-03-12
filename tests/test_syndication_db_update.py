"""
Unit Tests for Immediate Interaction Data Update on Syndication.

These tests verify that:
1. The interaction_data table is updated immediately after a post is syndicated
   (instead of waiting for the next periodic sync).
2. For split multi-image posts the syndication link stored in interaction_data
   points to the post containing the featured image (split_index 0).
3. The periodic sync (sync_post_interactions) also uses the featured image
   post as the canonical syndication link for split posts.
4. The ghost.py /api/interactions fallback endpoint uses the featured image
   post when building syndication_links from the syndication_mappings table.
"""
import json
import tempfile
import os
import shutil
import unittest
from unittest.mock import MagicMock, patch

from interactions.interaction_sync import (
    store_syndication_mapping,
    update_interaction_data_on_syndication,
    InteractionSyncService,
)
from interactions.storage import InteractionDataStore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_store(tmp_path: str) -> InteractionDataStore:
    return InteractionDataStore(tmp_path)


def _empty_interaction(ghost_post_id: str) -> dict:
    return {
        "ghost_post_id": ghost_post_id,
        "updated_at": "2026-01-01T00:00:00+00:00",
        "syndication_links": {"mastodon": {}, "bluesky": {}},
        "platforms": {"mastodon": {}, "bluesky": {}},
    }


# ---------------------------------------------------------------------------
# Tests for update_interaction_data_on_syndication
# ---------------------------------------------------------------------------

class TestUpdateInteractionDataOnSyndication(unittest.TestCase):
    """Tests for the update_interaction_data_on_syndication helper."""

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.post_id = "507f1f77bcf86cd799439001"

    def tearDown(self):
        shutil.rmtree(self.tmp_dir)

    def test_non_split_post_creates_interaction_data(self):
        """Calling the function for a non-split post creates an interaction_data row."""
        update_interaction_data_on_syndication(
            ghost_post_id=self.post_id,
            platform="mastodon",
            account_name="personal",
            post_url="https://mastodon.social/@user/111",
            split_info=None,
            storage_path=self.tmp_dir,
        )

        store = _make_store(self.tmp_dir)
        data = store.get(self.post_id)

        self.assertIsNotNone(data)
        self.assertEqual(
            data["syndication_links"]["mastodon"]["personal"],
            {"post_url": "https://mastodon.social/@user/111"},
        )

    def test_non_split_post_updates_existing_interaction_data(self):
        """Calling the function for a non-split post updates an existing row."""
        store = _make_store(self.tmp_dir)
        existing = _empty_interaction(self.post_id)
        existing["syndication_links"]["bluesky"]["main"] = {"post_url": "https://bsky.app/1"}
        store.put(self.post_id, existing)

        update_interaction_data_on_syndication(
            ghost_post_id=self.post_id,
            platform="mastodon",
            account_name="personal",
            post_url="https://mastodon.social/@user/222",
            storage_path=self.tmp_dir,
        )

        data = store.get(self.post_id)
        # New mastodon link present
        self.assertEqual(
            data["syndication_links"]["mastodon"]["personal"],
            {"post_url": "https://mastodon.social/@user/222"},
        )
        # Existing bluesky link preserved
        self.assertEqual(
            data["syndication_links"]["bluesky"]["main"],
            {"post_url": "https://bsky.app/1"},
        )

    def test_split_index_0_sets_syndication_link(self):
        """split_index 0 is the featured image post and must update syndication_links."""
        update_interaction_data_on_syndication(
            ghost_post_id=self.post_id,
            platform="mastodon",
            account_name="archive",
            post_url="https://mastodon.social/@user/split0",
            split_info={"is_split": True, "split_index": 0, "total_splits": 3},
            storage_path=self.tmp_dir,
        )

        store = _make_store(self.tmp_dir)
        data = store.get(self.post_id)

        self.assertIsNotNone(data)
        self.assertEqual(
            data["syndication_links"]["mastodon"]["archive"],
            {"post_url": "https://mastodon.social/@user/split0"},
        )

    def test_split_index_nonzero_does_not_overwrite_syndication_link(self):
        """Splits at index > 0 must NOT update syndication_links."""
        # First establish the link via split_index 0
        update_interaction_data_on_syndication(
            ghost_post_id=self.post_id,
            platform="mastodon",
            account_name="archive",
            post_url="https://mastodon.social/@user/split0",
            split_info={"is_split": True, "split_index": 0, "total_splits": 3},
            storage_path=self.tmp_dir,
        )

        # Now simulate split_index 1 arriving (should be ignored)
        update_interaction_data_on_syndication(
            ghost_post_id=self.post_id,
            platform="mastodon",
            account_name="archive",
            post_url="https://mastodon.social/@user/split1",
            split_info={"is_split": True, "split_index": 1, "total_splits": 3},
            storage_path=self.tmp_dir,
        )

        store = _make_store(self.tmp_dir)
        data = store.get(self.post_id)

        # Link must still point to split_index 0 (featured image)
        self.assertEqual(
            data["syndication_links"]["mastodon"]["archive"]["post_url"],
            "https://mastodon.social/@user/split0",
        )

    def test_split_index_nonzero_arriving_first_does_not_create_row(self):
        """If a non-featured split arrives before split_index 0, no row is created."""
        update_interaction_data_on_syndication(
            ghost_post_id=self.post_id,
            platform="mastodon",
            account_name="archive",
            post_url="https://mastodon.social/@user/split2",
            split_info={"is_split": True, "split_index": 2, "total_splits": 3},
            storage_path=self.tmp_dir,
        )

        store = _make_store(self.tmp_dir)
        data = store.get(self.post_id)
        self.assertIsNone(data)

    def test_missing_post_url_does_not_create_row(self):
        """An empty post_url must be silently skipped."""
        update_interaction_data_on_syndication(
            ghost_post_id=self.post_id,
            platform="mastodon",
            account_name="personal",
            post_url="",
            storage_path=self.tmp_dir,
        )

        store = _make_store(self.tmp_dir)
        self.assertIsNone(store.get(self.post_id))


# ---------------------------------------------------------------------------
# Tests for store_syndication_mapping → immediate interaction_data update
# ---------------------------------------------------------------------------

class TestStoreSyndicationMappingUpdatesInteractionData(unittest.TestCase):
    """store_syndication_mapping must immediately update interaction_data."""

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.post_id = "507f1f77bcf86cd799439002"

    def tearDown(self):
        shutil.rmtree(self.tmp_dir)

    def test_non_split_mastodon_updates_interaction_data(self):
        """After a non-split Mastodon syndication, interaction_data has the link."""
        store_syndication_mapping(
            ghost_post_id=self.post_id,
            ghost_post_url="https://blog.example.com/post/",
            platform="mastodon",
            account_name="personal",
            post_data={"status_id": "999", "post_url": "https://mastodon.social/@u/999"},
            storage_path=self.tmp_dir,
        )

        data = _make_store(self.tmp_dir).get(self.post_id)
        self.assertIsNotNone(data)
        self.assertEqual(
            data["syndication_links"]["mastodon"]["personal"],
            {"post_url": "https://mastodon.social/@u/999"},
        )

    def test_non_split_bluesky_updates_interaction_data(self):
        """After a non-split Bluesky syndication, interaction_data has the link."""
        store_syndication_mapping(
            ghost_post_id=self.post_id,
            ghost_post_url="https://blog.example.com/post/",
            platform="bluesky",
            account_name="main",
            post_data={
                "post_uri": "at://did:plc:abc/app.bsky.feed.post/xyz",
                "post_url": "https://bsky.app/profile/user/post/xyz",
            },
            storage_path=self.tmp_dir,
        )

        data = _make_store(self.tmp_dir).get(self.post_id)
        self.assertIsNotNone(data)
        self.assertEqual(
            data["syndication_links"]["bluesky"]["main"],
            {"post_url": "https://bsky.app/profile/user/post/xyz"},
        )

    def test_split_index_0_updates_interaction_data(self):
        """Featured image split (index 0) must update interaction_data."""
        store_syndication_mapping(
            ghost_post_id=self.post_id,
            ghost_post_url="https://blog.example.com/post/",
            platform="mastodon",
            account_name="archive",
            post_data={"status_id": "s0", "post_url": "https://mastodon.social/@u/s0"},
            split_info={"is_split": True, "split_index": 0, "total_splits": 2},
            storage_path=self.tmp_dir,
        )

        data = _make_store(self.tmp_dir).get(self.post_id)
        self.assertIsNotNone(data)
        self.assertEqual(
            data["syndication_links"]["mastodon"]["archive"],
            {"post_url": "https://mastodon.social/@u/s0"},
        )

    def test_split_index_1_does_not_update_interaction_data_link(self):
        """Non-featured splits (index > 0) must not change syndication_links."""
        # Establish link for split 0 first
        store_syndication_mapping(
            ghost_post_id=self.post_id,
            ghost_post_url="https://blog.example.com/post/",
            platform="mastodon",
            account_name="archive",
            post_data={"status_id": "s0", "post_url": "https://mastodon.social/@u/s0"},
            split_info={"is_split": True, "split_index": 0, "total_splits": 2},
            storage_path=self.tmp_dir,
        )
        # Now store split 1
        store_syndication_mapping(
            ghost_post_id=self.post_id,
            ghost_post_url="https://blog.example.com/post/",
            platform="mastodon",
            account_name="archive",
            post_data={"status_id": "s1", "post_url": "https://mastodon.social/@u/s1"},
            split_info={"is_split": True, "split_index": 1, "total_splits": 2},
            storage_path=self.tmp_dir,
        )

        data = _make_store(self.tmp_dir).get(self.post_id)
        # Syndication link must still point to the featured image (split 0)
        self.assertEqual(
            data["syndication_links"]["mastodon"]["archive"]["post_url"],
            "https://mastodon.social/@u/s0",
        )


# ---------------------------------------------------------------------------
# Tests for sync_post_interactions split post handling
# ---------------------------------------------------------------------------

class TestSyncPostInteractionsSplitLinks(unittest.TestCase):
    """sync_post_interactions must record the featured image URL for split posts."""

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.post_id = "507f1f77bcf86cd799439003"

    def tearDown(self):
        shutil.rmtree(self.tmp_dir)

    def _store_split_mapping(self):
        """Write a synthetic two-split syndication mapping to the store."""
        store = _make_store(self.tmp_dir)
        mapping = {
            "ghost_post_id": self.post_id,
            "ghost_post_url": "https://blog.example.com/split-post/",
            "syndicated_at": "2026-01-01T00:00:00+00:00",
            "platforms": {
                "mastodon": {
                    "archive": [
                        {
                            "status_id": "s0",
                            "post_url": "https://mastodon.social/@u/s0",
                            "split_index": 0,
                            "is_split": True,
                        },
                        {
                            "status_id": "s1",
                            "post_url": "https://mastodon.social/@u/s1",
                            "split_index": 1,
                            "is_split": True,
                        },
                    ]
                },
                "bluesky": {},
            },
        }
        store.put_syndication_mapping(self.post_id, mapping)

    def _make_split_mastodon_data(self):
        """Return mock split interaction data as would be returned by _sync_mastodon_split."""
        return {
            "is_split": True,
            "total_splits": 2,
            "synced_splits": 2,
            "split_posts": [
                {
                    "status_id": "s0",
                    "post_url": "https://mastodon.social/@u/s0",
                    "split_index": 0,
                    "favorites": 3,
                    "reblogs": 1,
                    "replies": 0,
                },
                {
                    "status_id": "s1",
                    "post_url": "https://mastodon.social/@u/s1",
                    "split_index": 1,
                    "favorites": 1,
                    "reblogs": 0,
                    "replies": 0,
                },
            ],
            "favorites": 4,
            "reblogs": 1,
            "replies": 0,
            "reply_previews": [],
            "updated_at": "2026-01-01T00:00:00+00:00",
        }

    def test_split_posts_syndication_link_points_to_featured_image(self):
        """sync_post_interactions stores the split_index 0 URL as the syndication link."""
        self._store_split_mapping()

        mock_mastodon = MagicMock()
        mock_mastodon.account_name = "archive"
        mock_mastodon.enabled = True
        mock_mastodon.api = MagicMock()

        service = InteractionSyncService(
            mastodon_clients=[mock_mastodon],
            storage_path=self.tmp_dir,
        )

        with patch.object(
            service,
            "_sync_mastodon_split_interactions",
            return_value=self._make_split_mastodon_data(),
        ):
            result = service.sync_post_interactions(self.post_id)

        syndi_link = result["syndication_links"]["mastodon"]["archive"]
        # Must be a single dict pointing to the featured image post (split_index 0)
        self.assertIsInstance(syndi_link, dict)
        self.assertEqual(syndi_link["post_url"], "https://mastodon.social/@u/s0")

    def test_split_posts_syndication_link_not_a_list(self):
        """sync_post_interactions must not store a list for split post syndication links."""
        self._store_split_mapping()

        mock_mastodon = MagicMock()
        mock_mastodon.account_name = "archive"
        mock_mastodon.enabled = True
        mock_mastodon.api = MagicMock()

        service = InteractionSyncService(
            mastodon_clients=[mock_mastodon],
            storage_path=self.tmp_dir,
        )

        with patch.object(
            service,
            "_sync_mastodon_split_interactions",
            return_value=self._make_split_mastodon_data(),
        ):
            result = service.sync_post_interactions(self.post_id)

        syndi_link = result["syndication_links"]["mastodon"]["archive"]
        self.assertNotIsInstance(syndi_link, list)


# ---------------------------------------------------------------------------
# Tests for ghost.py endpoint fallback using featured image link
# ---------------------------------------------------------------------------

class TestGhostEndpointSplitSyndicationLink(unittest.TestCase):
    """The /api/interactions fallback endpoint must return the featured image URL."""

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        from queue import Queue
        self.queue = Queue()

    def tearDown(self):
        shutil.rmtree(self.tmp_dir)

    def _create_app(self):
        from ghost.ghost import create_app, clear_rate_limit_caches
        clear_rate_limit_caches()
        config = {
            "security": {
                "rate_limit_enabled": False,
                "discovery_rate_limit_enabled": False,
                "allowed_referrers": [],
            }
        }
        app = create_app(
            self.queue,
            config=config,
            mastodon_clients=[],
            bluesky_clients=[],
            ghost_api_client=None,
        )
        app.config["TESTING"] = True
        app.config["INTERACTIONS_STORAGE_PATH"] = self.tmp_dir
        return app

    def test_split_mapping_fallback_returns_featured_image_link(self):
        """When interaction_data is absent, the fallback uses the featured image link."""
        post_id = "507f1f77bcf86cd799439020"
        store = _make_store(self.tmp_dir)
        mapping = {
            "ghost_post_id": post_id,
            "ghost_post_url": "https://blog.example.com/post/",
            "syndicated_at": "2026-01-01T00:00:00+00:00",
            "platforms": {
                "mastodon": {
                    "archive": [
                        {
                            "status_id": "s0",
                            "post_url": "https://mastodon.social/@u/s0",
                            "split_index": 0,
                            "is_split": True,
                        },
                        {
                            "status_id": "s1",
                            "post_url": "https://mastodon.social/@u/s1",
                            "split_index": 1,
                            "is_split": True,
                        },
                    ]
                },
                "bluesky": {},
            },
        }
        store.put_syndication_mapping(post_id, mapping)

        app = self._create_app()
        with app.test_client() as client:
            resp = client.get(
                f"/api/interactions/{post_id}",
                headers={"Referer": "https://blog.example.com/"},
            )

        self.assertEqual(resp.status_code, 200)
        body = json.loads(resp.data)
        link = body["syndication_links"]["mastodon"]["archive"]

        # Must be a single dict (not a list) pointing to split_index 0
        self.assertIsInstance(link, dict)
        self.assertEqual(link["post_url"], "https://mastodon.social/@u/s0")

    def test_non_split_mapping_fallback_returns_single_link(self):
        """Fallback for a non-split post still returns a single dict link."""
        post_id = "507f1f77bcf86cd799439021"
        store = _make_store(self.tmp_dir)
        mapping = {
            "ghost_post_id": post_id,
            "ghost_post_url": "https://blog.example.com/post2/",
            "syndicated_at": "2026-01-01T00:00:00+00:00",
            "platforms": {
                "mastodon": {
                    "personal": {
                        "status_id": "99",
                        "post_url": "https://mastodon.social/@u/99",
                    }
                },
                "bluesky": {},
            },
        }
        store.put_syndication_mapping(post_id, mapping)

        app = self._create_app()
        with app.test_client() as client:
            resp = client.get(
                f"/api/interactions/{post_id}",
                headers={"Referer": "https://blog.example.com/"},
            )

        self.assertEqual(resp.status_code, 200)
        body = json.loads(resp.data)
        link = body["syndication_links"]["mastodon"]["personal"]

        self.assertIsInstance(link, dict)
        self.assertEqual(link["post_url"], "https://mastodon.social/@u/99")


if __name__ == "__main__":
    unittest.main()
