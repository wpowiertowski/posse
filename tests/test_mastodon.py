"""
Unit Tests for Mastodon Client Module.

This test suite validates the Mastodon authentication and posting functionality,
ensuring that the Mastodon client works correctly for POSSE syndication:
- Client initialization with credentials
- App registration with Mastodon instances
- OAuth authorization flow
- Access token exchange
- Status posting
- Credential verification

Test Coverage:
    - MastodonClient initialization (with/without credentials)
    - from_config factory method
    - App registration (register_app)
    - Authorization URL generation
    - Access token retrieval
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
from unittest.mock import patch, MagicMock, mock_open
from mastodon import MastodonError

from mastodon_client.mastodon_client import MastodonClient


class TestMastodonClient:
    """Test suite for MastodonClient class."""
    
    def test_init_with_credentials(self):
        """Test initialization with complete credentials enables client."""
        with patch('mastodon_client.mastodon_client.Mastodon') as mock_mastodon:
            client = MastodonClient(
                instance_url="https://mastodon.social",
                client_id="test_client_id",
                client_secret="test_client_secret",
                access_token="test_access_token"
            )
            
            assert client.instance_url == "https://mastodon.social"
            assert client.client_id == "test_client_id"
            assert client.client_secret == "test_client_secret"
            assert client.access_token == "test_access_token"
            assert client.enabled is True
            assert client.api is not None
            
            # Verify Mastodon API was initialized
            mock_mastodon.assert_called_once_with(
                client_id="test_client_id",
                client_secret="test_client_secret",
                access_token="test_access_token",
                api_base_url="https://mastodon.social"
            )
    
    def test_init_without_credentials(self):
        """Test initialization without credentials disables client."""
        client = MastodonClient(
            instance_url="https://mastodon.social",
            client_id=None,
            client_secret=None,
            access_token=None
        )
        
        assert client.enabled is False
        assert client.api is None
    
    def test_init_with_partial_credentials(self):
        """Test initialization with partial credentials disables client."""
        client = MastodonClient(
            instance_url="https://mastodon.social",
            client_id="test_client_id",
            client_secret=None,
            access_token="test_access_token"
        )
        
        assert client.enabled is False
        assert client.api is None
    
    def test_init_disabled_via_config(self):
        """Test initialization with config_enabled=False disables client."""
        client = MastodonClient(
            instance_url="https://mastodon.social",
            client_id="test_client_id",
            client_secret="test_client_secret",
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
                client_id="test_client_id",
                client_secret="test_client_secret",
                access_token="test_access_token"
            )
            
            assert client.enabled is False
            assert client.api is None
    
    @patch('mastodon_client.mastodon_client.read_secret_file')
    def test_from_config_enabled(self, mock_read_secret):
        """Test from_config creates enabled client when properly configured."""
        # Mock secret file reading
        mock_read_secret.side_effect = [
            "test_client_id",
            "test_client_secret",
            "test_access_token"
        ]
        
        config = {
            'mastodon': {
                'enabled': True,
                'instance_url': 'https://mastodon.social',
                'client_id_file': '/run/secrets/mastodon_client_id',
                'client_secret_file': '/run/secrets/mastodon_client_secret',
                'access_token_file': '/run/secrets/mastodon_access_token'
            }
        }
        
        with patch('mastodon_client.mastodon_client.Mastodon'):
            client = MastodonClient.from_config(config)
            
            assert client.instance_url == "https://mastodon.social"
            assert client.client_id == "test_client_id"
            assert client.client_secret == "test_client_secret"
            assert client.access_token == "test_access_token"
            assert client.enabled is True
    
    @patch('mastodon_client.mastodon_client.read_secret_file')
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
    
    @patch('mastodon_client.mastodon_client.read_secret_file')
    def test_from_config_missing_secrets(self, mock_read_secret):
        """Test from_config handles missing secret files gracefully."""
        # Mock secret files not found
        mock_read_secret.return_value = None
        
        config = {
            'mastodon': {
                'enabled': True,
                'instance_url': 'https://mastodon.social',
                'client_id_file': '/run/secrets/mastodon_client_id',
                'client_secret_file': '/run/secrets/mastodon_client_secret',
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
    
    @patch('mastodon_client.mastodon_client.Mastodon.create_app')
    def test_register_app_success(self, mock_create_app):
        """Test successful app registration with Mastodon instance."""
        mock_create_app.return_value = ("client_id_123", "client_secret_456")
        
        client_id, client_secret = MastodonClient.register_app(
            instance_url="https://mastodon.social",
            app_name="POSSE Test"
        )
        
        assert client_id == "client_id_123"
        assert client_secret == "client_secret_456"
        
        mock_create_app.assert_called_once_with(
            "POSSE Test",
            scopes=['read', 'write:statuses'],
            api_base_url="https://mastodon.social"
        )
    
    @patch('mastodon_client.mastodon_client.Mastodon.create_app')
    def test_register_app_with_custom_scopes(self, mock_create_app):
        """Test app registration with custom OAuth scopes."""
        mock_create_app.return_value = ("client_id_123", "client_secret_456")
        
        custom_scopes = ['read', 'write:statuses', 'write:media']
        client_id, client_secret = MastodonClient.register_app(
            instance_url="https://mastodon.social",
            app_name="POSSE Test",
            scopes=custom_scopes
        )
        
        assert client_id == "client_id_123"
        assert client_secret == "client_secret_456"
        
        mock_create_app.assert_called_once_with(
            "POSSE Test",
            scopes=custom_scopes,
            api_base_url="https://mastodon.social"
        )
    
    @patch('mastodon_client.mastodon_client.Mastodon.create_app')
    def test_register_app_failure(self, mock_create_app):
        """Test app registration handles API errors."""
        mock_create_app.side_effect = MastodonError("Registration failed")
        
        with pytest.raises(MastodonError):
            MastodonClient.register_app(
                instance_url="https://mastodon.social"
            )
    
    @patch('mastodon_client.mastodon_client.Mastodon')
    def test_get_authorization_url(self, mock_mastodon_class):
        """Test generation of OAuth authorization URL."""
        mock_instance = MagicMock()
        mock_instance.auth_request_url.return_value = "https://mastodon.social/oauth/authorize?..."
        mock_mastodon_class.return_value = mock_instance
        
        client = MastodonClient(
            instance_url="https://mastodon.social",
            client_id="test_client_id",
            client_secret="test_client_secret"
        )
        
        auth_url = client.get_authorization_url()
        
        assert auth_url == "https://mastodon.social/oauth/authorize?..."
        mock_instance.auth_request_url.assert_called_once_with(
            scopes=['read', 'write:statuses'],
            redirect_uris='urn:ietf:wg:oauth:2.0:oob'
        )
    
    def test_get_authorization_url_without_credentials(self):
        """Test authorization URL generation fails without client credentials."""
        client = MastodonClient(
            instance_url="https://mastodon.social",
            client_id=None,
            client_secret=None
        )
        
        with pytest.raises(ValueError, match="Client ID and secret required"):
            client.get_authorization_url()
    
    @patch('mastodon_client.mastodon_client.Mastodon')
    def test_get_access_token(self, mock_mastodon_class):
        """Test exchange of authorization code for access token."""
        mock_instance = MagicMock()
        mock_instance.log_in.return_value = "access_token_789"
        mock_mastodon_class.return_value = mock_instance
        
        client = MastodonClient(
            instance_url="https://mastodon.social",
            client_id="test_client_id",
            client_secret="test_client_secret"
        )
        
        access_token = client.get_access_token("auth_code_123")
        
        assert access_token == "access_token_789"
        mock_instance.log_in.assert_called_once_with(
            code="auth_code_123",
            redirect_uri='urn:ietf:wg:oauth:2.0:oob',
            scopes=['read', 'write:statuses']
        )
    
    def test_get_access_token_without_credentials(self):
        """Test access token exchange fails without client credentials."""
        client = MastodonClient(
            instance_url="https://mastodon.social",
            client_id=None,
            client_secret=None
        )
        
        with pytest.raises(ValueError, match="Client ID and secret required"):
            client.get_access_token("auth_code_123")
    
    @patch('mastodon_client.mastodon_client.Mastodon')
    def test_get_access_token_failure(self, mock_mastodon_class):
        """Test access token exchange handles API errors."""
        mock_instance = MagicMock()
        mock_instance.log_in.side_effect = MastodonError("Invalid code")
        mock_mastodon_class.return_value = mock_instance
        
        client = MastodonClient(
            instance_url="https://mastodon.social",
            client_id="test_client_id",
            client_secret="test_client_secret"
        )
        
        with pytest.raises(MastodonError):
            client.get_access_token("invalid_code")
    
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
            client_id="test_client_id",
            client_secret="test_client_secret",
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
            client_id="test_client_id",
            client_secret="test_client_secret",
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
            client_id=None,
            client_secret=None,
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
            client_id="test_client_id",
            client_secret="test_client_secret",
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
            client_id="test_client_id",
            client_secret="test_client_secret",
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
            client_id=None,
            client_secret=None,
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
            client_id="test_client_id",
            client_secret="test_client_secret",
            access_token="test_access_token"
        )
        
        account = client.verify_credentials()
        
        assert account is None


class TestMastodonClientIntegration:
    """Integration tests for typical Mastodon client workflows."""
    
    @patch('mastodon_client.mastodon_client.Mastodon.create_app')
    @patch('mastodon_client.mastodon_client.Mastodon')
    def test_full_authentication_flow(self, mock_mastodon_class, mock_create_app):
        """Test complete authentication workflow from registration to posting."""
        # Step 1: Register app
        mock_create_app.return_value = ("client_id_123", "client_secret_456")
        
        client_id, client_secret = MastodonClient.register_app(
            instance_url="https://mastodon.social"
        )
        
        assert client_id == "client_id_123"
        assert client_secret == "client_secret_456"
        
        # Step 2: Get authorization URL
        mock_instance = MagicMock()
        mock_instance.auth_request_url.return_value = "https://mastodon.social/oauth/authorize"
        mock_mastodon_class.return_value = mock_instance
        
        client = MastodonClient(
            instance_url="https://mastodon.social",
            client_id=client_id,
            client_secret=client_secret
        )
        
        auth_url = client.get_authorization_url()
        assert auth_url is not None
        
        # Step 3: Get access token
        mock_instance.log_in.return_value = "access_token_789"
        access_token = client.get_access_token("auth_code_xyz")
        assert access_token == "access_token_789"
        
        # Step 4: Create authenticated client and post
        authenticated_client = MastodonClient(
            instance_url="https://mastodon.social",
            client_id=client_id,
            client_secret=client_secret,
            access_token=access_token
        )
        
        mock_instance.status_post.return_value = {
            'id': '12345',
            'url': 'https://mastodon.social/@user/12345'
        }
        
        result = authenticated_client.post_status("Hello Mastodon!")
        assert result is not None
        assert result['url'] == 'https://mastodon.social/@user/12345'
