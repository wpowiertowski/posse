"""
Unit Tests for Multi-Account Configuration.

This test suite validates multi-account configuration loading and initialization.
"""
import unittest
from unittest.mock import patch, MagicMock

from mastodon_client.mastodon_client import MastodonClient


class TestMultiAccountConfiguration(unittest.TestCase):
    """Test suite for multi-account configuration."""
    
    @patch('config.read_secret_file')
    @patch('mastodon_client.mastodon_client.Mastodon')
    def test_multi_account_config(self, mock_mastodon, mock_read_secret):
        """Test loading multi-account configuration."""
        # Mock different tokens for different accounts
        def mock_read_token(filepath):
            if 'personal' in filepath:
                return "personal_token"
            elif 'work' in filepath:
                return "work_token"
            return None
        
        mock_read_secret.side_effect = mock_read_token
        
        config = {
            'mastodon': {
                'accounts': [
                    {
                        'name': 'personal',
                        'instance_url': 'https://mastodon.social',
                        'access_token_file': '/run/secrets/mastodon_personal_access_token',
                        'filters': {'tags': ['personal']}
                    },
                    {
                        'name': 'work',
                        'instance_url': 'https://fosstodon.org',
                        'access_token_file': '/run/secrets/mastodon_work_access_token',
                        'filters': {'tags': ['work'], 'exclude_tags': ['personal']}
                    }
                ]
            }
        }
        
        clients = MastodonClient.from_config(config)
        
        # Should return list with two clients
        self.assertEqual(len(clients), 2)
        
        # Check first account
        self.assertTrue(clients[0].enabled)
        self.assertEqual(clients[0].account_name, "personal")
        self.assertEqual(clients[0].instance_url, "https://mastodon.social")
        self.assertEqual(clients[0].access_token, "personal_token")
        self.assertEqual(clients[0].filters, {'tags': ['personal']})
        
        # Check second account
        self.assertTrue(clients[1].enabled)
        self.assertEqual(clients[1].account_name, "work")
        self.assertEqual(clients[1].instance_url, "https://fosstodon.org")
        self.assertEqual(clients[1].access_token, "work_token")
        self.assertEqual(clients[1].filters, {'tags': ['work'], 'exclude_tags': ['personal']})
    
    @patch('config.read_secret_file')
    @patch('mastodon_client.mastodon_client.Mastodon')
    def test_multi_account_with_empty_filters(self, mock_mastodon, mock_read_secret):
        """Test multi-account with empty filters (matches all posts)."""
        mock_read_secret.return_value = "test_token"
        
        config = {
            'mastodon': {
                'accounts': [
                    {
                        'name': 'all_posts',
                        'instance_url': 'https://mastodon.social',
                        'access_token_file': '/run/secrets/mastodon_all_access_token',
                        'filters': {}  # Empty filters
                    }
                ]
            }
        }
        
        clients = MastodonClient.from_config(config)
        
        self.assertEqual(len(clients), 1)
        self.assertTrue(clients[0].enabled)
        self.assertEqual(clients[0].filters, {})
    
    @patch('config.read_secret_file')
    @patch('mastodon_client.mastodon_client.Mastodon')
    def test_multi_account_missing_token(self, mock_mastodon, mock_read_secret):
        """Test multi-account with missing access token."""
        mock_read_secret.return_value = None
        
        config = {
            'mastodon': {
                'accounts': [
                    {
                        'name': 'missing_token',
                        'instance_url': 'https://mastodon.social',
                        'access_token_file': '/run/secrets/nonexistent_token'
                    }
                ]
            }
        }
        
        clients = MastodonClient.from_config(config)
        
        # Should create client but it should be disabled
        self.assertEqual(len(clients), 1)
        self.assertFalse(clients[0].enabled)
    
    @patch('config.read_secret_file')
    @patch('mastodon_client.mastodon_client.Mastodon')
    def test_multi_account_no_filters_key(self, mock_mastodon, mock_read_secret):
        """Test multi-account when filters key is omitted."""
        mock_read_secret.return_value = "test_token"
        
        config = {
            'mastodon': {
                'accounts': [
                    {
                        'name': 'no_filters',
                        'instance_url': 'https://mastodon.social',
                        'access_token_file': '/run/secrets/mastodon_token'
                        # No 'filters' key
                    }
                ]
            }
        }
        
        clients = MastodonClient.from_config(config)
        
        self.assertEqual(len(clients), 1)
        self.assertTrue(clients[0].enabled)
        # Should default to empty dict
        self.assertEqual(clients[0].filters, {})
    
    @patch('config.read_secret_file')
    @patch('mastodon_client.mastodon_client.Mastodon')
    def test_empty_accounts_list(self, mock_mastodon, mock_read_secret):
        """Test multi-account config with empty accounts list."""
        config = {
            'mastodon': {
                'accounts': []
            }
        }
        
        clients = MastodonClient.from_config(config)
        
        # Should return empty list
        self.assertEqual(len(clients), 0)
    
    @patch('config.read_secret_file')
    @patch('mastodon_client.mastodon_client.Mastodon')
    def test_single_account_config(self, mock_mastodon, mock_read_secret):
        """Test configuration with a single account."""
        mock_read_secret.return_value = "test_token"
        
        config = {
            'mastodon': {
                'accounts': [
                    {
                        'name': 'main',
                        'instance_url': 'https://mastodon.social',
                        'access_token_file': '/run/secrets/mastodon_access_token',
                        'filters': {}
                    }
                ]
            }
        }
        
        clients = MastodonClient.from_config(config)
        
        # Should return list with one client
        self.assertEqual(len(clients), 1)
        self.assertTrue(clients[0].enabled)
        self.assertEqual(clients[0].instance_url, "https://mastodon.social")
        self.assertEqual(clients[0].access_token, "test_token")


if __name__ == '__main__':
    unittest.main()
