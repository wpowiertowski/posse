"""
Pushover Notification Client for POSSE.

This module provides functionality to send push notifications via Pushover
for important events in the POSSE workflow, such as:
- New Ghost posts received and validated
- Posts queued for syndication
- Validation errors or system issues
- Error-level log messages (via PushoverLoggingHandler)

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

    For logging integration:
    >>> handler = PushoverLoggingHandler(notifier)
    >>> logging.getLogger().addHandler(handler)

API Reference:
    Pushover API: https://pushover.net/api

Security:
    - Credentials are loaded from Docker secrets
    - No credentials are logged or stored in code
    - API token and user key should be kept secret
"""
import os
import logging
import time
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

    def notify_webmention_success(self, post_title: str, post_url: str, target_name: str = "webmention target") -> bool:
        """Send notification when a webmention is successfully sent.

        Args:
            post_title: Title of the Ghost post
            post_url: URL of the published post
            target_name: Human-readable name of the webmention target

        Returns:
            True if notification sent successfully, False otherwise

        Example:
            >>> notifier.notify_webmention_success(
            ...     "My Post",
            ...     "https://blog.example.com/my-post",
            ...     "IndieWeb News"
            ... )
        """
        title = f"🌐 Webmention: {target_name}"
        message = f"Webmention accepted by {target_name}:\n{post_title}"
        return self._send_notification(
            title=title,
            message=message,
            priority=0,  # Normal priority
            url=post_url,
            url_title="View Post"
        )

    def notify_webmention_failure(self, post_title: str, post_url: str, error: str, target_name: str = "webmention target") -> bool:
        """Send notification when a webmention send fails.

        Args:
            post_title: Title of the Ghost post
            post_url: URL of the published post
            error: Error message describing the failure
            target_name: Human-readable name of the webmention target

        Returns:
            True if notification sent successfully, False otherwise

        Example:
            >>> notifier.notify_webmention_failure(
            ...     "My Post",
            ...     "https://blog.example.com/my-post",
            ...     "no_link_found: The source document does not contain a link to the target",
            ...     "IndieWeb News"
            ... )
        """
        title = f"❌ Webmention Failed: {target_name}"
        message = f"Webmention to {target_name} failed:\n{post_title}\n\nError: {error}"
        return self._send_notification(
            title=title,
            message=message,
            priority=1,  # High priority for errors
            url=post_url,
            url_title="View Post"
        )

    def notify_new_social_reply(
        self,
        platform: str,
        account_name: str,
        author: str,
        content_snippet: str,
        reply_url: str,
        post_url: Optional[str] = None
    ) -> bool:
        """Send notification when a new reply is discovered on Mastodon or Bluesky.

        Args:
            platform: Platform name ("Mastodon" or "Bluesky")
            account_name: Name of the social media account that received the reply
            author: Author handle of the reply (e.g. "@user@mastodon.social")
            content_snippet: Short preview of the reply content
            reply_url: Direct URL to the reply
            post_url: Optional URL of the original syndicated post

        Returns:
            True if notification sent successfully, False otherwise
        """
        title = f"💬 New {platform} Reply"
        snippet = content_snippet[:200] if content_snippet else ""
        message = f"{author} replied on {account_name}:\n{snippet}"
        return self._send_notification(
            title=title,
            message=message,
            priority=0,
            url=reply_url,
            url_title="View Reply"
        )

    def notify_new_webmention_reply(
        self,
        author_name: str,
        content_snippet: str,
        target_url: str
    ) -> bool:
        """Send notification when a new webmention reply is received.

        Args:
            author_name: Display name of the reply author
            content_snippet: Short preview of the reply content
            target_url: URL of the post the reply was sent to

        Returns:
            True if notification sent successfully, False otherwise
        """
        title = "💬 New Webmention Reply"
        snippet = content_snippet[:200] if content_snippet else ""
        message = f"{author_name} replied via webmention:\n{snippet}"
        return self._send_notification(
            title=title,
            message=message,
            priority=0,
            url=target_url,
            url_title="View Post"
        )

    def notify_log_error(self, logger_name: str, message: str, level: str = "ERROR") -> bool:
        """Send notification for error-level log messages.

        Args:
            logger_name: Name of the logger that produced the message
            message: The log message content
            level: Log level (ERROR, CRITICAL, etc.)

        Returns:
            True if notification sent successfully, False otherwise
        """
        title = f"🚨 POSSE {level}"
        # Include logger name for context, truncate message to fit
        full_message = f"[{logger_name}]\n{message}"
        return self._send_notification(
            title=title,
            message=full_message,
            priority=1  # High priority for errors
        )


class PushoverLoggingHandler(logging.Handler):
    """Custom logging handler that sends ERROR and CRITICAL logs to Pushover.

    This handler integrates with Python's logging system to automatically send
    push notifications for error-level log messages. It includes rate limiting
    to prevent notification spam during error storms.

    Attributes:
        notifier: PushoverNotifier instance used to send notifications
        rate_limit_seconds: Minimum seconds between notifications (default: 60)
        _last_notification_time: Timestamp of last sent notification

    Example:
        >>> notifier = PushoverNotifier.from_config(config)
        >>> handler = PushoverLoggingHandler(notifier, rate_limit_seconds=30)
        >>> handler.setLevel(logging.ERROR)
        >>> logging.getLogger().addHandler(handler)
    """

    def __init__(self, notifier: PushoverNotifier, rate_limit_seconds: int = 60):
        """Initialize the Pushover logging handler.

        Args:
            notifier: PushoverNotifier instance to use for sending notifications
            rate_limit_seconds: Minimum seconds between notifications to prevent
                              spam during error storms (default: 60)
        """
        super().__init__()
        self.notifier = notifier
        self.rate_limit_seconds = rate_limit_seconds
        self._last_notification_time: float = 0.0
        # Default to ERROR level
        self.setLevel(logging.ERROR)

    def emit(self, record: logging.LogRecord) -> None:
        """Emit a log record by sending it to Pushover.

        This method is called by the logging system for each log record that
        passes the handler's level filter. It applies rate limiting to prevent
        notification spam.

        Args:
            record: The log record to emit
        """
        # Skip if notifier is disabled
        if not self.notifier.enabled:
            return

        # Apply rate limiting
        current_time = time.time()
        if current_time - self._last_notification_time < self.rate_limit_seconds:
            return

        try:
            # Format the log message
            message = self.format(record)

            # Send notification
            success = self.notifier.notify_log_error(
                logger_name=record.name,
                message=message,
                level=record.levelname
            )

            if success:
                self._last_notification_time = current_time

        except Exception:
            # Don't let notification failures break logging
            self.handleError(record)
