"""
Unit Tests for Interaction Discovery Feature.

This test suite validates the syndication mapping discovery functionality
that automatically discovers mappings by searching recent social media posts
for links back to Ghost posts.

Test Coverage:
    - MastodonClient.get_recent_posts()
    - BlueskyClient.get_recent_posts()
    - InteractionSyncService.discover_syndication_mapping()
    - Preservation of existing mappings during discovery
    - /api/interactions endpoint discovery flow

Testing Strategy:
    Tests use mocked API responses to verify discovery logic without
    making actual API calls to Mastodon or Bluesky.

Running Tests:
    $ PYTHONPATH=src python -m unittest tests.test_interaction_discovery -v
"""
import unittest
from unittest.mock import patch, MagicMock, mock_open, call
import json
import tempfile
import os
import shutil

from social.mastodon_client import MastodonClient
from social.bluesky_client import BlueskyClient
from interactions.interaction_sync import InteractionSyncService, store_syndication_mapping
from interactions.storage import InteractionDataStore


class TestMastodonGetRecentPosts(unittest.TestCase):
    """Test suite for MastodonClient.get_recent_posts()."""

    @patch("social.mastodon_client.Mastodon")
    def test_get_recent_posts_success(self, mock_mastodon_class):
        """Test successfully retrieving recent posts from Mastodon."""
        # Mock Mastodon API
        mock_api = MagicMock()
        mock_mastodon_class.return_value = mock_api

        # Mock account verification
        mock_api.account_verify_credentials.return_value = {
            'id': '12345',
            'username': 'testuser'
        }

        # Mock account_statuses response
        mock_statuses = [
            {
                'id': '111',
                'url': 'https://mastodon.social/@testuser/111',
                'content': '<p>Test post with <a href="https://blog.example.com/post1/">link</a></p>',
                'created_at': '2026-02-01T10:00:00.000Z'
            },
            {
                'id': '222',
                'url': 'https://mastodon.social/@testuser/222',
                'content': '<p>Another test post</p>',
                'created_at': '2026-02-01T09:00:00.000Z'
            }
        ]
        mock_api.account_statuses.return_value = mock_statuses

        # Create client
        client = MastodonClient(
            instance_url="https://mastodon.social",
            access_token="test_token",
            account_name="test"
        )

        # Test get_recent_posts
        posts = client.get_recent_posts(limit=20)

        # Verify results
        self.assertEqual(len(posts), 2)
        self.assertEqual(posts[0]['id'], '111')
        self.assertEqual(posts[0]['url'], 'https://mastodon.social/@testuser/111')
        self.assertIn('https://blog.example.com/post1/', posts[0]['content'])

        # Verify API calls
        # Note: account_verify_credentials is called twice - once during __init__, once in get_recent_posts()
        self.assertEqual(mock_api.account_verify_credentials.call_count, 2)
        mock_api.account_statuses.assert_called_once_with(
            id='12345',
            limit=20,
            exclude_replies=False,
            exclude_reblogs=True
        )

    @patch("social.mastodon_client.Mastodon")
    def test_get_recent_posts_client_disabled(self, mock_mastodon_class):
        """Test get_recent_posts when client is disabled."""
        # Create disabled client
        client = MastodonClient(
            instance_url="https://mastodon.social",
            access_token=None,  # No token = disabled
            account_name="test",
            config_enabled=False
        )

        # Test get_recent_posts
        posts = client.get_recent_posts(limit=20)

        # Verify returns empty list
        self.assertEqual(posts, [])

    @patch("social.mastodon_client.Mastodon")
    def test_get_recent_posts_api_error(self, mock_mastodon_class):
        """Test get_recent_posts handles API errors gracefully."""
        # Mock Mastodon API
        mock_api = MagicMock()
        mock_mastodon_class.return_value = mock_api

        # Mock account verification
        mock_api.account_verify_credentials.return_value = {'id': '12345'}

        # Mock API error
        from mastodon import MastodonError
        mock_api.account_statuses.side_effect = MastodonError("API Error")

        # Create client
        client = MastodonClient(
            instance_url="https://mastodon.social",
            access_token="test_token",
            account_name="test"
        )

        # Test get_recent_posts
        posts = client.get_recent_posts(limit=20)

        # Verify returns empty list on error
        self.assertEqual(posts, [])


