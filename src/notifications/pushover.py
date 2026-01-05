"""
Pushover Notification Client for POSSE.

This module provides functionality to send push notifications via Pushover
for important events in the POSSE workflow, such as:
- New Ghost posts received and validated
- Posts queued for syndication
- Validation errors or system issues

Pushover Configuration:
    Requires two environment variables:
    - PUSHOVER_APP_TOKEN: Your Pushover application API token
    - PUSHOVER_USER_KEY: Your Pushover user/group key

Usage:
    >>> notifier = PushoverNotifier()
    >>> notifier.notify_post_received("Post Title", "post-slug")
    
    >>> notifier.notify_post_queued("Post Title", "https://example.com/post")
    
    >>> notifier.notify_validation_error("Post Title", "Missing required field")

API Reference:
    Pushover API: https://pushover.net/api
    
Security:
    - Credentials are loaded from environment variables only
    - No credentials are logged or stored in code
    - API token and user key should be kept secret
"""
import os
import logging
from typing import Optional
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
    
    PUSHOVER_API_URL = "https://api.pushover.net/1/messages.json"
    
    def __init__(self, app_token: Optional[str] = None, user_key: Optional[str] = None):
        """Initialize Pushover notifier with credentials.
        
        Args:
            app_token: Pushover application API token. If None, reads from 
                      PUSHOVER_APP_TOKEN environment variable.
            user_key: Pushover user/group key. If None, reads from 
                     PUSHOVER_USER_KEY environment variable.
                     
        Note:
            If either credential is missing, notifications will be disabled
            and methods will log warnings instead of sending notifications.
        """
        self.app_token = app_token or os.environ.get('PUSHOVER_APP_TOKEN')
        self.user_key = user_key or os.environ.get('PUSHOVER_USER_KEY')
        self.enabled = bool(self.app_token and self.user_key)
        
        if not self.enabled:
            logger.warning(
                "Pushover notifications disabled: missing PUSHOVER_APP_TOKEN "
                "or PUSHOVER_USER_KEY environment variables"
            )
        else:
            logger.info("Pushover notifications enabled")
    
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
                "title": title[:250],  # Enforce Pushover limit
                "message": message[:1024],  # Enforce Pushover limit
                "priority": priority,
            }
            
            if url:
                payload["url"] = url[:512]  # Enforce Pushover limit
                if url_title:
                    payload["url_title"] = url_title[:100]  # Enforce Pushover limit
            
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
