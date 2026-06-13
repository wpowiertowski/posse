"""
Unit tests for dead Mastodon syndication-link detection and suppression.

Covers InteractionSyncService.prune_dead_links() and the regular-sync skip behaviour:

    - 404 detection is strike-gated (a single fluke 404 never suppresses a real link)
    - outages (timeout/5xx/network) cause no state change
    - confirmed-dead links are suppressed from the presented interaction data
    - records are flagged, never purged (status_id/post_url retained)
    - previously-dead links auto-recover when the status returns
    - split posts stay alive while any sub-entry is reachable
    - sync_post_interactions skips already-deleted accounts without hitting the API

Running:
    $ PYTHONPATH=src python -m unittest tests.test_dead_link_pruning -v
"""
import unittest
from unittest.mock import patch, MagicMock
import tempfile
import shutil
from datetime import datetime, timezone

from mastodon import MastodonNotFoundError

from social.mastodon_client import MastodonClient
from interactions.interaction_sync import InteractionSyncService
from interactions.storage import InteractionDataStore


def _make_client(mock_mastodon_class, status_side_effect, account_name="personal"):
    """Build a MastodonClient whose api.status() behaves per status_side_effect."""
    mock_api = MagicMock()
    mock_api.status.side_effect = status_side_effect
    mock_mastodon_class.return_value = mock_api
    client = MastodonClient(
        instance_url="https://mastodon.social",
        access_token="test_token",
        account_name=account_name,
    )
    return client, mock_api


