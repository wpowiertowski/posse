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
    ...     print(f"Posted: {result["url"]}")

Authentication:
    You need an access token from your Mastodon instance. You can obtain one by:
    1. Going to your Mastodon instance settings
    2. Navigate to Development -> New Application
    3. Create a new application with "write:statuses" scope
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
from typing import Optional, Dict, Any, List, TYPE_CHECKING
from mastodon import Mastodon, MastodonError

from social.base_client import SocialMediaClient

if TYPE_CHECKING:
    from notifications.pushover import PushoverNotifier

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
        notifier: PushoverNotifier instance for error notifications (optional)
        
    Example:
        >>> client = MastodonClient(
        ...     instance_url="https://mastodon.social",
        ...     access_token="your_access_token"
        ... )
        >>> if client.enabled:
        ...     client.post("Hello Mastodon!")
    """
    
    # Mastodon character limit (500 for most instances)
    MAX_POST_LENGTH = 500
    
    def __init__(self, notifier: Optional["PushoverNotifier"] = None, **kwargs):
        """Initialize MastodonClient with optional notifier.
        
        Args:
            notifier: PushoverNotifier instance for error notifications
            **kwargs: Arguments passed to SocialMediaClient parent class
        """
        self.notifier = notifier
        super().__init__(**kwargs)
    
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
        
        # Verify credentials immediately to catch authentication issues
        try:
            account = self.api.account_verify_credentials()
            logger.info(f"MastodonClient '{self.account_name}' authenticated as @{account['username']}")
        except MastodonError as e:
            error_msg = f"Authentication failed for '{self.account_name}': {e}"
            logger.error(error_msg)
            if self.notifier:
                self.notifier.notify_post_failure(
                    "Authentication Failed",
                    self.account_name,
                    "Mastodon",
                    "Invalid or expired access token. Please regenerate the token."
                )
            raise Exception(error_msg)
    
    @classmethod
    def from_config(cls, config: Dict[str, Any], notifier: Optional["PushoverNotifier"] = None) -> list["MastodonClient"]:
        """Create MastodonClient instances from configuration dictionary.
        
        This factory method reads configuration from config.yml and loads
        credentials from Docker secrets. Supports multiple accounts.
        
        Args:
            config: Configuration dictionary from load_config()
            notifier: PushoverNotifier instance for error notifications
            
        Returns:
            List of MastodonClient instances
            
        Example:
            >>> from config import load_config
            >>> config = load_config()
            >>> clients = MastodonClient.from_config(config)
            >>> for client in clients:
            ...     if client.enabled:
            ...         client.post("Hello!")
        """
        clients = super(MastodonClient, cls).from_config(config, "mastodon")
        # Inject notifier into all clients
        for client in clients:
            client.notifier = notifier
        return clients
    
    def post(
        self,
        content: str,
        visibility: str = "public",
        sensitive: bool = False,
        spoiler_text: Optional[str] = None,
        media_urls: Optional[List[str]] = None,
        media_descriptions: Optional[List[str]] = None,
        **kwargs
    ) -> Optional[Dict[str, Any]]:
        """Post content to Mastodon.
        
        Args:
            content: Text content of the status (max 500 characters for most instances)
            visibility: Post visibility ("public", "unlisted", "private", "direct")
            sensitive: Whether to mark the post as sensitive content
            spoiler_text: Content warning text (if provided, post will be hidden behind CW)
            media_urls: Optional list of image URLs to attach to the post
            media_descriptions: Optional list of alt text descriptions for images (should match media_urls length)
            **kwargs: Additional Mastodon-specific options
            
        Returns:
            Dictionary containing the posted status information, or None if posting failed
            
        Note:
            Images are downloaded and cached. Call _remove_images() separately to clean up.
            
        Example:
            >>> result = client.post("Hello from POSSE!")
            >>> if result:
            ...     print(f"Posted: {result["url"]}")
            
            >>> # Post with an image
            >>> result = client.post(
            ...     "Check out this photo!",
            ...     media_urls=["https://example.com/image.jpg"],
            ...     media_descriptions=["A beautiful sunset"]
            ... )
        """
        if not self.enabled or not self.api:
            logger.warning("Cannot post to Mastodon: client not enabled")
            return None
        
        media_ids = []
        
        try:
            # Upload media if provided
            if media_urls:
                for i, url in enumerate(media_urls):
                    if i > 3:
                        # only up to 4 images allowed on many instances
                        break
                    # Download image to cached file
                    temp_path = self._download_image(url)
                    if not temp_path:
                        error_msg = f"Failed to download image: {url}"
                        logger.warning(f"Skipping media upload for {url} due to download failure")
                        if self.notifier:
                            self.notifier.notify_post_failure(
                                "Media Download Failed",
                                self.account_name,
                                "Mastodon",
                                error_msg
                            )
                        continue
                    
                    # Get description for this image if available
                    description = None
                    if media_descriptions and i < len(media_descriptions):
                        description = media_descriptions[i]
                    
                    # Upload to Mastodon
                    try:
                        media = self.api.media_post(temp_path, description=description)
                        media_ids.append(media["id"])
                        logger.debug(f"Uploaded media {url} with ID {media['id']}")
                    except MastodonError as e:
                        error_msg = f"Failed to upload media {url}: {e}"
                        logger.error(error_msg)
                        if self.notifier:
                            self.notifier.notify_post_failure(
                                "Media Upload Failed",
                                self.account_name,
                                "Mastodon",
                                error_msg
                            )
            
            # Post status with media IDs
            result = self.api.status_post(
                status=content,
                visibility=visibility,
                sensitive=sensitive,
                spoiler_text=spoiler_text,
                media_ids=media_ids if media_ids else None
            )
            logger.info(f"Successfully posted status to Mastodon: {result['url']}")
            return result
            
        except MastodonError as e:
            error_msg = f"Failed to post status to Mastodon: {e}"
            logger.error(error_msg)
            if self.notifier:
                self.notifier.notify_post_failure(
                    content[:100] + "..." if len(content) > 100 else content,
                    self.account_name,
                    "Mastodon",
                    str(e)
                )
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
            ...     print(f"Authenticated as: @{account["username"]}")
        """
        if not self.enabled or not self.api:
            logger.warning("Cannot verify credentials: client not enabled")
            return None

        try:
            account = self.api.account_verify_credentials()
            logger.info(f"Verified credentials for @{account['username']}")
            return account
        except MastodonError as e:
            error_msg = f"Failed to verify credentials: {e}"
            logger.error(error_msg)
            if self.notifier:
                self.notifier.notify_post_failure(
                    "Credential Verification Failed",
                    self.account_name,
                    "Mastodon",
                    str(e)
                )
            return None

    def get_recent_posts(self, limit: int = 40) -> List[Dict[str, Any]]:
        """Get recent posts from the authenticated user's timeline.

        This method retrieves the user's own posts (statuses) from their timeline.
        Useful for discovering syndication mappings by searching for posts that
        link back to Ghost posts.

        Args:
            limit: Maximum number of posts to retrieve (default: 40, max: 40 per API call)

        Returns:
            List of status dictionaries, each containing:
                - id: Status ID
                - url: URL of the status
                - content: HTML content of the status
                - created_at: Creation timestamp

        Example:
            >>> posts = client.get_recent_posts(limit=20)
            >>> for post in posts:
            ...     print(f"Status {post['id']}: {post['url']}")
        """
        if not self.enabled or not self.api:
            logger.warning(f"Cannot get recent posts for Mastodon '{self.account_name}': client not enabled")
            return []

        try:
            # Get the authenticated user's account info
            account = self.api.account_verify_credentials()
            account_id = account['id']

            # Get the user's statuses (limit max is 40 for Mastodon API)
            statuses = self.api.account_statuses(
                id=account_id,
                limit=min(limit, 40),
                exclude_replies=False,
                exclude_reblogs=True  # Only get original posts, not reblogs
            )

            logger.debug(f"Retrieved {len(statuses)} recent posts from Mastodon '{self.account_name}'")
            return statuses

        except MastodonError as e:
            logger.error(f"Failed to get recent posts from Mastodon '{self.account_name}': {e}")
            return []
