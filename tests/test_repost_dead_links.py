"""
Unit tests for the dead-syndication repost tool (posse.repost_dead_links).

Covers worklist selection (only deleted entries, newest-first, account filter),
the single-post repost path (reuses the normal syndication formatting and clears the
dead flag), and the dry-run guard.

Running:
    $ PYTHONPATH=src python -m unittest tests.test_repost_dead_links -v
"""
import unittest
from unittest.mock import patch, MagicMock
import tempfile
import shutil

from interactions.storage import InteractionDataStore
from posse import repost_dead_links


class TestBuildWorklist(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.store = InteractionDataStore(self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _put(self, post_id, syndicated_at, mastodon):
        self.store.put_syndication_mapping(post_id, {
            "ghost_post_id": post_id,
            "ghost_post_url": f"https://blog.example.com/{post_id}/",
            "syndicated_at": syndicated_at,
            "platforms": {"mastodon": mastodon, "bluesky": {}},
        })

    def test_selects_only_deleted_newest_first(self):
        self._put("aaa", "2026-01-01T00:00:00+00:00",
                  {"personal": {"status_id": "1", "post_url": "u1", "deleted": True}})
        self._put("bbb", "2026-03-01T00:00:00+00:00",
                  {"personal": {"status_id": "2", "post_url": "u2", "deleted": True}})
        self._put("ccc", "2026-02-01T00:00:00+00:00",
                  {"personal": {"status_id": "3", "post_url": "u3"}})  # live, excluded

        work = repost_dead_links._build_worklist(self.store)

        self.assertEqual([w["ghost_post_id"] for w in work], ["bbb", "aaa"])

    def test_account_filter(self):
        self._put("aaa", "2026-01-01T00:00:00+00:00", {
            "personal": {"status_id": "1", "post_url": "u1", "deleted": True},
            "work": {"status_id": "2", "post_url": "u2", "deleted": True},
        })

        work = repost_dead_links._build_worklist(self.store, account_filter="work")

        self.assertEqual(len(work), 1)
        self.assertEqual(work[0]["account_name"], "work")

    def test_split_all_deleted_selected(self):
        self._put("aaa", "2026-01-01T00:00:00+00:00", {"personal": [
            {"status_id": "1", "post_url": "u1", "deleted": True},
            {"status_id": "2", "post_url": "u2", "deleted": True},
        ]})
        # one sub-entry alive -> account not fully dead -> excluded
        self._put("bbb", "2026-01-01T00:00:00+00:00", {"personal": [
            {"status_id": "3", "post_url": "u3", "deleted": True},
            {"status_id": "4", "post_url": "u4"},
        ]})

        work = repost_dead_links._build_worklist(self.store)

        self.assertEqual([w["ghost_post_id"] for w in work], ["aaa"])


class TestRepostOne(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.store = InteractionDataStore(self.tmp)
        self.post_id = "507f1f77bcf86cd799439011"
        self.store.put_syndication_mapping(self.post_id, {
            "ghost_post_id": self.post_id,
            "ghost_post_url": "https://blog.example.com/p/",
            "syndicated_at": "2026-01-01T00:00:00+00:00",
            "platforms": {
                "mastodon": {"personal": {"status_id": "1", "post_url": "old", "deleted": True}},
                "bluesky": {},
            },
        })

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _client(self):
        client = MagicMock()
        client.enabled = True
        client.api = MagicMock()
        client.account_name = "personal"
        client.max_post_length = 500
        client.post.return_value = {"id": "999", "url": "https://mastodon.social/@me/999"}
        return client

    def _ghost_api(self, post):
        api = MagicMock()
        api.get_post_by_id.return_value = post
        return api

    def test_successful_repost_overwrites_dead_entry(self):
        client = self._client()
        ghost_api = self._ghost_api({
            "title": "Title", "url": "https://blog.example.com/p/",
            "custom_excerpt": "Excerpt", "tags": [{"name": "tech", "slug": "tech"}],
            "feature_image": None, "html": "",
        })
        item = {"ghost_post_id": self.post_id, "ghost_post_url": "https://blog.example.com/p/",
                "account_name": "personal"}

        ok = repost_dead_links._repost_one(
            item, ghost_api, {"personal": client}, self.tmp, "UTC")

        self.assertTrue(ok)
        client.post.assert_called_once()
        # Dead flag cleared, new status_id stored.
        entry = self.store.get_syndication_mapping(self.post_id)["platforms"]["mastodon"]["personal"]
        self.assertEqual(entry["status_id"], "999")
        self.assertNotIn("deleted", entry)
        # ?ref=mastodon analytics tag preserved in the posted content.
        posted = client.post.call_args.kwargs["content"]
        self.assertIn("https://blog.example.com/p/", posted)

    def test_cleans_up_cached_images_after_post(self):
        client = self._client()
        # Local image in the post HTML so _extract_post_data returns it.
        ghost_api = self._ghost_api({
            "title": "Title", "url": "https://blog.example.com/p/",
            "custom_excerpt": "", "tags": [],
            "feature_image": "https://blog.example.com/feat.jpg", "feature_image_alt": "alt",
            "html": "",
        })
        item = {"ghost_post_id": self.post_id, "ghost_post_url": "https://blog.example.com/p/",
                "account_name": "personal"}

        ok = repost_dead_links._repost_one(item, ghost_api, {"personal": client}, self.tmp, "UTC")

        self.assertTrue(ok)
        # Downloaded images must be cleaned up like the normal syndication path.
        client._remove_images.assert_called_once()
        self.assertIn("https://blog.example.com/feat.jpg", client._remove_images.call_args.args[0])

    def test_skips_when_ghost_post_missing(self):
        client = self._client()
        ghost_api = self._ghost_api(None)
        item = {"ghost_post_id": self.post_id, "ghost_post_url": "x", "account_name": "personal"}

        ok = repost_dead_links._repost_one(item, ghost_api, {"personal": client}, self.tmp, "UTC")

        self.assertFalse(ok)
        client.post.assert_not_called()

    def test_skips_when_client_unavailable(self):
        ghost_api = self._ghost_api({"title": "T", "url": "u", "html": ""})
        item = {"ghost_post_id": self.post_id, "ghost_post_url": "x", "account_name": "personal"}

        ok = repost_dead_links._repost_one(item, ghost_api, {}, self.tmp, "UTC")

        self.assertFalse(ok)
        ghost_api.get_post_by_id.assert_not_called()


class TestMainDryRun(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.store = InteractionDataStore(self.tmp)
        self.store.put_syndication_mapping("aaa", {
            "ghost_post_id": "aaa",
            "ghost_post_url": "https://blog.example.com/aaa/",
            "syndicated_at": "2026-01-01T00:00:00+00:00",
            "platforms": {
                "mastodon": {"personal": {"status_id": "1", "post_url": "u", "deleted": True}},
                "bluesky": {},
            },
        })

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    @patch("posse.repost_dead_links.MastodonClient")
    @patch("posse.repost_dead_links.GhostContentAPIClient")
    @patch("posse.repost_dead_links.get_timezone_name", return_value="UTC")
    @patch("posse.repost_dead_links.load_config")
    def test_dry_run_does_not_post(self, mock_load, _tz, mock_ghost, mock_masto):
        mock_load.return_value = {"interactions": {"cache_directory": self.tmp}}

        rc = repost_dead_links.main(["--dry-run"])

        self.assertEqual(rc, 0)
        # Dry run must not construct clients/API or post anything.
        mock_ghost.from_config.assert_not_called()
        mock_masto.from_config.assert_not_called()


if __name__ == "__main__":
    unittest.main()