class TestDeadLinkPruning(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.store = InteractionDataStore(self.tmp)
        self.post_id = "507f1f77bcf86cd799439011"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    # -- seeding helpers ---------------------------------------------------

    def _seed_mapping(self, mastodon_entry):
        self.store.put_syndication_mapping(self.post_id, {
            "ghost_post_id": self.post_id,
            "ghost_post_url": "https://blog.example.com/my-post/",
            "syndicated_at": "2026-01-01T00:00:00+00:00",
            "platforms": {"mastodon": {"personal": mastodon_entry}, "bluesky": {}},
        })

    def _seed_interaction_link(self):
        self.store.put(self.post_id, {
            "ghost_post_id": self.post_id,
            "updated_at": "2026-01-01T00:00:00+00:00",
            "syndication_links": {
                "mastodon": {"personal": {"post_url": "https://mastodon.social/@me/1"}},
                "bluesky": {},
            },
            "platforms": {"mastodon": {"personal": {"favorites": 3}}, "bluesky": {}},
        })

    def _service(self, client, threshold=2, recheck_days=0):
        # recheck_days defaults to 0 (backoff disabled) so existing assertions are
        # deterministic and not time-dependent; the backoff test opts in explicitly.
        return InteractionSyncService(
            mastodon_clients=[client],
            storage_path=self.tmp,
            dead_link_confirm_threshold=threshold,
            dead_link_recheck_days=recheck_days,
        )

    def _masto_entry(self):
        return self.store.get_syndication_mapping(self.post_id)["platforms"]["mastodon"]["personal"]

    # -- existence helper --------------------------------------------------

    @patch("social.mastodon_client.Mastodon")
    def test_status_exists_helper(self, mock_mastodon_class):
        client, _ = _make_client(mock_mastodon_class, status_side_effect=[
            {"id": "1"},
            MastodonNotFoundError("gone"),
            TimeoutError("down"),
        ])
        svc = self._service(client)
        self.assertTrue(svc._mastodon_status_exists("personal", "1"))      # alive
        self.assertFalse(svc._mastodon_status_exists("personal", "1"))     # 404
        self.assertIsNone(svc._mastodon_status_exists("personal", "1"))    # outage

    # -- strike gating -----------------------------------------------------

    @patch("social.mastodon_client.Mastodon")
    def test_first_404_records_strike_without_suppressing(self, mock_mastodon_class):
        client, _ = _make_client(mock_mastodon_class, MastodonNotFoundError("gone"))
        self._seed_mapping({"status_id": "1", "post_url": "https://mastodon.social/@me/1"})
        self._seed_interaction_link()

        stats = self._service(client, threshold=2).prune_dead_links()

        entry = self._masto_entry()
        self.assertEqual(entry["dead_strikes"], 1)
        self.assertNotIn("deleted", entry)
        self.assertIn("first_seen_dead", entry)
        # Link still presented after a single 404.
        links = self.store.get(self.post_id)["syndication_links"]["mastodon"]
        self.assertIn("personal", links)
        self.assertEqual(stats["newly_suppressed"], 0)
        self.assertEqual(stats["pending_strikes"], 1)

    @patch("social.mastodon_client.Mastodon")
    def test_threshold_reached_suppresses(self, mock_mastodon_class):
        client, _ = _make_client(mock_mastodon_class, MastodonNotFoundError("gone"))
        # Already one strike from a prior sweep.
        self._seed_mapping({
            "status_id": "1", "post_url": "https://mastodon.social/@me/1",
            "dead_strikes": 1, "first_seen_dead": "2026-01-01T00:00:00+00:00",
        })
        self._seed_interaction_link()

        stats = self._service(client, threshold=2).prune_dead_links()

        entry = self._masto_entry()
        self.assertEqual(entry["dead_strikes"], 2)
        self.assertTrue(entry["deleted"])
        # Record retained — never purged.
        self.assertEqual(entry["status_id"], "1")
        self.assertEqual(entry["post_url"], "https://mastodon.social/@me/1")
        # Suppressed from both presentation sections.
        data = self.store.get(self.post_id)
        self.assertNotIn("personal", data["syndication_links"]["mastodon"])
        self.assertNotIn("personal", data["platforms"]["mastodon"])
        self.assertEqual(stats["newly_suppressed"], 1)

    # -- outage safety -----------------------------------------------------

    @patch("social.mastodon_client.Mastodon")
    def test_outage_causes_no_state_change(self, mock_mastodon_class):
        client, _ = _make_client(mock_mastodon_class, TimeoutError("instance down"))
        self._seed_mapping({"status_id": "1", "post_url": "https://mastodon.social/@me/1"})
        self._seed_interaction_link()

        stats = self._service(client, threshold=2).prune_dead_links()

        entry = self._masto_entry()
        self.assertNotIn("dead_strikes", entry)
        self.assertNotIn("deleted", entry)
        # Link preserved during outage.
        self.assertIn("personal", self.store.get(self.post_id)["syndication_links"]["mastodon"])
        self.assertEqual(stats["newly_suppressed"], 0)
        self.assertEqual(stats["pending_strikes"], 0)

    # -- recovery ----------------------------------------------------------

    @patch("social.mastodon_client.Mastodon")
    def test_resurrects_when_status_returns(self, mock_mastodon_class):
        client, _ = _make_client(mock_mastodon_class, [{"id": "1"}])
        self._seed_mapping({
            "status_id": "1", "post_url": "https://mastodon.social/@me/1",
            "dead_strikes": 2, "first_seen_dead": "2026-01-01T00:00:00+00:00",
            "deleted": True,
        })
        # interaction_data has no link (was suppressed)
        self.store.put(self.post_id, {
            "ghost_post_id": self.post_id,
            "updated_at": "2026-01-01T00:00:00+00:00",
            "syndication_links": {"mastodon": {}, "bluesky": {}},
            "platforms": {"mastodon": {}, "bluesky": {}},
        })

        stats = self._service(client).prune_dead_links()

        entry = self._masto_entry()
        self.assertNotIn("deleted", entry)
        self.assertNotIn("dead_strikes", entry)
        self.assertNotIn("first_seen_dead", entry)
        links = self.store.get(self.post_id)["syndication_links"]["mastodon"]
        self.assertEqual(links["personal"]["post_url"], "https://mastodon.social/@me/1")
        self.assertEqual(stats["resurrected"], 1)

    @patch("social.mastodon_client.Mastodon")
    def test_live_link_untouched(self, mock_mastodon_class):
        client, _ = _make_client(mock_mastodon_class, [{"id": "1"}])
        self._seed_mapping({"status_id": "1", "post_url": "https://mastodon.social/@me/1"})

        stats = self._service(client).prune_dead_links()

        entry = self._masto_entry()
        self.assertNotIn("deleted", entry)
        self.assertNotIn("dead_strikes", entry)
        self.assertEqual(stats["newly_suppressed"], 0)
        self.assertEqual(stats["resurrected"], 0)

    # -- split posts -------------------------------------------------------

    @patch("social.mastodon_client.Mastodon")
    def test_split_one_alive_keeps_account(self, mock_mastodon_class):
        # status "1" gone, status "2" alive
        def side_effect(status_id):
            if status_id == "1":
                raise MastodonNotFoundError("gone")
            return {"id": status_id}
        client, _ = _make_client(mock_mastodon_class, side_effect)
        self._seed_mapping([
            {"status_id": "1", "post_url": "https://mastodon.social/@me/1",
             "is_split": True, "split_index": 0, "total_splits": 2},
            {"status_id": "2", "post_url": "https://mastodon.social/@me/2",
             "is_split": True, "split_index": 1, "total_splits": 2},
        ])
        self._seed_interaction_link()

        stats = self._service(client, threshold=1).prune_dead_links()

        entries = self._masto_entry()
        self.assertTrue(entries[0]["deleted"])      # gone sub-entry flagged
        self.assertNotIn("deleted", entries[1])     # alive sub-entry kept
        # Account not fully dead -> link still presented.
        self.assertIn("personal", self.store.get(self.post_id)["syndication_links"]["mastodon"])
        self.assertEqual(stats["newly_suppressed"], 0)

    # -- regular sync respects the flag ------------------------------------

    @patch("social.mastodon_client.Mastodon")
    def test_sync_skips_already_deleted_account(self, mock_mastodon_class):
        client, mock_api = _make_client(mock_mastodon_class, MastodonNotFoundError("gone"))
        self._seed_mapping({
            "status_id": "1", "post_url": "https://mastodon.social/@me/1", "deleted": True,
        })

        result = self._service(client).sync_post_interactions(self.post_id)

        # Not presented, and we never called the API for the dead status.
        self.assertNotIn("personal", result["syndication_links"]["mastodon"])
        self.assertNotIn("personal", result["platforms"]["mastodon"])
        mock_api.status.assert_not_called()

    # -- recheck backoff for confirmed-dead entries ------------------------

    @patch("social.mastodon_client.Mastodon")
    def test_recently_checked_dead_entry_is_skipped(self, mock_mastodon_class):
        client, mock_api = _make_client(mock_mastodon_class, MastodonNotFoundError("gone"))
        recent = datetime.now(timezone.utc).isoformat()
        self._seed_mapping({
            "status_id": "1", "post_url": "u", "deleted": True,
            "dead_strikes": 2, "first_seen_dead": recent, "last_dead_check": recent,
        })

        stats = self._service(client, recheck_days=7).prune_dead_links()

        # Within backoff window -> no API call, nothing checked.
        mock_api.status.assert_not_called()
        self.assertEqual(stats["checked"], 0)

    @patch("social.mastodon_client.Mastodon")
    def test_stale_dead_entry_is_rechecked(self, mock_mastodon_class):
        client, mock_api = _make_client(mock_mastodon_class, [{"id": "1"}])  # now alive
        old = "2026-01-01T00:00:00+00:00"
        self._seed_mapping({
            "status_id": "1", "post_url": "u", "deleted": True,
            "dead_strikes": 2, "first_seen_dead": old, "last_dead_check": old,
        })

        stats = self._service(client, recheck_days=7).prune_dead_links()

        # Beyond backoff window -> rechecked and resurrected.
        mock_api.status.assert_called_once()
        self.assertNotIn("deleted", self._masto_entry())
        self.assertEqual(stats["resurrected"], 1)

    # -- concurrency: fresh re-read preserves a concurrent syndication -----

    @patch("social.mastodon_client.Mastodon")
    def test_concurrent_account_addition_survives_sweep(self, mock_mastodon_class):
        # While the existence check for 'personal' runs, a syndication adds 'work' to
        # the same post. The sweep must not clobber 'work' when it writes 'personal'.
        def side_effect(status_id):
            mapping = self.store.get_syndication_mapping(self.post_id)
            mapping["platforms"]["mastodon"]["work"] = {"status_id": "9", "post_url": "uw"}
            self.store.put_syndication_mapping(self.post_id, mapping)
            raise MastodonNotFoundError("gone")
        client, _ = _make_client(mock_mastodon_class, side_effect)
        self._seed_mapping({"status_id": "1", "post_url": "u1"})

        self._service(client, threshold=1).prune_dead_links()

        accounts = self.store.get_syndication_mapping(self.post_id)["platforms"]["mastodon"]
        self.assertTrue(accounts["personal"]["deleted"])   # personal flagged dead
        self.assertIn("work", accounts)                    # concurrent add preserved
        self.assertEqual(accounts["work"]["status_id"], "9")


if __name__ == "__main__":
    unittest.main()
