"""
Integration Tests for Mastodon Client Module.

This test suite validates the Mastodon authentication functionality
by testing login with provided credentials from Docker secrets.

Test Coverage:
    - Login with credentials from secrets

Testing Strategy:
    Tests use mocked credentials from Docker secrets to verify
    authentication initialization works correctly.

Running Tests:
    $ PYTHONPATH=src python -m unittest tests.test_mastodon -v
"""
import unittest
from unittest.mock import patch

from mastodon_client.mastodon_client import MastodonClient


class TestMastodonClient(unittest.TestCase):
    """Test suite for MastodonClient class."""
    
    @patch('config.read_secret_file')
    @patch('mastodon_client.mastodon_client.Mastodon')
    def test_login_with_provided_secrets(self, mock_mastodon, mock_read_secret):
        """Test login with credentials loaded from secrets."""
        # Mock secret file reading to simulate Docker secrets
        mock_read_secret.return_value = "test_access_token"
        
        config = {
            'mastodon': {
                'accounts': [
                    {
                        'name': 'test',
                        'instance_url': 'https://mastodon.social',
                        'access_token_file': '/run/secrets/mastodon_access_token'
                    }
                ]
            }
        }
        
        clients = MastodonClient.from_config(config)
        
        # Verify client is properly initialized with secrets
        self.assertEqual(len(clients), 1)
        client = clients[0]
        self.assertTrue(client.enabled)
        self.assertEqual(client.instance_url, "https://mastodon.social")
        self.assertEqual(client.access_token, "test_access_token")
        self.assertIsNotNone(client.api)
