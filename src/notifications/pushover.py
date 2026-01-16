"""
Pushover Notification Client for POSSE.

This module provides functionality to send push notifications via Pushover
for important events in the POSSE workflow, such as:
- New Ghost posts received and validated
- Posts queued for syndication
- Validation errors or system issues

Pushover Configuration:
    Configure via config.yml:
    - pushover.enabled: Set to true to enable notifications
    - pushover.app_token_file: Path to Docker secret for app token
    - pushover.user_key_file: Path to Docker secret for user key

Usage:
    >>> from config import load_config
    >>> config = load_config()
    >>> notifier = PushoverNotifier.from_config(config)
    >>> notifier.notify_post_received("Post Title", "post-slug")

API Reference:
    Pushover API: https://pushover.net/api
    
Security:
    - Credentials are loaded from Docker secrets
    - No credentials are logged or stored in code
    - API token and user key should be kept secret
"""
import os
import logging
from typing import Optional, Dict, Any
import requests


logger = logging.getLogger(__name__)


class PushoverNotifier:
    """Client for sending push notifications via Pushover service.
    
    This class encapsulates Pushover API interactions and provides
    convenient methods for sending notifications about POSSE events.
    
    Attributes:
        app_token: Pushover application API token (from PUSHOVER_APP_TOKEN env var)
        user_key: Pushover user/group key (from PUSHOVER_USER_KEY env var)
        enabled: Whether notifications are enabled (both credentials must be set)
        api_url: Pushover API endpoint URL
        
    Example:
        >>> notifier = PushoverNotifier()
        >>> if notifier.enabled:
        ...     notifier.notify_post_received("Welcome Post", "welcome")
    """
    
    # Pushover API endpoint
    PUSHOVER_API_URL = "https://api.pushover.net/1/messages.json"
    
    # Pushover field length limits
    MAX_TITLE_LENGTH = 250
    MAX_MESSAGE_LENGTH = 1024
    MAX_URL_LENGTH = 512
    MAX_URL_TITLE_LENGTH = 100
    
    def __init__(self, app_token: Optional[str] = None, user_key: Optional[str] = None, 
                 config_enabled: bool = True):
        """Initialize Pushover notifier with credentials.
        
        Args:
            app_token: Pushover application API token. If None, reads from 
                      PUSHOVER_APP_TOKEN environment variable (for backwards compatibility).
            user_key: Pushover user/group key. If None, reads from 
                     PUSHOVER_USER_KEY environment variable (for backwards compatibility).
            config_enabled: Whether Pushover is enabled in config.yml (default: True)
                      
        Note:
            Notifications will be disabled if:
            - config_enabled is False
            - Either credential is missing
        """
        self.app_token = app_token or os.environ.get("PUSHOVER_APP_TOKEN")
        self.user_key = user_key or os.environ.get("PUSHOVER_USER_KEY")
        self.enabled = (config_enabled and 
                       self.app_token is not None and 
                       self.user_key is not None)
        
        if not config_enabled:
            logger.info("Pushover notifications disabled via config.yml")
        elif not self.enabled:
            logger.warning(
                "Pushover notifications disabled: missing credentials"
            )
        else:
            logger.info("Pushover notifications enabled")
    
    @classmethod
    def from_config(cls, config: Dict[str, Any]) -> "PushoverNotifier":
        """Create PushoverNotifier from configuration dictionary.
        
        This factory method reads configuration from config.yml and Docker secrets
        to initialize the notifier.
        
        Args:
            config: Configuration dictionary from config.yml
            
        Returns:
            Initialized PushoverNotifier instance
            
        Example:
            >>> from config import load_config
            >>> config = load_config()
            >>> notifier = PushoverNotifier.from_config(config)
        """
        from config import read_secret_file
        
        pushover_config = config.get("pushover", {})
        enabled = pushover_config.get("enabled", False)
        
        if not enabled:
            return cls(config_enabled=False)
        
        # Read credentials from Docker secrets
        app_token_file = pushover_config.get("app_token_file", "/run/secrets/pushover_app_token")
        user_key_file = pushover_config.get("user_key_file", "/run/secrets/pushover_user_key")
        
        app_token = read_secret_file(app_token_file)
        user_key = read_secret_file(user_key_file)
        
        return cls(app_token=app_token, user_key=user_key, config_enabled=True)
    
    def _send_notification(
        self,
        title: str,
        message: str,
        priority: int = 0,
        url: Optional[str] = None,
        url_title: Optional[str] = None
    ) -> bool:
        """Send a push notification via Pushover API.
        
        Args:
            title: Notification title (up to 250 characters)
            message: Notification message (up to 1024 characters)
            priority: Priority level (-2 to 2):
                     -2: Lowest priority (no sound/vibration)
                     -1: Low priority (no sound)
                      0: Normal priority (default)
                      1: High priority (bypasses quiet hours)
                      2: Emergency (requires acknowledgment)
            url: Optional URL to include in notification
            url_title: Optional title for the URL
            
        Returns:
            True if notification sent successfully, False otherwise
            
        Raises:
            Does not raise exceptions - logs errors and returns False
        """
        if not self.enabled:
            logger.debug(
                f"Pushover notification skipped (disabled): {title} - {message}"
            )
            return False
        
        try:
            payload = {
                "token": self.app_token,
                "user": self.user_key,
                "title": title[:self.MAX_TITLE_LENGTH],
                "message": message[:self.MAX_MESSAGE_LENGTH],
                "priority": priority,
            }
            
            if url:
                payload["url"] = url[:self.MAX_URL_LENGTH]
                if url_title:
                    payload["url_title"] = url_title[:self.MAX_URL_TITLE_LENGTH]
            
            response = requests.post(
                self.PUSHOVER_API_URL,
                data=payload,
                timeout=10  # 10 second timeout
            )
            
            response.raise_for_status()
            
            logger.info(f"Pushover notification sent: {title}")
            return True
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to send Pushover notification: {e}")
            return False
    
    def notify_post_received(self, post_title: str, post_id: str) -> bool:
        """Send notification when a Ghost post is received and validated.
        
        Args:
            post_title: Title of the Ghost post
            post_id: ID of the Ghost post
            
        Returns:
            True if notification sent successfully, False otherwise
            
        Example:
            >>> notifier.notify_post_received("Welcome to Ghost", "abc123")
        """
        title = "📝 Post Received"
        message = f"New post received and validated:\n{post_title}"
        return self._send_notification(
            title=title,
            message=message,
            priority=0  # Normal priority
        )
    
    def notify_post_queued(self, post_title: str, post_url: str) -> bool:
        """Send notification when a post is queued for syndication.
        
        Args:
            post_title: Title of the Ghost post
            post_url: URL of the published post
            
        Returns:
            True if notification sent successfully, False otherwise
            
        Example:
            >>> notifier.notify_post_queued(
            ...     "Welcome to Ghost",
            ...     "https://blog.example.com/welcome"
            ... )
        """
        title = "✅ Post Queued"
        message = f"Post queued for syndication:\n{post_title}"
        return self._send_notification(
            title=title,
            message=message,
            priority=0,  # Normal priority
            url=post_url,
            url_title="View Post"
        )
    
    def notify_validation_error(self, details: str) -> bool:
        """Send notification when post validation fails.
        
        Args:
            details: Error details from validation failure
            
        Returns:
            True if notification sent successfully, False otherwise
            
        Example:
            >>> notifier.notify_validation_error("Missing required field: title")
        """
        title = "⚠️ Validation Error"
        message = f"Failed to validate Ghost post:\n{details}"
        return self._send_notification(
            title=title,
            message=message,
            priority=1  # High priority for errors
        )
    
    def notify_post_success(self, post_title: str, account_name: str, platform: str, post_url: Optional[str] = None) -> bool:
        """Send notification when a post is successfully syndicated to an account.
        
        Args:
            post_title: Title of the Ghost post
            account_name: Name of the social media account
            platform: Platform name ("Mastodon" or "Bluesky")
            post_url: URL of the posted content (optional)
            
        Returns:
            True if notification sent successfully, False otherwise
            
        Example:
            >>> notifier.notify_post_success(
            ...     "Welcome Post",
            ...     "personal",
            ...     "Mastodon",
            ...     "https://mastodon.social/@user/123"
            ... )
        """
        title = f"✅ Posted to {platform}"
        message = f"Successfully posted to {account_name}:\n{post_title}"
        return self._send_notification(
            title=title,
            message=message,
            priority=0,  # Normal priority
            url=post_url,
            url_title=f"View on {platform}" if post_url else None
        )
    
    def notify_post_failure(self, post_title: str, account_name: str, platform: str, error: str) -> bool:
        """Send notification when posting to an account fails.
        
        Args:
            post_title: Title of the Ghost post
            account_name: Name of the social media account
            platform: Platform name ("Mastodon" or "Bluesky")
            error: Error message describing the failure
            
        Returns:
            True if notification sent successfully, False otherwise
            
        Example:
            >>> notifier.notify_post_failure(
            ...     "Welcome Post",
            ...     "personal",
            ...     "Mastodon",
            ...     "Authentication failed"
            ... )
        """
        title = f"❌ Failed to post to {platform}"
        message = f"Failed to post to {account_name}:\n{post_title}\n\nError: {error}"
        return self._send_notification(
            title=title,
            message=message,
            priority=1  # High priority for errors
        )
    
    def send_test_notification(self) -> bool:
        """Send a low-priority test notification to verify Pushover service is working.
        
        This method is used by the healthcheck endpoint to verify that the
        Pushover notification service is properly configured and operational.
        
        Returns:
            True if test notification sent successfully, False otherwise
            
        Example:
            >>> notifier = PushoverNotifier.from_config(config)
            >>> if notifier.send_test_notification():
            ...     print("Pushover service is healthy")
        """
        title = "🔔 POSSE Health Check"
        message = "This is a test notification from the POSSE healthcheck endpoint."
        return self._send_notification(
            title=title,
            message=message,
            priority=-1  # Low priority (no sound)
        )
