"""
Base Social Media Client for POSSE.

This module provides a base class for social media clients with common
authentication and posting functionality that can be inherited by
platform-specific implementations (Mastodon, Bluesky, etc.).
"""
import logging
import os
import hashlib
import tempfile
from typing import Optional, Dict, Any, List
from abc import ABC, abstractmethod
import requests


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
    
    # Configuration constants for image handling
    IMAGE_DOWNLOAD_TIMEOUT = 30  # seconds
    DEFAULT_IMAGE_EXTENSION = ".jpg"  # fallback for images without file extension
    
    # Platform-specific character limit (default, override in subclasses)
    MAX_POST_LENGTH = 300  # Conservative default
    
    def __init__(
        self,
        instance_url: str,
        access_token: Optional[str] = None,
        config_enabled: bool = True,
        account_name: Optional[str] = None,
        tags: Optional[List[str]] = None,
        max_post_length: Optional[int] = None
    ):
        """Initialize social media client with credentials.
        
        Args:
            instance_url: URL of the social media instance (e.g., https://mastodon.social)
            access_token: Access token for API authentication
            config_enabled: Whether posting is enabled in config.yml (default: True)
            account_name: Optional name for this account (for logging)
            tags: Optional list of tags to filter posts (empty or None means all posts)
            max_post_length: Optional maximum post length for this account (uses platform default if None)
            
        Note:
            Posting will be disabled if:
            - config_enabled is False
            - instance_url is not provided
            - access_token is missing
        """
        self.instance_url = instance_url
        self.access_token = access_token
        self.api: Optional[Any] = None
        self.account_name = account_name or "unnamed"
        self.tags = tags if tags is not None else []
        
        # Set max_post_length to instance-specific value or fall back to class constant
        if max_post_length is not None:
            self.max_post_length = max_post_length
        else:
            self.max_post_length = self.__class__.MAX_POST_LENGTH
        
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
                logger.info(f"{self.__class__.__name__} '{self.account_name}' initialized for {self.instance_url}")
            except Exception as e:
                logger.error(f"Failed to initialize {self.__class__.__name__} '{self.account_name}': {e}")
                self.enabled = False
                self.api = None
    
    @staticmethod
    def _get_image_cache_path(url: str, default_extension: str = ".jpg") -> str:
        """Generate a predictable cache path for an image URL.
        
        Uses SHA-256 hash of the URL to create a consistent filename, allowing
        for caching and reuse of previously downloaded images.
        
        Args:
            url: URL of the image
            default_extension: Default file extension if URL doesn't have one (default: .jpg)
            
        Returns:
            Full path to the cached image file
        """
        # Generate SHA-256 hash of URL for consistent filename
        url_hash = hashlib.sha256(url.encode()).hexdigest()
        
        # Extract file extension from URL, use default if not present
        suffix = os.path.splitext(url)[1] or default_extension
        
        # Create filename with hash and extension
        filename = f"{url_hash}{suffix}"
        
        # Use system temp directory for cache
        cache_path = os.path.join(tempfile.gettempdir(), "posse_image_cache", filename)
        
        return cache_path
    
    def _download_image(self, url: str) -> Optional[str]:
        """Download an image from a URL to a predictable cached location.
        
        If the image has already been downloaded (based on URL hash), returns
        the existing cached path without re-downloading.
        
        Args:
            url: URL of the image to download
            
        Returns:
            Path to the cached file containing the image, or None if download fails
            
        Note:
            Caller should use _remove_images() to clean up cached files when done.
            
            This method has inherent TOCTOU (time-of-check-time-of-use) race conditions
            in concurrent environments:
            - The file could be deleted between the existence check and use
            - The file could be partially written by another process
            
            These are acceptable trade-offs for this use case since:
            - Failed uploads will be logged but won't crash the posting process
            - Social media APIs will reject invalid/corrupted images with clear errors
            - The cache is temporary and will be cleaned up by the caller
        """
        try:
            # Get predictable cache path for this URL
            cache_path = SocialMediaClient._get_image_cache_path(url, self.DEFAULT_IMAGE_EXTENSION)
            
            # Check if already downloaded
            # Note: There's a TOCTOU race here - file could be deleted or incomplete
            # This is acceptable since upload failures are handled gracefully
            if os.path.exists(cache_path):
                logger.debug(f"Using cached image for {url} at {cache_path}")
                return cache_path
            
            # Create cache directory if it doesn't exist with restrictive permissions
            cache_dir = os.path.dirname(cache_path)
            os.makedirs(cache_dir, mode=0o700, exist_ok=True)
            
            # Download the image
            response = requests.get(url, timeout=self.IMAGE_DOWNLOAD_TIMEOUT)
            response.raise_for_status()
            
            # Write to cache file with restrictive permissions (600 = rw-------)
            # Use os.open with O_EXCL to prevent race conditions, but handle case where file exists
            try:
                fd = os.open(cache_path, os.O_CREAT | os.O_WRONLY | os.O_EXCL, 0o600)
            except FileExistsError:
                # File was created between check and open (race condition)
                # Use existing file - if it's incomplete, the upload will fail gracefully
                logger.debug(f"Using cached image for {url} at {cache_path} (created concurrently)")
                return cache_path
            
            try:
                os.write(fd, response.content)
            finally:
                os.close(fd)
            
            logger.debug(f"Downloaded image from {url} to {cache_path}")
            return cache_path
        except Exception as e:
            logger.error(f"Failed to download image from {url}: {e}")
            return None
    
    def _remove_images(self, media_urls: List[str]) -> None:
        """Remove cached images for the given URLs.
        
        This method looks up the cached files for the provided URLs and
        removes them from the file system. It's safe to call even if some
        images were not successfully downloaded.
        
        Args:
            media_urls: List of image URLs to remove from cache
        """
        for url in media_urls:
            try:
                cache_path = SocialMediaClient._get_image_cache_path(url, self.DEFAULT_IMAGE_EXTENSION)
                if os.path.exists(cache_path):
                    os.unlink(cache_path)
                    logger.debug(f"Removed cached image {cache_path}")
            except Exception as e:
                logger.warning(f"Failed to remove cached image for {url}: {e}")
    
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
    def from_config(cls, config: Dict[str, Any], platform_key: str) -> list["SocialMediaClient"]:
        """Create social media clients from configuration dictionary.
        
        This factory method reads configuration from config.yml and loads
        credentials from Docker secrets. Supports multiple accounts per platform.
        
        Configuration Format:
            platform:
              accounts:
                - name: "personal"
                  instance_url: "https://instance.com"
                  access_token_file: "/run/secrets/token"
                  tags: ["tech", "python"]  # Optional: filter posts by tags
                - name: "work"
                  instance_url: "https://work.instance.com"
                  access_token_file: "/run/secrets/work_token"
                  tags: []  # Empty list means all posts
        
        Args:
            config: Configuration dictionary from load_config()
            platform_key: Key in config dict for this platform (e.g., "mastodon", "bluesky")
            
        Returns:
            List of SocialMediaClient instances configured from config.yml and secrets.
            Returns empty list if no accounts are configured.
            
        Example:
            >>> from config import load_config
            >>> config = load_config()
            >>> clients = MastodonClient.from_config(config, "mastodon")
            >>> for client in clients:
            ...     if client.enabled:
            ...         client.post("Hello!")
        """
        from config import read_secret_file
        
        platform_config = config.get(platform_key, {})
        accounts_config = platform_config.get("accounts", [])
        
        clients = []
        for account_config in accounts_config:
            account_name = account_config.get("name", "unnamed")
            instance_url = account_config.get("instance_url", "")
            access_token_file = account_config.get("access_token_file")
            access_token = read_secret_file(access_token_file) if access_token_file else None
            tags = account_config.get("tags", [])
            max_post_length = account_config.get("max_post_length")
            
            # Account is enabled if it has required fields
            enabled = bool(instance_url and access_token)
            
            client = cls(
                instance_url=instance_url,
                access_token=access_token,
                config_enabled=enabled,
                account_name=account_name,
                tags=tags,
                max_post_length=max_post_length
            )
            clients.append(client)
        
        return clients
    
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
            ...     print(f"Posted: {result["url"]}")
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
            ...     print(f"Authenticated as: {account["username"]}")
        """
        pass
