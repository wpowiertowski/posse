"""
Unit Tests for Split Multi-Image Posts Feature.

This test suite validates the split_multi_image_posts configuration option
that allows accounts to split Ghost posts with multiple images into separate
syndicated posts, each containing one image.

It also tests the #nosplit tag feature that allows bypassing the split behavior
on a per-post basis.

Test Coverage:
    - Configuration loading with split_multi_image_posts option
    - Default behavior (split_multi_image_posts=False)
    - Attribute initialization on client instances
    - Mastodon and Bluesky client support
    - #nosplit tag detection and filtering
    - Bypass split behavior when #nosplit tag is present
"""
import unittest
from unittest.mock import patch, MagicMock

from posse.posse import (
    _has_nosplit_tag,
    _filter_nosplit_tag,
    _format_post_content,
    NOSPLIT_TAG
)
from social.mastodon_client import MastodonClient
from social.bluesky_client import BlueskyClient
from social.base_client import SocialMediaClient


class ConcreteClient(SocialMediaClient):
    """Concrete implementation of SocialMediaClient for testing."""

    def _initialize_api(self):
        """Mock API initialization."""
        self.api = MagicMock()

    def post(self, content, **kwargs):
        """Mock post method."""
        return {"status": "posted"}

    def verify_credentials(self):
        """Mock verify credentials."""
        return {"username": "test_user"}


class TestSplitMultiImagePostsConfig(unittest.TestCase):
    """Test suite for split_multi_image_posts configuration."""

    def test_base_client_default_split_disabled(self):
        """Test that split_multi_image_posts defaults to False."""
        client = ConcreteClient(
            instance_url="https://example.com",
            access_token="test_token"
        )

        self.assertFalse(client.split_multi_image_posts)

    def test_base_client_split_enabled(self):
        """Test that split_multi_image_posts can be enabled."""
        client = ConcreteClient(
            instance_url="https://example.com",
            access_token="test_token",
            split_multi_image_posts=True
        )

        self.assertTrue(client.split_multi_image_posts)

    def test_base_client_split_explicitly_disabled(self):
        """Test that split_multi_image_posts can be explicitly disabled."""
        client = ConcreteClient(
            instance_url="https://example.com",
            access_token="test_token",
            split_multi_image_posts=False
        )

        self.assertFalse(client.split_multi_image_posts)

    @patch("config.read_secret_file")
    @patch("social.mastodon_client.Mastodon")
    def test_mastodon_split_enabled_from_config(self, mock_mastodon, mock_read_secret):
        """Test loading Mastodon config with split_multi_image_posts enabled."""
        mock_read_secret.return_value = "test_token"

        config = {
            "mastodon": {
                "accounts": [
                    {
                        "name": "archive",
                        "instance_url": "https://mastodon.social",
                        "access_token_file": "/run/secrets/mastodon_access_token",
                        "split_multi_image_posts": True
                    }
                ]
            }
        }

        clients = MastodonClient.from_config(config)

        self.assertEqual(len(clients), 1)
        self.assertTrue(clients[0].enabled)
        self.assertTrue(clients[0].split_multi_image_posts)

    @patch("config.read_secret_file")
    @patch("social.mastodon_client.Mastodon")
    def test_mastodon_split_disabled_from_config(self, mock_mastodon, mock_read_secret):
        """Test loading Mastodon config with split_multi_image_posts disabled."""
        mock_read_secret.return_value = "test_token"

        config = {
            "mastodon": {
                "accounts": [
                    {
                        "name": "personal",
                        "instance_url": "https://mastodon.social",
                        "access_token_file": "/run/secrets/mastodon_access_token",
                        "split_multi_image_posts": False
                    }
                ]
            }
        }

        clients = MastodonClient.from_config(config)

        self.assertEqual(len(clients), 1)
        self.assertTrue(clients[0].enabled)
        self.assertFalse(clients[0].split_multi_image_posts)

    @patch("config.read_secret_file")
    @patch("social.mastodon_client.Mastodon")
    def test_mastodon_split_default_from_config(self, mock_mastodon, mock_read_secret):
        """Test loading Mastodon config without split_multi_image_posts (default)."""
        mock_read_secret.return_value = "test_token"

        config = {
            "mastodon": {
                "accounts": [
                    {
                        "name": "personal",
                        "instance_url": "https://mastodon.social",
                        "access_token_file": "/run/secrets/mastodon_access_token"
                    }
                ]
            }
        }

        clients = MastodonClient.from_config(config)

        self.assertEqual(len(clients), 1)
        self.assertTrue(clients[0].enabled)
        # Should default to False
        self.assertFalse(clients[0].split_multi_image_posts)

    @patch("config.read_secret_file")
    @patch("social.bluesky_client.Client")
    def test_bluesky_split_enabled_from_config(self, mock_client, mock_read_secret):
        """Test loading Bluesky config with split_multi_image_posts enabled."""
        mock_read_secret.return_value = "test_password"

        # Mock the ATProto client
        mock_atproto = MagicMock()
        mock_atproto.me.handle = "test.bsky.social"
        mock_atproto.me.did = "did:plc:test123"
        mock_client.return_value = mock_atproto

        config = {
            "bluesky": {
                "accounts": [
                    {
                        "name": "archive",
                        "instance_url": "https://bsky.social",
                        "handle": "test.bsky.social",
                        "app_password_file": "/run/secrets/bluesky_app_password",
                        "split_multi_image_posts": True
                    }
                ]
            }
        }

        clients = BlueskyClient.from_config(config)

        self.assertEqual(len(clients), 1)
        self.assertTrue(clients[0].enabled)
        self.assertTrue(clients[0].split_multi_image_posts)

    @patch("config.read_secret_file")
    @patch("social.bluesky_client.Client")
    def test_bluesky_split_default_from_config(self, mock_client, mock_read_secret):
        """Test loading Bluesky config without split_multi_image_posts (default)."""
        mock_read_secret.return_value = "test_password"

        # Mock the ATProto client
        mock_atproto = MagicMock()
        mock_atproto.me.handle = "test.bsky.social"
        mock_atproto.me.did = "did:plc:test123"
        mock_client.return_value = mock_atproto

        config = {
            "bluesky": {
                "accounts": [
                    {
                        "name": "main",
                        "instance_url": "https://bsky.social",
                        "handle": "test.bsky.social",
                        "app_password_file": "/run/secrets/bluesky_app_password"
                    }
                ]
            }
        }

        clients = BlueskyClient.from_config(config)

        self.assertEqual(len(clients), 1)
        self.assertTrue(clients[0].enabled)
        # Should default to False
        self.assertFalse(clients[0].split_multi_image_posts)

    @patch("config.read_secret_file")
    @patch("social.mastodon_client.Mastodon")
    def test_multi_account_mixed_split_settings(self, mock_mastodon, mock_read_secret):
        """Test multi-account config with mixed split_multi_image_posts settings."""
        def mock_read_token(filepath):
            if "personal" in filepath:
                return "personal_token"
            elif "archive" in filepath:
                return "archive_token"
            return None

        mock_read_secret.side_effect = mock_read_token

        config = {
            "mastodon": {
                "accounts": [
                    {
                        "name": "personal",
                        "instance_url": "https://mastodon.social",
                        "access_token_file": "/run/secrets/mastodon_personal_access_token",
                        "split_multi_image_posts": False
                    },
                    {
                        "name": "archive",
                        "instance_url": "https://mastodon.archive.org",
                        "access_token_file": "/run/secrets/mastodon_archive_access_token",
                        "split_multi_image_posts": True
                    }
                ]
            }
        }

        clients = MastodonClient.from_config(config)

        # Should return list with two clients
        self.assertEqual(len(clients), 2)

        # First account should have split disabled
        self.assertTrue(clients[0].enabled)
        self.assertEqual(clients[0].account_name, "personal")
        self.assertFalse(clients[0].split_multi_image_posts)

        # Second account should have split enabled
        self.assertTrue(clients[1].enabled)
        self.assertEqual(clients[1].account_name, "archive")
        self.assertTrue(clients[1].split_multi_image_posts)


