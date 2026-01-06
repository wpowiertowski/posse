"""
Base Social Media Client for POSSE.

This module provides a base class for social media clients with common
authentication and posting functionality that can be inherited by
platform-specific implementations (Mastodon, Bluesky, etc.).
"""
import logging
from typing import Optional, Dict, Any
from abc import ABC, abstractmethod


logger = logging.getLogger(__name__)


class SocialMediaClient(ABC):
    """Abstract base class for social media clients.
    
    This class provides common functionality for authentication and posting
    to social media platforms. Platform-specific implementations should
    inherit from this class and implement the abstract methods.
    
    Attributes:
        instance_url: URL of the social media instance/server
        access_token: Access token for authenticated API calls
        enabled: Whether posting is enabled for this client
        api: Platform-specific API client instance (None if not enabled)
        
    Example:
        >>> class MyClient(SocialMediaClient):
        ...     def _initialize_api(self):
        ...         # Platform-specific initialization
        ...         pass
        ...     
        ...     def post(self, content, **kwargs):
        ...         # Platform-specific posting
        ...         pass
    """
    
    def __init__(
        self,
        instance_url: str,
        access_token: Optional[str] = None,
        config_enabled: bool = True
    ):
        """Initialize social media client with credentials.
        
        Args:
            instance_url: URL of the social media instance (e.g., https://mastodon.social)
            access_token: Access token for API authentication
            config_enabled: Whether posting is enabled in config.yml (default: True)
            
        Note:
            Posting will be disabled if:
            - config_enabled is False
            - instance_url is not provided
            - access_token is missing
        """
        self.instance_url = instance_url
        self.access_token = access_token
        self.api: Optional[Any] = None
        
        # Determine if client is enabled
        self.enabled = bool(
            config_enabled and
            instance_url and  # Check for non-empty string
            access_token is not None
        )
        
        if not config_enabled:
            logger.info(f"{self.__class__.__name__} posting disabled via config.yml")
        elif not self.enabled:
            logger.warning(
                f"{self.__class__.__name__} posting disabled: missing instance URL or access token"
            )
        else:
            try:
                # Initialize platform-specific API client
                self._initialize_api()
                logger.info(f"{self.__class__.__name__} initialized for {self.instance_url}")
            except Exception as e:
                logger.error(f"Failed to initialize {self.__class__.__name__}: {e}")
                self.enabled = False
                self.api = None
    
    @abstractmethod
    def _initialize_api(self) -> None:
        """Initialize the platform-specific API client.
        
        This method should be implemented by subclasses to set up
        the API client with the appropriate credentials.
        
        The implementation should set self.api to the initialized client.
        
        Raises:
            Exception: If API initialization fails
        """
        pass
    
    @classmethod
    def from_config(cls, config: Dict[str, Any], platform_key: str) -> 'SocialMediaClient':
        """Create a social media client from configuration dictionary.
        
        This factory method reads configuration from config.yml and loads
        credentials from Docker secrets.
        
        Args:
            config: Configuration dictionary from load_config()
            platform_key: Key in config dict for this platform (e.g., 'mastodon', 'bluesky')
            
        Returns:
            SocialMediaClient instance configured from config.yml and secrets
            
        Example:
            >>> from config import load_config
            >>> config = load_config()
            >>> client = MastodonClient.from_config(config, 'mastodon')
        """
        from config import read_secret_file
        
        platform_config = config.get(platform_key, {})
        
        # Check if platform is enabled in config
        enabled = platform_config.get('enabled', False)
        if not enabled:
            return cls(instance_url="", config_enabled=False)
        
        # Get instance URL from config
        instance_url = platform_config.get('instance_url', '')
        
        # Read access token from Docker secret
        access_token_file = platform_config.get('access_token_file')
        access_token = read_secret_file(access_token_file) if access_token_file else None
        
        return cls(
            instance_url=instance_url,
            access_token=access_token,
            config_enabled=enabled
        )
    
    @abstractmethod
    def post(
        self,
        content: str,
        **kwargs
    ) -> Optional[Dict[str, Any]]:
        """Post content to the social media platform.
        
        This method should be implemented by subclasses to handle
        platform-specific posting logic.
        
        Args:
            content: Text content to post
            **kwargs: Platform-specific options (visibility, media, etc.)
            
        Returns:
            Dictionary containing the posted content information, or None if posting failed
            
        Example:
            >>> result = client.post("Hello from POSSE!")
            >>> if result:
            ...     print(f"Posted: {result['url']}")
        """
        pass
    
    @abstractmethod
    def verify_credentials(self) -> Optional[Dict[str, Any]]:
        """Verify that the access token is valid and get account information.
        
        This method should be implemented by subclasses to verify
        credentials using platform-specific API calls.
        
        Returns:
            Dictionary containing account information, or None if verification failed
            
        Example:
            >>> account = client.verify_credentials()
            >>> if account:
            ...     print(f"Authenticated as: {account['username']}")
        """
        pass
