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
    ...     result = client.post_status("Hello from POSSE!")
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

from config import read_secret_file


logger = logging.getLogger(__name__)


class MastodonClient:
    """Client for posting to Mastodon instances.
    
    This class encapsulates Mastodon API interactions using the Mastodon.py
    library and provides methods for posting statuses.
    
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
        ...     client.post_status("Hello Mastodon!")
    """
    
    def __init__(
        self,
        instance_url: str,
        access_token: Optional[str] = None,
        config_enabled: bool = True
    ):
        """Initialize Mastodon client with credentials.
        
        Args:
            instance_url: URL of the Mastodon instance (e.g., https://mastodon.social)
            access_token: Access token for API authentication
            config_enabled: Whether Mastodon is enabled in config.yml (default: True)
            
        Note:
            Mastodon posting will be disabled if:
            - config_enabled is False
            - instance_url is not provided
            - access_token is missing
        """
        self.instance_url = instance_url
        self.access_token = access_token
        self.api: Optional[Mastodon] = None
        
        # Determine if client is enabled
        self.enabled = bool(
            config_enabled and
            instance_url and  # Check for non-empty string
            access_token is not None
        )
        
        if not config_enabled:
            logger.info("Mastodon posting disabled via config.yml")
        elif not self.enabled:
            logger.warning(
                "Mastodon posting disabled: missing instance URL or access token"
            )
        else:
            try:
                # Initialize Mastodon API client with just access token
                self.api = Mastodon(
                    access_token=self.access_token,
                    api_base_url=self.instance_url
                )
                logger.info(f"Mastodon client initialized for {self.instance_url}")
            except Exception as e:
                logger.error(f"Failed to initialize Mastodon client: {e}")
                self.enabled = False
                self.api = None
    
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
        mastodon_config = config.get('mastodon', {})
        
        # Check if Mastodon is enabled in config
        enabled = mastodon_config.get('enabled', False)
        if not enabled:
            return cls(instance_url="", config_enabled=False)
        
        # Get instance URL from config
        instance_url = mastodon_config.get('instance_url', '')
        
        # Read access token from Docker secret
        access_token_file = mastodon_config.get('access_token_file')
        access_token = read_secret_file(access_token_file) if access_token_file else None
        
        return cls(
            instance_url=instance_url,
            access_token=access_token,
            config_enabled=enabled
        )
    
    def post_status(
        self,
        status: str,
        visibility: str = 'public',
        sensitive: bool = False,
        spoiler_text: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Post a status to Mastodon.
        
        Args:
            status: Text content of the status (max 500 characters for most instances)
            visibility: Post visibility ('public', 'unlisted', 'private', 'direct')
            sensitive: Whether to mark the post as sensitive content
            spoiler_text: Content warning text (if provided, post will be hidden behind CW)
            
        Returns:
            Dictionary containing the posted status information, or None if posting failed
            
        Example:
            >>> result = client.post_status("Hello from POSSE!")
            >>> if result:
            ...     print(f"Posted: {result['url']}")
        """
        if not self.enabled or not self.api:
            logger.warning("Cannot post to Mastodon: client not enabled")
            return None
        
        try:
            result = self.api.status_post(
                status=status,
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