class TestSplitMultiImagePostsBehavior(unittest.TestCase):
    """Test suite for split_multi_image_posts posting behavior."""

    def test_client_with_split_enabled_has_attribute(self):
        """Test that client with split enabled has the correct attribute."""
        client = ConcreteClient(
            instance_url="https://example.com",
            access_token="test_token",
            split_multi_image_posts=True
        )

        # Check that the attribute exists and is True
        self.assertTrue(hasattr(client, 'split_multi_image_posts'))
        self.assertTrue(client.split_multi_image_posts)

    def test_client_preserves_other_attributes_with_split(self):
        """Test that enabling split doesn't affect other client attributes."""
        client = ConcreteClient(
            instance_url="https://example.com",
            access_token="test_token",
            account_name="test_account",
            tags=["tech", "python"],
            max_post_length=450,
            split_multi_image_posts=True
        )

        # Verify all attributes are preserved
        self.assertEqual(client.instance_url, "https://example.com")
        self.assertEqual(client.access_token, "test_token")
        self.assertEqual(client.account_name, "test_account")
        self.assertEqual(client.tags, ["tech", "python"])
        self.assertEqual(client.max_post_length, 450)
        self.assertTrue(client.split_multi_image_posts)


class TestNosplitTagDetection(unittest.TestCase):
    """Test suite for #nosplit tag detection and filtering."""

    def test_has_nosplit_tag_returns_true_when_present(self):
        """Test that _has_nosplit_tag returns True when #nosplit is in tags."""
        tags = [
            {"name": "#photography", "slug": "hash-photography"},
            {"name": "#nosplit", "slug": "hash-nosplit"},
            {"name": "#posse", "slug": "hash-posse"}
        ]
        self.assertTrue(_has_nosplit_tag(tags))

    def test_has_nosplit_tag_returns_false_when_absent(self):
        """Test that _has_nosplit_tag returns False when #nosplit is not in tags."""
        tags = [
            {"name": "#photography", "slug": "hash-photography"},
            {"name": "#posse", "slug": "hash-posse"}
        ]
        self.assertFalse(_has_nosplit_tag(tags))

    def test_has_nosplit_tag_case_insensitive(self):
        """Test that #nosplit detection is case-insensitive."""
        tags_upper = [{"name": "#NOSPLIT", "slug": "hash-nosplit"}]
        tags_mixed = [{"name": "#NoSplit", "slug": "hash-nosplit"}]

        self.assertTrue(_has_nosplit_tag(tags_upper))
        self.assertTrue(_has_nosplit_tag(tags_mixed))

    def test_has_nosplit_tag_empty_tags(self):
        """Test that _has_nosplit_tag returns False for empty tags list."""
        self.assertFalse(_has_nosplit_tag([]))

    def test_has_nosplit_tag_handles_missing_name(self):
        """Test that _has_nosplit_tag handles tags without name field."""
        tags = [
            {"slug": "hash-nosplit"},  # Missing 'name' field
            {"name": "#photography", "slug": "hash-photography"}
        ]
        self.assertFalse(_has_nosplit_tag(tags))

    def test_filter_nosplit_tag_removes_tag(self):
        """Test that _filter_nosplit_tag removes #nosplit from tags."""
        tags = [
            {"name": "#photography", "slug": "hash-photography"},
            {"name": "#nosplit", "slug": "hash-nosplit"},
            {"name": "#posse", "slug": "hash-posse"}
        ]
        filtered = _filter_nosplit_tag(tags)

        self.assertEqual(len(filtered), 2)
        tag_names = [t["name"] for t in filtered]
        self.assertIn("#photography", tag_names)
        self.assertIn("#posse", tag_names)
        self.assertNotIn("#nosplit", tag_names)

    def test_filter_nosplit_tag_case_insensitive(self):
        """Test that _filter_nosplit_tag is case-insensitive."""
        tags = [
            {"name": "#photography", "slug": "hash-photography"},
            {"name": "#NOSPLIT", "slug": "hash-nosplit"}
        ]
        filtered = _filter_nosplit_tag(tags)

        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]["name"], "#photography")

    def test_filter_nosplit_tag_preserves_other_tags(self):
        """Test that _filter_nosplit_tag doesn't affect tags without #nosplit."""
        tags = [
            {"name": "#photography", "slug": "hash-photography"},
            {"name": "#travel", "slug": "hash-travel"}
        ]
        filtered = _filter_nosplit_tag(tags)

        self.assertEqual(len(filtered), 2)
        self.assertEqual(filtered, tags)

    def test_filter_nosplit_tag_empty_list(self):
        """Test that _filter_nosplit_tag handles empty list."""
        filtered = _filter_nosplit_tag([])
        self.assertEqual(filtered, [])


