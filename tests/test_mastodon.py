"""
Unit Tests for Mastodon Client Module.

This test suite validates the Mastodon posting functionality,
ensuring that the Mastodon client works correctly for POSSE syndication:
- Client initialization with credentials
- Status posting
- Credential verification

Test Coverage:
    - MastodonClient initialization (with/without credentials)
    - from_config factory method
    - Status posting (successful and failed)
    - Credential verification
    - Disabled state handling (when not configured)
    - API error handling

Testing Strategy:
    Uses unittest.mock to simulate Mastodon API interactions without
    making actual HTTP requests. This provides:
    - Fast test execution (no network overhead)
    - Isolation (no external dependencies)
    - Deterministic results (controlled responses)
    - No cost (no real API calls)
    - No need for actual Mastodon credentials

Running Tests:
    $ pytest tests/test_mastodon.py -v
    $ pytest tests/test_mastodon.py --cov=mastodon
"""
import pytest
from unittest.mock import patch, MagicMock
from mastodon import MastodonError

from mastodon_client.mastodon_client import MastodonClient


class TestMastodonClient:
    """Test suite for MastodonClient class."""
    
    def test_init_with_credentials(self):
        """Test initialization with complete credentials enables client."""
        with patch('mastodon_client.mastodon_client.Mastodon') as mock_mastodon:
            client = MastodonClient(
                instance_url="https://mastodon.social",
                access_token="test_access_token"
            )
            
            assert client.instance_url == "https://mastodon.social"
            assert client.access_token == "test_access_token"
            assert client.enabled is True
            assert client.api is not None
            
            # Verify Mastodon API was initialized with just access_token
            mock_mastodon.assert_called_once_with(
                access_token="test_access_token",
                api_base_url="https://mastodon.social"
            )
    
    def test_init_without_credentials(self):
        """Test initialization without credentials disables client."""
        client = MastodonClient(
            instance_url="https://mastodon.social",
            access_token=None
        )
        
        assert client.enabled is False
        assert client.api is None
    
    def test_init_with_empty_instance_url(self):
        """Test initialization with empty instance URL disables client."""
        client = MastodonClient(
            instance_url="",
            access_token="test_access_token"
        )
        
        assert client.enabled is False
        assert client.api is None
    
    def test_init_disabled_via_config(self):
        """Test initialization with config_enabled=False disables client."""
        client = MastodonClient(
            instance_url="https://mastodon.social",
            access_token="test_access_token",
            config_enabled=False
        )
        
        assert client.enabled is False
        assert client.api is None
    
    def test_init_with_api_error(self):
        """Test initialization handles Mastodon API errors gracefully."""
        with patch('mastodon_client.mastodon_client.Mastodon', side_effect=Exception("API Error")):
            client = MastodonClient(
                instance_url="https://mastodon.social",
                access_token="test_access_token"
            )
            
            assert client.enabled is False
            assert client.api is None
    
    @patch('config.read_secret_file')
    def test_from_config_enabled(self, mock_read_secret):
        """Test from_config creates enabled client when properly configured."""
        # Mock secret file reading
        mock_read_secret.return_value = "test_access_token"
        
        config = {
            'mastodon': {
                'enabled': True,
                'instance_url': 'https://mastodon.social',
                'access_token_file': '/run/secrets/mastodon_access_token'
            }
        }
        
        with patch('mastodon_client.mastodon_client.Mastodon'):
            client = MastodonClient.from_config(config)
            
            assert client.instance_url == "https://mastodon.social"
            assert client.access_token == "test_access_token"
            assert client.enabled is True
    
    @patch('config.read_secret_file')
    def test_from_config_disabled(self, mock_read_secret):
        """Test from_config creates disabled client when not enabled in config."""
        config = {
            'mastodon': {
                'enabled': False,
                'instance_url': 'https://mastodon.social'
            }
        }
        
        client = MastodonClient.from_config(config)
        
        assert client.enabled is False
        assert client.api is None
        # Should not attempt to read secrets when disabled
        mock_read_secret.assert_not_called()
    
    @patch('config.read_secret_file')
    def test_from_config_missing_secrets(self, mock_read_secret):
        """Test from_config handles missing secret files gracefully."""
        # Mock secret files not found
        mock_read_secret.return_value = None
        
        config = {
            'mastodon': {
                'enabled': True,
                'instance_url': 'https://mastodon.social',
                'access_token_file': '/run/secrets/mastodon_access_token'
            }
        }
        
        client = MastodonClient.from_config(config)
        
        assert client.enabled is False
        assert client.api is None
    
    def test_from_config_empty_config(self):
        """Test from_config handles empty or missing mastodon config."""
        config = {}
        
        client = MastodonClient.from_config(config)
        
        assert client.enabled is False
        assert client.api is None
    
    @patch('mastodon_client.mastodon_client.Mastodon')
    def test_post_status_success(self, mock_mastodon_class):
        """Test successful status posting to Mastodon."""
        mock_instance = MagicMock()
        mock_instance.status_post.return_value = {
            'id': '12345',
            'url': 'https://mastodon.social/@user/12345',
            'content': 'Test post'
        }
        mock_mastodon_class.return_value = mock_instance
        
        client = MastodonClient(
            instance_url="https://mastodon.social",
            access_token="test_access_token"
        )
        
        result = client.post_status("Test post")
        
        assert result is not None
        assert result['id'] == '12345'
        assert result['url'] == 'https://mastodon.social/@user/12345'
        
        mock_instance.status_post.assert_called_once_with(
            status="Test post",
            visibility='public',
            sensitive=False,
            spoiler_text=None
        )
    
    @patch('mastodon_client.mastodon_client.Mastodon')
    def test_post_status_with_options(self, mock_mastodon_class):
        """Test status posting with visibility and content warning options."""
        mock_instance = MagicMock()
        mock_instance.status_post.return_value = {
            'id': '12345',
            'url': 'https://mastodon.social/@user/12345'
        }
        mock_mastodon_class.return_value = mock_instance
        
        client = MastodonClient(
            instance_url="https://mastodon.social",
            access_token="test_access_token"
        )
        
        result = client.post_status(
            status="Sensitive content",
            visibility='unlisted',
            sensitive=True,
            spoiler_text="CW: Test"
        )
        
        assert result is not None
        
        mock_instance.status_post.assert_called_once_with(
            status="Sensitive content",
            visibility='unlisted',
            sensitive=True,
            spoiler_text="CW: Test"
        )
    
    def test_post_status_when_disabled(self):
        """Test posting fails gracefully when client is disabled."""
        client = MastodonClient(
            instance_url="https://mastodon.social",
            access_token=None
        )
        
        result = client.post_status("Test post")
        
        assert result is None
    
    @patch('mastodon_client.mastodon_client.Mastodon')
    def test_post_status_failure(self, mock_mastodon_class):
        """Test status posting handles API errors gracefully."""
        mock_instance = MagicMock()
        mock_instance.status_post.side_effect = MastodonError("Posting failed")
        mock_mastodon_class.return_value = mock_instance
        
        client = MastodonClient(
            instance_url="https://mastodon.social",
            access_token="test_access_token"
        )
        
        result = client.post_status("Test post")
        
        assert result is None
    
    @patch('mastodon_client.mastodon_client.Mastodon')
    def test_verify_credentials_success(self, mock_mastodon_class):
        """Test successful credential verification."""
        mock_instance = MagicMock()
        mock_instance.account_verify_credentials.return_value = {
            'id': '123',
            'username': 'testuser',
            'acct': 'testuser@mastodon.social'
        }
        mock_mastodon_class.return_value = mock_instance
        
        client = MastodonClient(
            instance_url="https://mastodon.social",
            access_token="test_access_token"
        )
        
        account = client.verify_credentials()
        
        assert account is not None
        assert account['username'] == 'testuser'
        mock_instance.account_verify_credentials.assert_called_once()
    
    def test_verify_credentials_when_disabled(self):
        """Test credential verification fails gracefully when client is disabled."""
        client = MastodonClient(
            instance_url="https://mastodon.social",
            access_token=None
        )
        
        account = client.verify_credentials()
        
        assert account is None
    
    @patch('mastodon_client.mastodon_client.Mastodon')
    def test_verify_credentials_failure(self, mock_mastodon_class):
        """Test credential verification handles API errors gracefully."""
        mock_instance = MagicMock()
        mock_instance.account_verify_credentials.side_effect = MastodonError("Invalid token")
        mock_mastodon_class.return_value = mock_instance
        
        client = MastodonClient(
            instance_url="https://mastodon.social",
            access_token="test_access_token"
        )
        
        account = client.verify_credentials()
        
        assert account is None
