"""
Mastodon Client for POSSE.

This module provides functionality to post content to Mastodon accounts 
from Ghost blog posts.

Mastodon Configuration:
    Configure via config.yml:
    - mastodon.enabled: Set to true to enable Mastodon posting
    - mastodon.instance_url: URL of the Mastodon instance (e.g., https://mastodon.social)
    - mastodon.access_token_file: Path to Docker secret for access token

Usage:
    >>> from config import load_config
    >>> config = load_config()
    >>> client = MastodonClient.from_config(config)
    >>> if client.enabled:
    ...     result = client.post("Hello from POSSE!")
    ...     print(f"Posted: {result['url']}")

Authentication:
    You need an access token from your Mastodon instance. You can obtain one by:
    1. Going to your Mastodon instance settings
    2. Navigate to Development -> New Application
    3. Create a new application with 'write:statuses' scope
    4. Copy the access token

API Reference:
    Mastodon API: https://docs.joinmastodon.org/api/
    Mastodon.py: https://mastodonpy.readthedocs.io/

Security:
    - Access token is loaded from Docker secrets
    - No credentials are logged or stored in code
    - Access token should be kept secret
"""
import logging
from typing import Optional, Dict, Any
from mastodon import Mastodon, MastodonError

from social.base_client import SocialMediaClient


logger = logging.getLogger(__name__)


class MastodonClient(SocialMediaClient):
    """Client for posting to Mastodon instances.
    
    This class extends SocialMediaClient to provide Mastodon-specific
    functionality using the Mastodon.py library.
    
    Attributes:
        instance_url: URL of the Mastodon instance (e.g., https://mastodon.social)
        access_token: Access token for authenticated API calls
        enabled: Whether Mastodon posting is enabled
        api: Mastodon API client instance (None if not enabled)
        
    Example:
        >>> client = MastodonClient(
        ...     instance_url="https://mastodon.social",
        ...     access_token="your_access_token"
        ... )
        >>> if client.enabled:
        ...     client.post("Hello Mastodon!")
    """
    
    def _initialize_api(self) -> None:
        """Initialize the Mastodon API client.
        
        Sets up the Mastodon.py client with the access token and instance URL.
        
        Raises:
            Exception: If Mastodon API initialization fails
        """
        self.api = Mastodon(
            access_token=self.access_token,
            api_base_url=self.instance_url
        )
    
    @classmethod
    def from_config(cls, config: Dict[str, Any]) -> 'MastodonClient':
        """Create MastodonClient from configuration dictionary.
        
        This factory method reads configuration from config.yml and loads
        credentials from Docker secrets.
        
        Args:
            config: Configuration dictionary from load_config()
            
        Returns:
            MastodonClient instance configured from config.yml and secrets
            
        Example:
            >>> from config import load_config
            >>> config = load_config()
            >>> client = MastodonClient.from_config(config)
        """
        return super(MastodonClient, cls).from_config(config, 'mastodon')
    
    def post(
        self,
        content: str,
        visibility: str = 'public',
        sensitive: bool = False,
        spoiler_text: Optional[str] = None,
        **kwargs
    ) -> Optional[Dict[str, Any]]:
        """Post content to Mastodon.
        
        Args:
            content: Text content of the status (max 500 characters for most instances)
            visibility: Post visibility ('public', 'unlisted', 'private', 'direct')
            sensitive: Whether to mark the post as sensitive content
            spoiler_text: Content warning text (if provided, post will be hidden behind CW)
            **kwargs: Additional Mastodon-specific options
            
        Returns:
            Dictionary containing the posted status information, or None if posting failed
            
        Example:
            >>> result = client.post("Hello from POSSE!")
            >>> if result:
            ...     print(f"Posted: {result['url']}")
        """
        if not self.enabled or not self.api:
            logger.warning("Cannot post to Mastodon: client not enabled")
            return None
        
        try:
            result = self.api.status_post(
                status=content,
                visibility=visibility,
                sensitive=sensitive,
                spoiler_text=spoiler_text
            )
            logger.info(f"Successfully posted status to Mastodon: {result['url']}")
            return result
        except MastodonError as e:
            logger.error(f"Failed to post status to Mastodon: {e}")
            return None
    
    def verify_credentials(self) -> Optional[Dict[str, Any]]:
        """Verify that the access token is valid and get account information.
        
        This method tests the connection and credentials by fetching the
        authenticated user's account information.
        
        Returns:
            Dictionary containing account information, or None if verification failed
            
        Example:
            >>> account = client.verify_credentials()
            >>> if account:
            ...     print(f"Authenticated as: @{account['username']}")
        """
        if not self.enabled or not self.api:
            logger.warning("Cannot verify credentials: client not enabled")
            return None
        
        try:
            account = self.api.account_verify_credentials()
            logger.info(f"Verified credentials for @{account['username']}")
            return account
        except MastodonError as e:
            logger.error(f"Failed to verify credentials: {e}")
            return None
