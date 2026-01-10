"""
Unit Tests for Tag-Based Filtering.

This test suite validates tag filtering functionality for account syndication.
"""
import unittest
from unittest.mock import patch, MagicMock

from social.mastodon_client import MastodonClient
from social.bluesky_client import BlueskyClient


class TestTagFiltering(unittest.TestCase):
    """Test suite for tag filtering functionality."""
    
    @patch("config.read_secret_file")
    @patch("social.mastodon_client.Mastodon")
    def test_mastodon_account_with_tags(self, mock_mastodon, mock_read_secret):
        """Test Mastodon account configuration with tags."""
        mock_read_secret.return_value = "test_token"
        
        config = {
            "mastodon": {
                "accounts": [
                    {
                        "name": "tech",
                        "instance_url": "https://mastodon.social",
                        "access_token_file": "/run/secrets/mastodon_tech_access_token",
                        "tags": ["technology", "programming"]
                    }
                ]
            }
        }
        
        clients = MastodonClient.from_config(config)
        
        # Should create one client with tags
        self.assertEqual(len(clients), 1)
        self.assertEqual(clients[0].tags, ["technology", "programming"])
        self.assertEqual(clients[0].account_name, "tech")
    
    @patch("config.read_secret_file")
    @patch("social.mastodon_client.Mastodon")
    def test_mastodon_account_without_tags(self, mock_mastodon, mock_read_secret):
        """Test Mastodon account configuration without tags field."""
        mock_read_secret.return_value = "test_token"
        
        config = {
            "mastodon": {
                "accounts": [
                    {
                        "name": "all",
                        "instance_url": "https://mastodon.social",
                        "access_token_file": "/run/secrets/mastodon_all_access_token"
                    }
                ]
            }
        }
        
        clients = MastodonClient.from_config(config)
        
        # Should create one client with empty tags list (receives all posts)
        self.assertEqual(len(clients), 1)
        self.assertEqual(clients[0].tags, [])
        self.assertEqual(clients[0].account_name, "all")
    
    @patch("config.read_secret_file")
    @patch("social.mastodon_client.Mastodon")
    def test_mastodon_multiple_accounts_mixed_tags(self, mock_mastodon, mock_read_secret):
        """Test multiple Mastodon accounts with different tag configurations."""
        mock_read_secret.return_value = "test_token"
        
        config = {
            "mastodon": {
                "accounts": [
                    {
                        "name": "all",
                        "instance_url": "https://mastodon.social",
                        "access_token_file": "/run/secrets/mastodon_all_access_token",
                        "tags": []  # Explicitly empty
                    },
                    {
                        "name": "tech",
                        "instance_url": "https://fosstodon.org",
                        "access_token_file": "/run/secrets/mastodon_tech_access_token",
                        "tags": ["tech", "programming"]
                    },
                    {
                        "name": "personal",
                        "instance_url": "https://mastodon.social",
                        "access_token_file": "/run/secrets/mastodon_personal_access_token"
                        # No tags field
                    }
                ]
            }
        }
        
        clients = MastodonClient.from_config(config)
        
        # Should create three clients
        self.assertEqual(len(clients), 3)
        self.assertEqual(clients[0].tags, [])  # Explicit empty list
        self.assertEqual(clients[1].tags, ["tech", "programming"])
        self.assertEqual(clients[2].tags, [])  # Default empty list
    
    @patch("config.read_secret_file")
    def test_bluesky_account_with_tags(self, mock_read_secret):
        """Test Bluesky account configuration with tags."""
        mock_read_secret.return_value = "test_password"
        
        config = {
            "bluesky": {
                "accounts": [
                    {
                        "name": "tech",
                        "instance_url": "https://bsky.social",
                        "handle": "tech.bsky.social",
                        "app_password_file": "/run/secrets/bluesky_tech_app_password",
                        "tags": ["coding", "python"]
                    }
                ]
            }
        }
        
        clients = BlueskyClient.from_config(config)
        
        # Should create one client with tags
        self.assertEqual(len(clients), 1)
        self.assertEqual(clients[0].tags, ["coding", "python"])
        self.assertEqual(clients[0].account_name, "tech")
    
    @patch("config.read_secret_file")
    def test_bluesky_account_without_tags(self, mock_read_secret):
        """Test Bluesky account configuration without tags field."""
        mock_read_secret.return_value = "test_password"
        
        config = {
            "bluesky": {
                "accounts": [
                    {
                        "name": "main",
                        "instance_url": "https://bsky.social",
                        "handle": "user.bsky.social",
                        "app_password_file": "/run/secrets/bluesky_main_app_password"
                    }
                ]
            }
        }
        
        clients = BlueskyClient.from_config(config)
        
        # Should create one client with empty tags list
        self.assertEqual(len(clients), 1)
        self.assertEqual(clients[0].tags, [])
    
    def test_tag_matching_logic(self):
        """Test the tag matching logic used in process_events."""
        # Simulate post tags
        post_tags = [
            {"name": "Technology", "slug": "technology"},
            {"name": "Python", "slug": "python"}
        ]
        post_tag_slugs = [tag["slug"].lower() for tag in post_tags]
        
        # Test case 1: Account with no tags (receives all posts)
        client_tags_1 = []
        should_receive_1 = not client_tags_1 or any(
            tag.lower() in [t.lower() for t in client_tags_1] 
            for tag in post_tag_slugs
        )
        self.assertTrue(should_receive_1)
        
        # Test case 2: Account with matching tags
        client_tags_2 = ["technology", "coding"]
        client_tags_2_lower = [t.lower() for t in client_tags_2]
        matching_tags_2 = [tag for tag in post_tag_slugs if tag in client_tags_2_lower]
        should_receive_2 = len(matching_tags_2) > 0
        self.assertTrue(should_receive_2)
        self.assertIn("technology", matching_tags_2)
        
        # Test case 3: Account with non-matching tags
        client_tags_3 = ["business", "work"]
        client_tags_3_lower = [t.lower() for t in client_tags_3]
        matching_tags_3 = [tag for tag in post_tag_slugs if tag in client_tags_3_lower]
        should_receive_3 = len(matching_tags_3) > 0
        self.assertFalse(should_receive_3)
        
        # Test case 4: Account with partial match
        client_tags_4 = ["python", "javascript"]
        client_tags_4_lower = [t.lower() for t in client_tags_4]
        matching_tags_4 = [tag for tag in post_tag_slugs if tag in client_tags_4_lower]
        should_receive_4 = len(matching_tags_4) > 0
        self.assertTrue(should_receive_4)
        self.assertIn("python", matching_tags_4)
    
    def test_case_insensitive_matching(self):
        """Test that tag matching is case-insensitive."""
        post_tag_slugs = ["technology", "python"]
        
        # Different case variations
        client_tags = ["TECHNOLOGY", "Python"]
        client_tags_lower = [t.lower() for t in client_tags]
        matching_tags = [tag for tag in post_tag_slugs if tag in client_tags_lower]
        
        self.assertEqual(len(matching_tags), 2)
        self.assertIn("technology", matching_tags)
        self.assertIn("python", matching_tags)


if __name__ == "__main__":
    unittest.main()