class TestBlueskyGetRecentPosts(unittest.TestCase):
    """Test suite for BlueskyClient.get_recent_posts()."""

    @patch("social.bluesky_client.Client")
    def test_get_recent_posts_success(self, mock_client_class):
        """Test successfully retrieving recent posts from Bluesky."""
        # Mock ATProto Client
        mock_api = MagicMock()
        mock_client_class.return_value = mock_api

        # Mock session
        mock_api.me = MagicMock()
        mock_api.me.did = 'did:plc:test123'

        # Mock feed response
        mock_post1 = MagicMock()
        mock_post1.uri = 'at://did:plc:test123/app.bsky.feed.post/abc123'
        mock_post1.cid = 'cid123'
        mock_post1.record.text = 'Test post https://blog.example.com/post1/'
        mock_post1.record.created_at = '2026-02-01T10:00:00.000Z'
        mock_post1.author.handle = 'testuser.bsky.social'

        mock_post2 = MagicMock()
        mock_post2.uri = 'at://did:plc:test123/app.bsky.feed.post/def456'
        mock_post2.cid = 'cid456'
        mock_post2.record.text = 'Another test post'
        mock_post2.record.created_at = '2026-02-01T09:00:00.000Z'
        mock_post2.author.handle = 'testuser.bsky.social'

        mock_feed_item1 = MagicMock()
        mock_feed_item1.post = mock_post1

        mock_feed_item2 = MagicMock()
        mock_feed_item2.post = mock_post2

        mock_feed_response = MagicMock()
        mock_feed_response.feed = [mock_feed_item1, mock_feed_item2]

        mock_api.app.bsky.feed.get_author_feed.return_value = mock_feed_response

        # Create client
        client = BlueskyClient(
            instance_url="https://bsky.social",
            handle="testuser.bsky.social",
            app_password="test_password",
            account_name="test"
        )

        # Test get_recent_posts
        posts = client.get_recent_posts(limit=30)

        # Verify results
        self.assertEqual(len(posts), 2)
        self.assertEqual(posts[0]['uri'], 'at://did:plc:test123/app.bsky.feed.post/abc123')
        self.assertIn('https://blog.example.com/post1/', posts[0]['text'])
        self.assertEqual(posts[0]['url'], 'https://bsky.app/profile/testuser.bsky.social/post/abc123')

        # Verify API calls
        mock_api.app.bsky.feed.get_author_feed.assert_called_once()

    @patch("social.bluesky_client.Client")
    def test_get_recent_posts_client_disabled(self, mock_client_class):
        """Test get_recent_posts when client is disabled."""
        # Create disabled client
        client = BlueskyClient(
            instance_url="https://bsky.social",
            handle="testuser.bsky.social",
            app_password=None,  # No password = disabled
            account_name="test",
            config_enabled=False
        )

        # Test get_recent_posts
        posts = client.get_recent_posts(limit=30)

        # Verify returns empty list
        self.assertEqual(posts, [])


