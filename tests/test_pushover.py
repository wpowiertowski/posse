"""
Unit Tests for Pushover Notification Module.

This test suite validates the Pushover notification functionality,
ensuring that push notifications are sent correctly for main POSSE events:
- New posts received and validated
- Posts queued for syndication
- Validation errors

Test Coverage:
    - Pushover client initialization (with/without credentials)
    - Notification sending (successful and failed)
    - Post received notifications
    - Post queued notifications
    - Validation error notifications
    - Disabled state handling (when credentials not configured)
    - API error handling

Testing Strategy:
    Uses unittest.mock to simulate Pushover API interactions without
    making actual HTTP requests. This provides:
    - Fast test execution (no network overhead)
    - Isolation (no external dependencies)
    - Deterministic results (controlled responses)
    - No cost (no real API calls)

Running Tests:
    $ pytest tests/test_pushover.py -v
    $ pytest tests/test_pushover.py --cov=notifications
"""
import os
import pytest
from unittest.mock import patch, MagicMock
import requests

from notifications.pushover import PushoverNotifier


class TestPushoverNotifier:
    """Test suite for PushoverNotifier class."""
    
    def test_init_with_credentials(self):
        """Test initialization with explicit credentials enables notifications."""
        notifier = PushoverNotifier(
            app_token="test_app_token",
            user_key="test_user_key"
        )
        
        assert notifier.app_token == "test_app_token"
        assert notifier.user_key == "test_user_key"
        assert notifier.enabled is True
    
    def test_init_without_credentials(self):
        """Test initialization without credentials disables notifications."""
        # Ensure env vars are not set
        with patch.dict(os.environ, {}, clear=True):
            notifier = PushoverNotifier()
            
            assert notifier.app_token is None
            assert notifier.user_key is None
            assert notifier.enabled is False
    
    def test_init_from_environment(self):
        """Test initialization from environment variables."""
        with patch.dict(os.environ, {
            'PUSHOVER_APP_TOKEN': 'env_app_token',
            'PUSHOVER_USER_KEY': 'env_user_key'
        }):
            notifier = PushoverNotifier()
            
            assert notifier.app_token == 'env_app_token'
            assert notifier.user_key == 'env_user_key'
            assert notifier.enabled is True
    
    def test_init_partial_credentials_disables_notifications(self):
        """Test that missing either credential disables notifications."""
        # Only app token
        notifier1 = PushoverNotifier(app_token="token", user_key=None)
        assert notifier1.enabled is False
        
        # Only user key
        notifier2 = PushoverNotifier(app_token=None, user_key="key")
        assert notifier2.enabled is False
    
    @patch('notifications.pushover.requests.post')
    def test_send_notification_success(self, mock_post):
        """Test successful notification sending."""
        # Mock successful API response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response
        
        notifier = PushoverNotifier(
            app_token="test_app_token",
            user_key="test_user_key"
        )
        
        result = notifier._send_notification(
            title="Test Title",
            message="Test message"
        )
        
        assert result is True
        assert mock_post.called
        
        # Verify API call parameters
        call_args = mock_post.call_args
        assert call_args[0][0] == PushoverNotifier.PUSHOVER_API_URL
        assert call_args[1]['data']['token'] == "test_app_token"
        assert call_args[1]['data']['user'] == "test_user_key"
        assert call_args[1]['data']['title'] == "Test Title"
        assert call_args[1]['data']['message'] == "Test message"
    
    @patch('notifications.pushover.requests.post')
    def test_send_notification_with_url(self, mock_post):
        """Test notification with URL and URL title."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response
        
        notifier = PushoverNotifier(
            app_token="test_app_token",
            user_key="test_user_key"
        )
        
        result = notifier._send_notification(
            title="Test",
            message="Message",
            url="https://example.com/post",
            url_title="View Post"
        )
        
        assert result is True
        call_data = mock_post.call_args[1]['data']
        assert call_data['url'] == "https://example.com/post"
        assert call_data['url_title'] == "View Post"
    
    @patch('notifications.pushover.requests.post')
    def test_send_notification_api_error(self, mock_post):
        """Test notification sending when API returns error."""
        # Mock API error response
        mock_post.side_effect = requests.exceptions.RequestException("API Error")
        
        notifier = PushoverNotifier(
            app_token="test_app_token",
            user_key="test_user_key"
        )
        
        result = notifier._send_notification(
            title="Test",
            message="Message"
        )
        
        assert result is False
    
    def test_send_notification_when_disabled(self):
        """Test that notifications are skipped when disabled."""
        notifier = PushoverNotifier()  # No credentials - disabled
        
        result = notifier._send_notification(
            title="Test",
            message="Message"
        )
        
        assert result is False
    
    @patch('notifications.pushover.requests.post')
    def test_notify_post_received(self, mock_post):
        """Test post received notification."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response
        
        notifier = PushoverNotifier(
            app_token="test_app_token",
            user_key="test_user_key"
        )
        
        result = notifier.notify_post_received(
            post_title="Welcome to Ghost",
            post_id="abc123"
        )
        
        assert result is True
        call_data = mock_post.call_args[1]['data']
        assert "📝 Post Received" in call_data['title']
        assert "Welcome to Ghost" in call_data['message']
        assert call_data['priority'] == 0  # Normal priority
    
    @patch('notifications.pushover.requests.post')
    def test_notify_post_queued(self, mock_post):
        """Test post queued notification."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response
        
        notifier = PushoverNotifier(
            app_token="test_app_token",
            user_key="test_user_key"
        )
        
        result = notifier.notify_post_queued(
            post_title="Welcome to Ghost",
            post_url="https://blog.example.com/welcome"
        )
        
        assert result is True
        call_data = mock_post.call_args[1]['data']
        assert "✅ Post Queued" in call_data['title']
        assert "Welcome to Ghost" in call_data['message']
        assert call_data['url'] == "https://blog.example.com/welcome"
        assert call_data['url_title'] == "View Post"
        assert call_data['priority'] == 0  # Normal priority
    
    @patch('notifications.pushover.requests.post')
    def test_notify_validation_error(self, mock_post):
        """Test validation error notification."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response
        
        notifier = PushoverNotifier(
            app_token="test_app_token",
            user_key="test_user_key"
        )
        
        result = notifier.notify_validation_error(
            details="Missing required field: title"
        )
        
        assert result is True
        call_data = mock_post.call_args[1]['data']
        assert "⚠️ Validation Error" in call_data['title']
        assert "Missing required field: title" in call_data['message']
        assert call_data['priority'] == 1  # High priority for errors
    
    @patch('notifications.pushover.requests.post')
    def test_message_length_limits(self, mock_post):
        """Test that message length limits are enforced."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response
        
        notifier = PushoverNotifier(
            app_token="test_app_token",
            user_key="test_user_key"
        )
        
        # Create strings that exceed Pushover limits
        long_title = "A" * 300  # Exceeds 250 char limit
        long_message = "B" * 1100  # Exceeds 1024 char limit
        long_url = "https://example.com/" + "C" * 600  # Exceeds 512 char limit
        long_url_title = "D" * 150  # Exceeds 100 char limit
        
        result = notifier._send_notification(
            title=long_title,
            message=long_message,
            url=long_url,
            url_title=long_url_title
        )
        
        assert result is True
        call_data = mock_post.call_args[1]['data']
        
        # Verify truncation
        assert len(call_data['title']) <= 250
        assert len(call_data['message']) <= 1024
        assert len(call_data['url']) <= 512
        assert len(call_data['url_title']) <= 100
    
    @patch('notifications.pushover.requests.post')
    def test_notification_timeout(self, mock_post):
        """Test that API calls have timeout configured."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response
        
        notifier = PushoverNotifier(
            app_token="test_app_token",
            user_key="test_user_key"
        )
        
        notifier._send_notification(title="Test", message="Message")
        
        # Verify timeout is set
        assert mock_post.call_args[1]['timeout'] == 10