class TestNosplitTagInPostContent(unittest.TestCase):
    """Test suite for #nosplit tag exclusion from formatted post content."""

    def test_nosplit_tag_excluded_from_hashtags(self):
        """Test that #nosplit is excluded from formatted post hashtags."""
        tags = [
            {"name": "#photography", "slug": "hash-photography"},
            {"name": "#nosplit", "slug": "hash-nosplit"}
        ]
        content = _format_post_content(
            post_title="Test Post",
            post_url="https://example.com/test",
            excerpt="This is a test excerpt",
            tags=tags,
            max_length=500
        )

        self.assertIn("#photography", content)
        self.assertIn("#posse", content)  # Always added
        self.assertNotIn("#nosplit", content)

    def test_nosplit_tag_excluded_case_insensitive(self):
        """Test that #nosplit exclusion is case-insensitive."""
        tags = [
            {"name": "#photography", "slug": "hash-photography"},
            {"name": "#NOSPLIT", "slug": "hash-nosplit"}
        ]
        content = _format_post_content(
            post_title="Test Post",
            post_url="https://example.com/test",
            excerpt="This is a test excerpt",
            tags=tags,
            max_length=500
        )

        self.assertNotIn("#nosplit", content.lower())

    def test_content_without_nosplit_tag_unchanged(self):
        """Test that content without #nosplit tag includes all hashtags."""
        tags = [
            {"name": "#photography", "slug": "hash-photography"},
            {"name": "#travel", "slug": "hash-travel"}
        ]
        content = _format_post_content(
            post_title="Test Post",
            post_url="https://example.com/test",
            excerpt="This is a test excerpt",
            tags=tags,
            max_length=500
        )

        self.assertIn("#photography", content)
        self.assertIn("#travel", content)
        self.assertIn("#posse", content)

    def test_nosplit_constant_value(self):
        """Test that NOSPLIT_TAG constant has expected value."""
        self.assertEqual(NOSPLIT_TAG, "#nosplit")


if __name__ == "__main__":
    unittest.main()