class TestDiscoverSyndicationMapping(unittest.TestCase):
    """Test suite for InteractionSyncService.discover_syndication_mapping()."""

    def setUp(self):
        """Set up test fixtures."""
        # Create temporary directory for test data
        self.test_dir = tempfile.mkdtemp()
        self.storage_path = os.path.join(self.test_dir, "interactions")
        self.mappings_path = os.path.join(self.test_dir, "mappings")
        os.makedirs(self.storage_path, exist_ok=True)
        os.makedirs(self.mappings_path, exist_ok=True)

    def tearDown(self):
        """Clean up test fixtures."""
        shutil.rmtree(self.test_dir)

    @patch("social.mastodon_client.Mastodon")
    def test_discover_mapping_mastodon_found(self, mock_mastodon_class):
        """Test discovering a mapping from Mastodon posts."""
        # Mock Mastodon API
        mock_api = MagicMock()
        mock_mastodon_class.return_value = mock_api

        mock_api.account_verify_credentials.return_value = {
            'id': '12345',
            'username': 'testuser'
        }

        # Mock posts with Ghost post URL
        mock_api.account_statuses.return_value = [
            {
                'id': '111',
                'url': 'https://mastodon.social/@testuser/111',
                'content': '<p>Check out my new post! <a href="https://blog.example.com/my-post/">Read here</a></p>',
                'created_at': '2026-02-01T10:00:00.000Z'
            }
        ]

        # Create Mastodon client
        mastodon_client = MastodonClient(
            instance_url="https://mastodon.social",
            access_token="test_token",
            account_name="personal"
        )

        # Create sync service
        sync_service = InteractionSyncService(
            mastodon_clients=[mastodon_client],
            bluesky_clients=[],
            storage_path=self.storage_path,
        )

        # Test discovery
        found = sync_service.discover_syndication_mapping(
            ghost_post_id="abc123",
            ghost_post_url="https://blog.example.com/my-post/",
            max_posts_to_search=50
        )

        # Verify mapping was found
        self.assertTrue(found)

        # Verify mapping contents were stored in SQLite
        mapping = InteractionDataStore(self.storage_path).get_syndication_mapping("abc123")
        self.assertIsNotNone(mapping)

        self.assertEqual(mapping['ghost_post_id'], 'abc123')
        self.assertIn('personal', mapping['platforms']['mastodon'])
        self.assertEqual(
            mapping['platforms']['mastodon']['personal']['status_id'],
            '111'
        )

    @patch("social.bluesky_client.Client")
    def test_discover_mapping_bluesky_found(self, mock_client_class):
        """Test discovering a mapping from Bluesky posts."""
        # Mock ATProto Client
        mock_api = MagicMock()
        mock_client_class.return_value = mock_api

        mock_api.me = MagicMock()
        mock_api.me.did = 'did:plc:test123'

        # Mock posts with Ghost post URL
        mock_post = MagicMock()
        mock_post.uri = 'at://did:plc:test123/app.bsky.feed.post/xyz789'
        mock_post.cid = 'cid789'
        mock_post.record.text = 'New blog post! https://blog.example.com/my-post/ Check it out!'
        mock_post.record.created_at = '2026-02-01T10:00:00.000Z'
        mock_post.author.handle = 'testuser.bsky.social'

        mock_feed_item = MagicMock()
        mock_feed_item.post = mock_post

        mock_feed_response = MagicMock()
        mock_feed_response.feed = [mock_feed_item]

        mock_api.app.bsky.feed.get_author_feed.return_value = mock_feed_response

        # Create Bluesky client
        bluesky_client = BlueskyClient(
            instance_url="https://bsky.social",
            handle="testuser.bsky.social",
            app_password="test_password",
            account_name="main"
        )

        # Create sync service
        sync_service = InteractionSyncService(
            mastodon_clients=[],
            bluesky_clients=[bluesky_client],
            storage_path=self.storage_path,
        )

        # Test discovery
        found = sync_service.discover_syndication_mapping(
            ghost_post_id="def456",
            ghost_post_url="https://blog.example.com/my-post/",
            max_posts_to_search=50
        )

        # Verify mapping was found
        self.assertTrue(found)

        # Verify mapping contents were stored in SQLite
        mapping = InteractionDataStore(self.storage_path).get_syndication_mapping("def456")
        self.assertIsNotNone(mapping)

        self.assertEqual(mapping['ghost_post_id'], 'def456')
        self.assertIn('main', mapping['platforms']['bluesky'])
        self.assertEqual(
            mapping['platforms']['bluesky']['main']['post_uri'],
            'at://did:plc:test123/app.bsky.feed.post/xyz789'
        )

    @patch("social.mastodon_client.Mastodon")
    def test_discover_mapping_not_found(self, mock_mastodon_class):
        """Test discovery when no matching posts are found."""
        # Mock Mastodon API
        mock_api = MagicMock()
        mock_mastodon_class.return_value = mock_api

        mock_api.account_verify_credentials.return_value = {'id': '12345'}

        # Mock posts WITHOUT the Ghost post URL
        mock_api.account_statuses.return_value = [
            {
                'id': '111',
                'url': 'https://mastodon.social/@testuser/111',
                'content': '<p>Random post about something else</p>',
                'created_at': '2026-02-01T10:00:00.000Z'
            }
        ]

        # Create Mastodon client
        mastodon_client = MastodonClient(
            instance_url="https://mastodon.social",
            access_token="test_token",
            account_name="personal"
        )

        # Create sync service
        sync_service = InteractionSyncService(
            mastodon_clients=[mastodon_client],
            bluesky_clients=[],
            storage_path=self.storage_path,
        )

        # Test discovery
        found = sync_service.discover_syndication_mapping(
            ghost_post_id="notfound123",
            ghost_post_url="https://blog.example.com/nonexistent-post/",
            max_posts_to_search=50
        )

        # Verify mapping was NOT found
        self.assertFalse(found)

        # Verify no mapping was created
        mapping = InteractionDataStore(self.storage_path).get_syndication_mapping("notfound123")
        self.assertIsNone(mapping)

    @patch("social.mastodon_client.Mastodon")
    def test_discover_mapping_preserves_existing(self, mock_mastodon_class):
        """Test that discovery preserves existing mappings."""
        # Create existing mapping with one account
        existing_mapping = {
            "ghost_post_id": "existing123",
            "ghost_post_url": "https://blog.example.com/my-post/",
            "syndicated_at": "2026-01-01T00:00:00.000Z",
            "platforms": {
                "mastodon": {
                    "personal": {
                        "status_id": "999",
                        "post_url": "https://mastodon.social/@testuser/999"
                    }
                }
            }
        }

        InteractionDataStore(self.storage_path).put_syndication_mapping("existing123", existing_mapping)

        # Mock Mastodon API
        mock_api = MagicMock()
        mock_mastodon_class.return_value = mock_api

        mock_api.account_verify_credentials.return_value = {
            'id': '12345',
            'username': 'testuser'
        }

        # Mock posts - should not be searched since account already exists
        mock_api.account_statuses.return_value = []

        # Create Mastodon client (same account name as existing)
        mastodon_client = MastodonClient(
            instance_url="https://mastodon.social",
            access_token="test_token",
            account_name="personal"  # Already exists in mapping
        )

        # Create sync service
        sync_service = InteractionSyncService(
            mastodon_clients=[mastodon_client],
            bluesky_clients=[],
            storage_path=self.storage_path,
        )

        # Test discovery
        found = sync_service.discover_syndication_mapping(
            ghost_post_id="existing123",
            ghost_post_url="https://blog.example.com/my-post/",
            max_posts_to_search=50
        )

        # Verify no new mapping found (existing was preserved)
        self.assertFalse(found)

        # Verify account_statuses was NOT called (account was skipped)
        mock_api.account_statuses.assert_not_called()

        # Verify existing mapping is still intact
        final_mapping = InteractionDataStore(self.storage_path).get_syndication_mapping("existing123")
        self.assertIsNotNone(final_mapping)
        self.assertEqual(final_mapping['platforms']['mastodon']['personal']['status_id'], '999')

    @patch("social.mastodon_client.Mastodon")
    def test_discover_mapping_preserves_existing_from_sqlite(self, mock_mastodon_class):
        """Test that discovery preserves existing mappings already stored in SQLite."""
        legacy_mapping = {
            "ghost_post_id": "existing-legacy-123",
            "ghost_post_url": "https://blog.example.com/my-post/",
            "syndicated_at": "2026-01-01T00:00:00.000Z",
            "platforms": {
                "mastodon": {
                    "personal": {
                        "status_id": "999",
                        "post_url": "https://mastodon.social/@testuser/999"
                    }
                }
            }
        }

        InteractionDataStore(self.storage_path).put_syndication_mapping(
            "existing-legacy-123",
            legacy_mapping,
        )

        mock_api = MagicMock()
        mock_mastodon_class.return_value = mock_api
        mock_api.account_verify_credentials.return_value = {
            'id': '12345',
            'username': 'testuser'
        }

        # Should be skipped because mapping already exists for this account,
        # even though the filename is legacy/slug-based.
        mock_api.account_statuses.return_value = []

        mastodon_client = MastodonClient(
            instance_url="https://mastodon.social",
            access_token="test_token",
            account_name="personal"
        )

        sync_service = InteractionSyncService(
            mastodon_clients=[mastodon_client],
            bluesky_clients=[],
            storage_path=self.storage_path,
        )

        found = sync_service.discover_syndication_mapping(
            ghost_post_id="existing-legacy-123",
            ghost_post_url="https://blog.example.com/my-post/",
            max_posts_to_search=50
        )

        self.assertFalse(found)
        mock_api.account_statuses.assert_not_called()

        final_mapping = InteractionDataStore(self.storage_path).get_syndication_mapping("existing-legacy-123")
        self.assertIsNotNone(final_mapping)
        self.assertEqual(final_mapping['platforms']['mastodon']['personal']['status_id'], '999')


