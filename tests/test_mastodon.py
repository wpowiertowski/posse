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


class TestMastodonOAuth:
    """Test suite for Mastodon OAuth flow."""
    
    @patch('mastodon_client.mastodon_client.Mastodon.create_app')
    def test_register_app_success(self, mock_create_app):
        """Test successful app registration."""
        mock_create_app.return_value = ("client_id_123", "client_secret_456")
        
        client_id, client_secret = MastodonClient.register_app(
            app_name="POSSE Test",
            instance_url="https://mastodon.social"
        )
        
        assert client_id == "client_id_123"
        assert client_secret == "client_secret_456"
        
        mock_create_app.assert_called_once()
        call_args = mock_create_app.call_args
        assert call_args[1]['client_name'] == "POSSE Test"
        assert call_args[1]['api_base_url'] == "https://mastodon.social"
    
    @patch('mastodon_client.mastodon_client.Mastodon.create_app')
    def test_register_app_with_file(self, mock_create_app):
        """Test app registration with credential file."""
        mock_create_app.return_value = ("client_id_123", "client_secret_456")
        
        MastodonClient.register_app(
            app_name="POSSE",
            instance_url="https://mastodon.social",
            to_file="test_cred.secret"
        )
        
        call_args = mock_create_app.call_args
        assert call_args[1]['to_file'] == "test_cred.secret"
    
    @patch('mastodon_client.mastodon_client.Mastodon')
    def test_create_for_oauth(self, mock_mastodon_class):
        """Test creating OAuth client."""
        mock_instance = MagicMock()
        mock_mastodon_class.return_value = mock_instance
        
        client = MastodonClient.create_for_oauth(
            client_credential_file="clientcred.secret",
            instance_url="https://mastodon.social"
        )
        
        assert client.instance_url == "https://mastodon.social"
        assert client.enabled is True
        assert client.api is not None
        
        mock_mastodon_class.assert_called_once_with(
            client_id="clientcred.secret",
            api_base_url="https://mastodon.social"
        )
    
    @patch('mastodon_client.mastodon_client.Mastodon')
    def test_get_auth_request_url(self, mock_mastodon_class):
        """Test getting authorization URL."""
        mock_instance = MagicMock()
        mock_instance.auth_request_url.return_value = "https://mastodon.social/oauth/authorize?..."
        mock_mastodon_class.return_value = mock_instance
        
        client = MastodonClient.create_for_oauth(
            client_credential_file="clientcred.secret",
            instance_url="https://mastodon.social"
        )
        
        auth_url = client.get_auth_request_url()
        
        assert auth_url == "https://mastodon.social/oauth/authorize?..."
        mock_instance.auth_request_url.assert_called_once()
    
    @patch('mastodon_client.mastodon_client.Mastodon')
    def test_login_with_code(self, mock_mastodon_class):
        """Test exchanging auth code for access token."""
        mock_instance = MagicMock()
        mock_instance.log_in.return_value = "access_token_789"
        mock_mastodon_class.return_value = mock_instance
        
        client = MastodonClient.create_for_oauth(
            client_credential_file="clientcred.secret",
            instance_url="https://mastodon.social"
        )
        
        access_token = client.login_with_code(code="auth_code_xyz")
        
        assert access_token == "access_token_789"
        assert client.access_token == "access_token_789"
        mock_instance.log_in.assert_called_once()
    
    @patch('mastodon_client.mastodon_client.Mastodon')
    def test_toot_alias(self, mock_mastodon_class):
        """Test that toot() is an alias for post()."""
        mock_instance = MagicMock()
        mock_instance.status_post.return_value = {
            'id': '12345',
            'url': 'https://mastodon.social/@user/12345'
        }
        mock_mastodon_class.return_value = mock_instance
        
        client = MastodonClient(
            instance_url="https://mastodon.social",
            access_token="test_token"
        )
        
        result = client.toot("Test toot")
        
        assert result is not None
        assert result['id'] == '12345'
        mock_instance.status_post.assert_called_once()
