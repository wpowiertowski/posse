"""
Integration Tests for Bluesky Client Module.

This test suite validates the Bluesky authentication functionality
by testing login with provided credentials from Docker secrets.

Test Coverage:
    - Login with credentials from secrets
    - Posting to Bluesky
    - Credential verification

Testing Strategy:
    Tests use mocked credentials from Docker secrets to verify
    authentication initialization works correctly.

Running Tests:
    $ PYTHONPATH=src python -m unittest tests.test_bluesky -v
"""
import unittest
from unittest.mock import patch, MagicMock, call

from social.bluesky_client import BlueskyClient


class TestBlueskyClient(unittest.TestCase):
    """Test suite for BlueskyClient class."""
    
    @patch('config.read_secret_file')
    @patch('social.bluesky_client.Client')
    def test_login_with_provided_secrets(self, mock_client_class, mock_read_secret):
        """Test login with credentials loaded from secrets."""
        # Mock secret file reading to simulate Docker secrets
        mock_read_secret.return_value = "test_app_password"
        
        # Mock ATProto Client
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        
        config = {
            'bluesky': {
                'accounts': [
                    {
                        'name': 'test',
                        'instance_url': 'https://bsky.social',
                        'handle': 'user.bsky.social',
                        'app_password_file': '/run/secrets/bluesky_app_password'
                    }
                ]
            }
        }
        
        clients = BlueskyClient.from_config(config)
        
        # Verify client is properly initialized with secrets
        self.assertEqual(len(clients), 1)
        client = clients[0]
        self.assertTrue(client.enabled)
        self.assertEqual(client.instance_url, "https://bsky.social")
        self.assertEqual(client.handle, "user.bsky.social")
        self.assertEqual(client.app_password, "test_app_password")
        self.assertIsNotNone(client.api)
        
        # Verify login was called with correct credentials
        mock_client.login.assert_called_once_with(
            login='user.bsky.social',
            password='test_app_password'
        )
    
    @patch('config.read_secret_file')
    @patch('social.bluesky_client.Client')
    def test_login_with_access_token_file_fallback(self, mock_client_class, mock_read_secret):
        """Test that access_token_file works as fallback for app_password_file."""
        # Mock secret file reading
        mock_read_secret.return_value = "test_app_password"
        
        # Mock ATProto Client
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        
        config = {
            'bluesky': {
                'accounts': [
                    {
                        'name': 'test',
                        'instance_url': 'https://bsky.social',
                        'handle': 'user.bsky.social',
                        'access_token_file': '/run/secrets/bluesky_access_token'
                    }
                ]
            }
        }
        
        clients = BlueskyClient.from_config(config)
        
        # Verify client is properly initialized
        self.assertEqual(len(clients), 1)
        client = clients[0]
        self.assertTrue(client.enabled)
        self.assertEqual(client.app_password, "test_app_password")
    
    @patch('social.bluesky_client.Client')
    def test_post_success(self, mock_client_class):
        """Test posting status to Bluesky successfully."""
        # Setup mock API
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        
        # Mock send_post result
        mock_result = MagicMock()
        mock_result.uri = 'at://did:plc:abc123/app.bsky.feed.post/xyz789'
        mock_result.cid = 'bafyreiabc123'
        mock_client.send_post.return_value = mock_result
        
        # Create client
        client = BlueskyClient(
            instance_url='https://bsky.social',
            handle='user.bsky.social',
            app_password='test_password'
        )
        
        # Post content
        result = client.post('Hello Bluesky!')
        
        # Verify send_post was called
        self.assertEqual(mock_client.send_post.call_count, 1)
        
        # Verify result
        self.assertIsNotNone(result)
        self.assertEqual(result['uri'], 'at://did:plc:abc123/app.bsky.feed.post/xyz789')
        self.assertEqual(result['cid'], 'bafyreiabc123')
    
    @patch('social.bluesky_client.Client')
    def test_post_disabled_client(self, mock_client_class):
        """Test posting with disabled client returns None."""
        # Create disabled client (no handle)
        client = BlueskyClient(
            instance_url='https://bsky.social',
            handle=None,
            app_password='test_password'
        )
        
        # Attempt to post
        result = client.post('Test post')
        
        # Verify result is None
        self.assertIsNone(result)
    
    @patch('social.bluesky_client.Client')
    def test_post_failure(self, mock_client_class):
        """Test posting when API call fails."""
        # Setup mock API
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        
        # Mock send_post to raise exception
        mock_client.send_post.side_effect = Exception("API Error")
        
        # Create client
        client = BlueskyClient(
            instance_url='https://bsky.social',
            handle='user.bsky.social',
            app_password='test_password'
        )
        
        # Attempt to post
        result = client.post('Test post')
        
        # Verify result is None
        self.assertIsNone(result)
    
    @patch('social.bluesky_client.Client')
    def test_verify_credentials_success(self, mock_client_class):
        """Test verifying credentials successfully."""
        # Setup mock API
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        
        # Mock session and profile
        mock_client.me = MagicMock()
        mock_client.me.did = 'did:plc:abc123'
        
        mock_profile = MagicMock()
        mock_profile.handle = 'user.bsky.social'
        mock_profile.did = 'did:plc:abc123'
        mock_profile.display_name = 'Test User'
        mock_client.get_profile.return_value = mock_profile
        
        # Create client
        client = BlueskyClient(
            instance_url='https://bsky.social',
            handle='user.bsky.social',
            app_password='test_password'
        )
        
        # Verify credentials
        result = client.verify_credentials()
        
        # Verify get_profile was called
        mock_client.get_profile.assert_called_once_with(actor='did:plc:abc123')
        
        # Verify result
        self.assertIsNotNone(result)
        self.assertEqual(result['handle'], 'user.bsky.social')
        self.assertEqual(result['did'], 'did:plc:abc123')
        self.assertEqual(result['display_name'], 'Test User')
    
    @patch('social.bluesky_client.Client')
    def test_verify_credentials_no_session(self, mock_client_class):
        """Test verifying credentials when no session exists."""
        # Setup mock API
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        
        # Mock missing session
        mock_client.me = None
        
        # Create client
        client = BlueskyClient(
            instance_url='https://bsky.social',
            handle='user.bsky.social',
            app_password='test_password'
        )
        
        # Verify credentials
        result = client.verify_credentials()
        
        # Verify result is None
        self.assertIsNone(result)
    
    @patch('social.bluesky_client.Client')
    def test_verify_credentials_disabled_client(self, mock_client_class):
        """Test verifying credentials with disabled client."""
        # Create disabled client
        client = BlueskyClient(
            instance_url='https://bsky.social',
            handle=None,
            app_password='test_password'
        )
        
        # Verify credentials
        result = client.verify_credentials()
        
        # Verify result is None
        self.assertIsNone(result)
    
    @patch('social.bluesky_client.Client')
    def test_verify_credentials_failure(self, mock_client_class):
        """Test verifying credentials when API call fails."""
        # Setup mock API
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        
        # Mock session
        mock_client.me = MagicMock()
        mock_client.me.did = 'did:plc:abc123'
        
        # Mock get_profile to raise exception
        mock_client.get_profile.side_effect = Exception("API Error")
        
        # Create client
        client = BlueskyClient(
            instance_url='https://bsky.social',
            handle='user.bsky.social',
            app_password='test_password'
        )
        
        # Verify credentials
        result = client.verify_credentials()
        
        # Verify result is None
        self.assertIsNone(result)
    
    @patch('config.read_secret_file')
    @patch('social.bluesky_client.Client')
    def test_multiple_accounts_from_config(self, mock_client_class, mock_read_secret):
        """Test creating multiple Bluesky clients from config."""
        # Mock secret file reading with different values
        mock_read_secret.side_effect = ["password1", "password2"]
        
        # Mock ATProto Client
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        
        config = {
            'bluesky': {
                'accounts': [
                    {
                        'name': 'personal',
                        'instance_url': 'https://bsky.social',
                        'handle': 'user1.bsky.social',
                        'app_password_file': '/run/secrets/bluesky_personal'
                    },
                    {
                        'name': 'work',
                        'instance_url': 'https://bsky.social',
                        'handle': 'user2.bsky.social',
                        'app_password_file': '/run/secrets/bluesky_work'
                    }
                ]
            }
        }
        
        clients = BlueskyClient.from_config(config)
        
        # Verify two clients were created
        self.assertEqual(len(clients), 2)
        
        # Verify first client
        self.assertEqual(clients[0].account_name, 'personal')
        self.assertEqual(clients[0].handle, 'user1.bsky.social')
        self.assertEqual(clients[0].app_password, 'password1')
        
        # Verify second client
        self.assertEqual(clients[1].account_name, 'work')
        self.assertEqual(clients[1].handle, 'user2.bsky.social')
        self.assertEqual(clients[1].app_password, 'password2')
    
    @patch('config.read_secret_file')
    @patch('social.bluesky_client.Client')
    def test_disabled_account_missing_handle(self, mock_client_class, mock_read_secret):
        """Test that account is disabled when handle is missing."""
        mock_read_secret.return_value = "password"
        
        config = {
            'bluesky': {
                'accounts': [
                    {
                        'name': 'test',
                        'instance_url': 'https://bsky.social',
                        'app_password_file': '/run/secrets/bluesky'
                    }
                ]
            }
        }
        
        clients = BlueskyClient.from_config(config)
        
        # Verify client is disabled
        self.assertEqual(len(clients), 1)
        self.assertFalse(clients[0].enabled)
    
    @patch('config.read_secret_file')
    @patch('social.bluesky_client.Client')
    def test_disabled_account_missing_password(self, mock_client_class, mock_read_secret):
        """Test that account is disabled when password is missing."""
        mock_read_secret.return_value = None
        
        config = {
            'bluesky': {
                'accounts': [
                    {
                        'name': 'test',
                        'instance_url': 'https://bsky.social',
                        'handle': 'user.bsky.social',
                        'app_password_file': '/run/secrets/bluesky'
                    }
                ]
            }
        }
        
        clients = BlueskyClient.from_config(config)
        
        # Verify client is disabled
        self.assertEqual(len(clients), 1)
        self.assertFalse(clients[0].enabled)


if __name__ == '__main__':
    unittest.main()