class TestStoreSyndicationMappingPreservation(unittest.TestCase):
    """Test suite for store_syndication_mapping() data preservation."""

    def setUp(self):
        """Set up test fixtures."""
        self.test_dir = tempfile.mkdtemp()
        self.storage_path = os.path.join(self.test_dir, "interactions")
        self.mappings_path = os.path.join(self.test_dir, "mappings")
        os.makedirs(self.storage_path, exist_ok=True)
        os.makedirs(self.mappings_path, exist_ok=True)

    def tearDown(self):
        """Clean up test fixtures."""
        shutil.rmtree(self.test_dir)

    def test_store_mapping_preserves_other_platforms(self):
        """Test that storing a mapping preserves data from other platforms."""
        # Create existing mapping with Mastodon
        existing_mapping = {
            "ghost_post_id": "test123",
            "ghost_post_url": "https://blog.example.com/post/",
            "syndicated_at": "2026-01-01T00:00:00.000Z",
            "platforms": {
                "mastodon": {
                    "personal": {
                        "status_id": "111",
                        "post_url": "https://mastodon.social/@user/111"
                    }
                }
            }
        }

        InteractionDataStore(self.storage_path).put_syndication_mapping("test123", existing_mapping)

        # Add Bluesky mapping
        store_syndication_mapping(
            ghost_post_id="test123",
            ghost_post_url="https://blog.example.com/post/",
            platform="bluesky",
            account_name="main",
            post_data={
                "post_uri": "at://did:plc:test/app.bsky.feed.post/abc",
                "post_url": "https://bsky.app/profile/user/post/abc"
            },
            storage_path=self.storage_path,
        )

        # Verify both platforms exist
        final_mapping = InteractionDataStore(self.storage_path).get_syndication_mapping("test123")
        self.assertIsNotNone(final_mapping)

        self.assertIn("mastodon", final_mapping["platforms"])
        self.assertIn("bluesky", final_mapping["platforms"])
        self.assertEqual(final_mapping["platforms"]["mastodon"]["personal"]["status_id"], "111")
        self.assertEqual(final_mapping["platforms"]["bluesky"]["main"]["post_uri"], "at://did:plc:test/app.bsky.feed.post/abc")

    def test_store_mapping_preserves_other_accounts(self):
        """Test that storing a mapping preserves data from other accounts on same platform."""
        # Create existing mapping with two Mastodon accounts
        existing_mapping = {
            "ghost_post_id": "test456",
            "ghost_post_url": "https://blog.example.com/post/",
            "syndicated_at": "2026-01-01T00:00:00.000Z",
            "platforms": {
                "mastodon": {
                    "personal": {
                        "status_id": "111",
                        "post_url": "https://mastodon.social/@user/111"
                    },
                    "photos": {
                        "status_id": "222",
                        "post_url": "https://pixelfed.social/@user/222"
                    }
                }
            }
        }

        InteractionDataStore(self.storage_path).put_syndication_mapping("test456", existing_mapping)

        # Add third Mastodon account
        store_syndication_mapping(
            ghost_post_id="test456",
            ghost_post_url="https://blog.example.com/post/",
            platform="mastodon",
            account_name="archive",
            post_data={
                "status_id": "333",
                "post_url": "https://mastodon.archive/@user/333"
            },
            storage_path=self.storage_path,
        )

        # Verify all three accounts exist
        final_mapping = InteractionDataStore(self.storage_path).get_syndication_mapping("test456")
        self.assertIsNotNone(final_mapping)

        self.assertEqual(len(final_mapping["platforms"]["mastodon"]), 3)
        self.assertIn("personal", final_mapping["platforms"]["mastodon"])
        self.assertIn("photos", final_mapping["platforms"]["mastodon"])
        self.assertIn("archive", final_mapping["platforms"]["mastodon"])

    def test_store_mapping_persists_to_sqlite(self):
        """Test that storing a mapping writes to SQLite."""
        store_syndication_mapping(
            ghost_post_id="db123",
            ghost_post_url="https://blog.example.com/post/",
            platform="mastodon",
            account_name="personal",
            post_data={
                "status_id": "444",
                "post_url": "https://mastodon.social/@user/444"
            },
            storage_path=self.storage_path
        )
        data_store = InteractionDataStore(self.storage_path)
        mapping = data_store.get_syndication_mapping("db123")

        self.assertIsNotNone(mapping)
        self.assertEqual(mapping["platforms"]["mastodon"]["personal"]["status_id"], "444")


if __name__ == '__main__':
    unittest.main()
