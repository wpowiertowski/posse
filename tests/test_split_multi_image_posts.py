"""
Unit Tests for Split Multi-Image Posts Feature.

This test suite validates the split_multi_image_posts configuration option
that allows accounts to split Ghost posts with multiple images into separate
syndicated posts, each containing one image.

Test Coverage:
    - Configuration loading with split_multi_image_posts option
    - Default behavior (split_multi_image_posts=False)
    - Attribute initialization on client instances
    - Mastodon and Bluesky client support
"""
import unittest
from unittest.mock import patch, MagicMock

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


if __name__ == "__main__":
    unittest.main()
