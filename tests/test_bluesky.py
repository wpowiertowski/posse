"""
Integration Tests for Bluesky Client Module.

This test suite validates the Bluesky authentication functionality
by testing login with provided credentials from Docker secrets.

Test Coverage:
    - Login with credentials from secrets
    - Posting content
    - Credential verification
    - Error handling

Testing Strategy:
    Tests use mocked credentials from Docker secrets to verify
    authentication initialization works correctly.

Running Tests:
    $ PYTHONPATH=src python -m unittest tests.test_bluesky -v
"""
import unittest
from unittest.mock import patch, MagicMock, PropertyMock

from social.bluesky_client import BlueskyClient


class TestBlueskyClient(unittest.TestCase):
    """Test suite for BlueskyClient class."""
    
    @patch('config.read_secret_file')
    @patch('social.bluesky_client.Client')
    def test_login_with_provided_secrets(self, mock_client_class, mock_read_secret):
        """Test login with credentials loaded from secrets."""
        # Mock secret file reading to simulate Docker secrets
        mock_read_secret.return_value = "test_session_string"
        
        # Mock the Client instance
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        
        config = {
            'bluesky': {
                'accounts': [
                    {
                        'name': 'test',
                        'instance_url': 'https://bsky.social',
                        'access_token_file': '/run/secrets/bluesky_access_token'
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
        self.assertEqual(client.access_token, "test_session_string")
        self.assertIsNotNone(client.api)
        
        # Verify login was called with session_string
        mock_client.login.assert_called_once_with(session_string="test_session_string")
    
    @patch('social.bluesky_client.Client')
    def test_post_success(self, mock_client_class):
        """Test posting content successfully."""
        # Setup mock API
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        
        # Mock send_post response
        mock_response = MagicMock()
        mock_response.uri = 'at://did:plc:test/app.bsky.feed.post/123abc'
        mock_response.cid = 'bafytest123'
        mock_client.send_post.return_value = mock_response
        
        # Create client
        client = BlueskyClient(
            instance_url='https://bsky.social',
            access_token='test_session_string'
        )
        
        # Post content
        result = client.post('Hello Bluesky!')
        
        # Verify send_post was called
        mock_client.send_post.assert_called_once_with(text='Hello Bluesky!')
        
        # Verify result
        self.assertIsNotNone(result)
        self.assertEqual(result['uri'], 'at://did:plc:test/app.bsky.feed.post/123abc')
        self.assertEqual(result['cid'], 'bafytest123')
    
    @patch('social.bluesky_client.Client')
    def test_post_with_atprotocol_error(self, mock_client_class):
        """Test posting when ATProtocol error occurs."""
        from atproto.exceptions import AtProtocolError
        
        # Setup mock API
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        
        # Mock send_post to raise AtProtocolError
        mock_client.send_post.side_effect = AtProtocolError("Rate limit exceeded")
        
        # Create client
        client = BlueskyClient(
            instance_url='https://bsky.social',
            access_token='test_session_string'
        )
        
        # Post content
        result = client.post('Test post')
        
        # Verify send_post was called
        mock_client.send_post.assert_called_once()
        
        # Verify result is None due to error
        self.assertIsNone(result)
    
    @patch('social.bluesky_client.Client')
    def test_post_disabled_client(self, mock_client_class):
        """Test posting with disabled client returns None."""
        # Create disabled client (no access token)
        client = BlueskyClient(
            instance_url='https://bsky.social',
            access_token=None
        )
        
        # Attempt to post
        result = client.post('Test post')
        
        # Verify no API calls were made
        mock_client_class.return_value.send_post.assert_not_called()
        
        # Verify result is None
        self.assertIsNone(result)
    
    @patch('social.bluesky_client.Client')
    def test_verify_credentials_success(self, mock_client_class):
        """Test successful credential verification."""
        # Setup mock API
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        
        # Mock the me property
        mock_me = MagicMock()
        mock_me.did = 'did:plc:test123'
        type(mock_client).me = PropertyMock(return_value=mock_me)
        
        # Mock get_profile response
        mock_profile = MagicMock()
        mock_profile.handle = 'test.bsky.social'
        mock_profile.did = 'did:plc:test123'
        mock_profile.display_name = 'Test User'
        mock_client.get_profile.return_value = mock_profile
        
        # Create client
        client = BlueskyClient(
            instance_url='https://bsky.social',
            access_token='test_session_string'
        )
        
        # Verify credentials
        result = client.verify_credentials()
        
        # Verify get_profile was called with the correct DID
        mock_client.get_profile.assert_called_once_with('did:plc:test123')
        
        # Verify result
        self.assertIsNotNone(result)
        self.assertEqual(result['handle'], 'test.bsky.social')
        self.assertEqual(result['did'], 'did:plc:test123')
        self.assertEqual(result['display_name'], 'Test User')
    
    @patch('social.bluesky_client.Client')
    def test_verify_credentials_no_session(self, mock_client_class):
        """Test credential verification when no session exists."""
        # Setup mock API
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        
        # Mock the me property to be None (no session)
        type(mock_client).me = PropertyMock(return_value=None)
        
        # Create client
        client = BlueskyClient(
            instance_url='https://bsky.social',
            access_token='test_session_string'
        )
        
        # Verify credentials
        result = client.verify_credentials()
        
        # Verify get_profile was NOT called
        mock_client.get_profile.assert_not_called()
        
        # Verify result is None
        self.assertIsNone(result)
    
    @patch('social.bluesky_client.Client')
    def test_verify_credentials_disabled_client(self, mock_client_class):
        """Test credential verification with disabled client."""
        # Create disabled client (no access token)
        client = BlueskyClient(
            instance_url='https://bsky.social',
            access_token=None
        )
        
        # Attempt to verify credentials
        result = client.verify_credentials()
        
        # Verify no API calls were made
        mock_client_class.return_value.get_profile.assert_not_called()
        
        # Verify result is None
        self.assertIsNone(result)
    
    @patch('social.bluesky_client.Client')
    def test_initialization_failure(self, mock_client_class):
        """Test that client is disabled when initialization fails."""
        # Setup mock to raise exception during login
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_client.login.side_effect = Exception("Connection failed")
        
        # Create client - should catch exception and disable
        client = BlueskyClient(
            instance_url='https://bsky.social',
            access_token='test_session_string'
        )
        
        # Verify client is disabled
        self.assertFalse(client.enabled)
        
        # Verify posting returns None
        result = client.post('Test post')
        self.assertIsNone(result)
    
    @patch('config.read_secret_file')
    @patch('social.bluesky_client.Client')
    def test_multiple_accounts_from_config(self, mock_client_class, mock_read_secret):
        """Test loading multiple Bluesky accounts from config."""
        # Mock secret file reading
        def mock_read_secret_side_effect(path):
            if 'personal' in path:
                return 'personal_session_string'
            elif 'professional' in path:
                return 'professional_session_string'
            return None
        
        mock_read_secret.side_effect = mock_read_secret_side_effect
        
        # Mock the Client instance
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        
        config = {
            'bluesky': {
                'accounts': [
                    {
                        'name': 'personal',
                        'instance_url': 'https://bsky.social',
                        'access_token_file': '/run/secrets/bluesky_personal_access_token'
                    },
                    {
                        'name': 'professional',
                        'instance_url': 'https://bsky.social',
                        'access_token_file': '/run/secrets/bluesky_professional_access_token'
                    }
                ]
            }
        }
        
        clients = BlueskyClient.from_config(config)
        
        # Verify two clients were created
        self.assertEqual(len(clients), 2)
        
        # Verify both clients are enabled with correct credentials
        self.assertTrue(clients[0].enabled)
        self.assertEqual(clients[0].account_name, 'personal')
        self.assertEqual(clients[0].access_token, 'personal_session_string')
        
        self.assertTrue(clients[1].enabled)
        self.assertEqual(clients[1].account_name, 'professional')
        self.assertEqual(clients[1].access_token, 'professional_session_string')
