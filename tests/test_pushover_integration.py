"""
Integration Tests for Pushover Notification Module.

This test suite validates that Pushover notifications work end-to-end
with actual secrets and the real Pushover API when configured.

These tests are designed to:
1. Check if config.yml has notifications enabled
2. Check if secrets are accessible (Docker secrets or files)
3. Send an actual test notification to verify the complete setup

Test Strategy:
    - Tests run conditionally based on secret availability
    - If secrets are not available, tests are skipped (not failed)
    - When secrets are available, an actual API call is made
    - This verifies the entire notification pipeline works

Running Tests:
    $ pytest tests/test_pushover_integration.py -v
    
    # With Docker secrets mounted:
    $ docker compose run --rm app pytest tests/test_pushover_integration.py -v
"""
import os
import pytest
from pathlib import Path

from config import load_config, read_secret_file
from notifications.pushover import PushoverNotifier


class TestPushoverIntegration:
    """Integration tests for actual Pushover notification sending."""
    
    def _get_secrets_from_config(self):
        """Helper to read secrets from config.yml paths.
        
        Returns:
            tuple: (app_token, user_key, enabled) or (None, None, False)
        """
        config = load_config()
        pushover_config = config.get('pushover', {})
        enabled = pushover_config.get('enabled', False)
        
        if not enabled:
            return None, None, False
        
        # Try to read from Docker secrets paths first
        app_token_file = pushover_config.get('app_token_file', '/run/secrets/pushover_app_token')
        user_key_file = pushover_config.get('user_key_file', '/run/secrets/pushover_user_key')
        
        app_token = read_secret_file(app_token_file)
        user_key = read_secret_file(user_key_file)
        
        # Fallback to local secrets/ directory for development/testing
        if not app_token:
            local_app_token_file = Path('secrets/pushover_app_token.txt')
            if local_app_token_file.exists():
                app_token = read_secret_file(str(local_app_token_file))
        
        if not user_key:
            local_user_key_file = Path('secrets/pushover_user_key.txt')
            if local_user_key_file.exists():
                user_key = read_secret_file(str(local_user_key_file))
        
        # Final fallback to environment variables for backwards compatibility
        if not app_token:
            app_token = os.environ.get('PUSHOVER_APP_TOKEN')
        if not user_key:
            user_key = os.environ.get('PUSHOVER_USER_KEY')
        
        return app_token, user_key, enabled
    
    def _check_secrets_directory(self):
        """Helper to check if secrets directory exists with required files.
        
        Returns:
            bool: True if secrets directory has required files
        """
        secrets_dir = Path('secrets')
        if not secrets_dir.exists():
            return False
        
        app_token_file = secrets_dir / 'pushover_app_token.txt'
        user_key_file = secrets_dir / 'pushover_user_key.txt'
        
        return app_token_file.exists() and user_key_file.exists()
    
    def test_config_has_notifications_enabled(self):
        """Test that config.yml has pushover.enabled set to true."""
        config = load_config()
        pushover_config = config.get('pushover', {})
        
        # Verify notifications are enabled in config.yml
        assert pushover_config.get('enabled') is True, \
            "Pushover notifications should be enabled in config.yml"
        
        # Verify secret file paths are configured
        assert 'app_token_file' in pushover_config, \
            "app_token_file should be configured in config.yml"
        assert 'user_key_file' in pushover_config, \
            "user_key_file should be configured in config.yml"
    
    def test_secrets_accessibility(self):
        """Test that secrets can be accessed when configured.
        
        This test verifies that when notifications are enabled,
        the application can read the required secrets from either:
        - Docker secrets (/run/secrets/)
        - Local secrets directory (secrets/)
        - Environment variables
        """
        app_token, user_key, enabled = self._get_secrets_from_config()
        
        if not enabled:
            pytest.skip("Pushover notifications are disabled in config.yml")
        
        # Check if secrets directory exists (for local development)
        has_secrets_dir = self._check_secrets_directory()
        
        # Check if Docker secrets exist (for Docker Compose)
        has_docker_secrets = (
            Path('/run/secrets/pushover_app_token').exists() and
            Path('/run/secrets/pushover_user_key').exists()
        )
        
        # Check if environment variables are set (for legacy support)
        has_env_vars = (
            os.environ.get('PUSHOVER_APP_TOKEN') is not None and
            os.environ.get('PUSHOVER_USER_KEY') is not None
        )
        
        # At least one method should provide secrets
        assert has_secrets_dir or has_docker_secrets or has_env_vars, \
            ("Pushover notifications are enabled in config.yml but secrets are not accessible. "
             "Please set up secrets via: "
             "1) Docker secrets (/run/secrets/), "
             "2) Local secrets directory (secrets/), or "
             "3) Environment variables (PUSHOVER_APP_TOKEN, PUSHOVER_USER_KEY)")
        
        # Verify secrets were actually read
        assert app_token is not None, \
            "Pushover app token should be readable from configured sources"
        assert user_key is not None, \
            "Pushover user key should be readable from configured sources"
        assert len(app_token) > 0, \
            "Pushover app token should not be empty"
        assert len(user_key) > 0, \
            "Pushover user key should not be empty"
    
    def test_send_actual_notification(self):
        """Test sending an actual notification through Pushover API.
        
        This test sends a real notification to verify the complete setup:
        - Config is enabled
        - Secrets are accessible
        - Pushover API accepts the credentials
        - Notification is delivered
        
        The test is skipped if secrets are not available.
        """
        app_token, user_key, enabled = self._get_secrets_from_config()
        
        # Skip if notifications are disabled or secrets are missing
        if not enabled:
            pytest.skip("Pushover notifications are disabled in config.yml")
        
        if not app_token or not user_key:
            pytest.skip(
                "Pushover secrets are not available. "
                "Set up secrets in Docker secrets, secrets/ directory, or environment variables."
            )
        
        # Create notifier with actual credentials
        notifier = PushoverNotifier(
            app_token=app_token,
            user_key=user_key,
            config_enabled=True
        )
        
        # Verify notifier is enabled
        assert notifier.enabled is True, \
            "Notifier should be enabled with valid credentials"
        
        # Send a test notification
        result = notifier._send_notification(
            title="🧪 POSSE Integration Test",
            message="This is a test notification from the POSSE integration test suite. "
                   "If you receive this, your Pushover notification setup is working correctly!",
            priority=0  # Normal priority
        )
        
        # Verify notification was sent successfully
        assert result is True, \
            ("Failed to send Pushover notification. "
             "Check that your app token and user key are correct, "
             "and that your Pushover account is active.")
    
    def test_notifier_from_config(self):
        """Test creating notifier from config.yml with actual secrets.
        
        This test verifies the from_config() factory method works correctly
        with the actual configuration and secrets.
        """
        config = load_config()
        notifier = PushoverNotifier.from_config(config)
        
        # Check if notifier is enabled based on config
        pushover_config = config.get('pushover', {})
        config_enabled = pushover_config.get('enabled', False)
        
        if not config_enabled:
            assert notifier.enabled is False, \
                "Notifier should be disabled when config.enabled is False"
            pytest.skip("Pushover is disabled in config.yml")
        
        # If config is enabled, check if secrets are available
        app_token, user_key, _ = self._get_secrets_from_config()
        
        if not app_token or not user_key:
            # Secrets not available - notifier should be disabled
            assert notifier.enabled is False, \
                "Notifier should be disabled when secrets are missing"
            pytest.skip("Pushover secrets are not available")
        
        # Config is enabled and secrets are available
        assert notifier.enabled is True, \
            "Notifier should be enabled when config.enabled is True and secrets are available"
        assert notifier.app_token == app_token
        assert notifier.user_key == user_key
    
    def test_notification_methods_with_real_api(self):
        """Test all notification methods with actual API calls.
        
        This comprehensive test sends notifications using all three
        notification methods to verify they work correctly.
        
        The test is skipped if secrets are not available.
        """
        app_token, user_key, enabled = self._get_secrets_from_config()
        
        if not enabled or not app_token or not user_key:
            pytest.skip("Pushover is not fully configured with valid secrets")
        
        notifier = PushoverNotifier(
            app_token=app_token,
            user_key=user_key,
            config_enabled=True
        )
        
        # Test 1: Post received notification
        result1 = notifier.notify_post_received(
            post_title="Integration Test Post",
            post_id="test-123"
        )
        assert result1 is True, "Post received notification should be sent successfully"
        
        # Test 2: Post queued notification
        result2 = notifier.notify_post_queued(
            post_title="Integration Test Post",
            post_url="https://example.com/test-post"
        )
        assert result2 is True, "Post queued notification should be sent successfully"
        
        # Test 3: Validation error notification
        result3 = notifier.notify_validation_error(
            details="Integration test: simulated validation error"
        )
        assert result3 is True, "Validation error notification should be sent successfully"
