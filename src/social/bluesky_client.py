"""
Bluesky Client for POSSE.

This module provides functionality to post content to Bluesky accounts 
from Ghost blog posts using the ATProto library.

Bluesky Configuration:
    Configure via config.yml:
    - bluesky.accounts: List of Bluesky accounts to post to
    - Each account needs:
        - name: Account identifier (for logging)
        - instance_url: Bluesky instance URL (e.g., https://bsky.social)
        - handle: Bluesky handle (e.g., user.bsky.social)
        - app_password_file: Path to Docker secret for app password

Usage:
    >>> from config import load_config
    >>> config = load_config()
    >>> clients = BlueskyClient.from_config(config)
    >>> for client in clients:
    ...     if client.enabled:
    ...         result = client.post("Hello from POSSE!")
    ...         print(f"Posted: {result["uri"]}")

Authentication:
    You need an app password from Bluesky. You can obtain one by:
    1. Going to Bluesky Settings
    2. Navigate to App Passwords
    3. Create a new app password
    4. Use the generated password (not your account password)

API Reference:
    ATProto Python SDK: https://atproto.blue/
    Bluesky API: https://docs.bsky.app/

Security:
    - App password is loaded from Docker secrets
    - No credentials are logged or stored in code
    - App password should be kept secret
"""
import logging
from typing import Optional, Dict, Any, List, TYPE_CHECKING

from atproto import Client, client_utils

from social.base_client import SocialMediaClient

if TYPE_CHECKING:
    from notifications.pushover import PushoverNotifier

logger = logging.getLogger(__name__)


class BlueskyClient(SocialMediaClient):
    """Client for posting to Bluesky.
    
    This class extends SocialMediaClient to provide Bluesky-specific
    functionality using the ATProto library.
    
    Attributes:
        instance_url: URL of the Bluesky instance (e.g., https://bsky.social)
        handle: Bluesky handle (e.g., user.bsky.social)
        app_password: App password for authenticated API calls
        enabled: Whether Bluesky posting is enabled
        api: ATProto Client instance (None if not enabled)
    
    Example:
        >>> client = BlueskyClient(
        ...     instance_url="https://bsky.social",
        ...     handle="user.bsky.social",
        ...     app_password="your-app-password"
        ... )
        >>> if client.enabled:
        ...     client.post("Hello Bluesky!")
    """
    
    def __init__(
        self,
        instance_url: str,
        handle: Optional[str] = None,
        app_password: Optional[str] = None,
        access_token: Optional[str] = None,  # For compatibility with base class
        config_enabled: bool = True,
        account_name: Optional[str] = None,
        notifier: Optional["PushoverNotifier"] = None,
        tags: Optional[List[str]] = None
    ):
        """Initialize Bluesky client with credentials.
        
        Args:
            instance_url: URL of the Bluesky instance (e.g., https://bsky.social)
            handle: Bluesky handle (e.g., user.bsky.social)
            app_password: App password for API authentication
            access_token: Alias for app_password (for base class compatibility)
            config_enabled: Whether posting is enabled in config.yml (default: True)
            account_name: Optional name for this account (for logging)
            notifier: PushoverNotifier instance for error notifications
            tags: Optional list of tags to filter posts (empty or None means all posts)
        """
        # For Bluesky, app_password is the access_token equivalent
        if app_password is None and access_token is not None:
            app_password = access_token
        
        self.handle = handle
        self.app_password = app_password
        self.notifier = notifier
        
        # Call parent init with app_password as access_token
        super().__init__(
            instance_url=instance_url,
            access_token=app_password,
            config_enabled=config_enabled,
            account_name=account_name,
            tags=tags
        )
    
    def _initialize_api(self) -> None:
        """Initialize the Bluesky ATProto client.
        
        Sets up the ATProto client and authenticates with handle and app password.
        
        Raises:
            Exception: If API initialization fails
        """
        if not self.handle or not self.app_password:
            raise ValueError("Bluesky handle and app_password are required")
        
        self.api = Client(base_url=self.instance_url)
        self.api.login(login=self.handle, password=self.app_password)
    
    @classmethod
    def from_config(cls, config: Dict[str, Any], notifier: Optional["PushoverNotifier"] = None) -> list["BlueskyClient"]:
        """Create BlueskyClient instances from configuration dictionary.
        
        This factory method reads configuration from config.yml and loads
        credentials from Docker secrets. Supports multiple accounts.
        
        Configuration Format:
            bluesky:
              accounts:
                - name: "personal"
                  instance_url: "https://bsky.social"
                  handle: "user.bsky.social"
                  app_password_file: "/run/secrets/bluesky_personal_app_password"
        
        Note:
            The configuration supports both `app_password_file` (recommended) and
            `access_token_file` (for backward compatibility) field names. Use
            `app_password_file` for Bluesky configurations as it better reflects
            that Bluesky uses app passwords rather than access tokens.
        
        Args:
            config: Configuration dictionary from load_config()
            notifier: PushoverNotifier instance for error notifications
            
        Returns:
            List of BlueskyClient instances
            
        Example:
            >>> from config import load_config
            >>> config = load_config()
            >>> clients = BlueskyClient.from_config(config)
            >>> for client in clients:
            ...     if client.enabled:
            ...         client.post("Hello!")
        """
        from config import read_secret_file
        
        bluesky_config = config.get("bluesky", {})
        accounts_config = bluesky_config.get("accounts", [])
        
        clients = []
        for account_config in accounts_config:
            account_name = account_config.get("name", "unnamed")
            instance_url = account_config.get("instance_url", "")
            handle = account_config.get("handle", "")
            app_password_file = account_config.get("app_password_file") or account_config.get("access_token_file")
            app_password = read_secret_file(app_password_file) if app_password_file else None
            tags = account_config.get("tags", [])
            
            # Account is enabled if it has required fields
            enabled = bool(instance_url and handle and app_password)
            
            client = cls(
                instance_url=instance_url,
                handle=handle,
                app_password=app_password,
                config_enabled=enabled,
                account_name=account_name,
                notifier=notifier,
                tags=tags
            )
            clients.append(client)
        
        return clients
    
    def post(
        self,
        content: str,
        media_urls: Optional[List[str]] = None,
        media_descriptions: Optional[List[str]] = None,
        **kwargs
    ) -> Optional[Dict[str, Any]]:
        """Post content to Bluesky.
        
        Args:
            content: Text content to post (max 300 characters)
            media_urls: Optional list of image URLs to attach to the post
            media_descriptions: Optional list of alt text descriptions for images.
                               If provided, should ideally match media_urls length.
                               If shorter, remaining images will have empty alt text.
                               If longer, extra descriptions are ignored.
            **kwargs: Bluesky-specific options (reply_to, etc.)
            
        Returns:
            Dictionary with post info including URI and CID, or None if posting failed
            
        Note:
            Images are downloaded and cached. Call _remove_images() separately to clean up.
            
        Example:
            >>> result = client.post("Hello from POSSE!")
            >>> if result:
            ...     print(f"Posted: {result["uri"]}")
            
            >>> # Post with an image
            >>> result = client.post(
            ...     "Check out this photo!",
            ...     media_urls=["https://example.com/image.jpg"],
            ...     media_descriptions=["A beautiful sunset"]
            ... )
        """
        if not self.enabled or not self.api:
            logger.warning(f"Cannot post to Bluesky '{self.account_name}': client not enabled")
            return None
        
        try:
            # Create text builder for rich text support
            text_builder = client_utils.TextBuilder()
            text_builder.text(content)
            
            # Prepare embed for images if provided
            embed = None
            if media_urls:
                images = []
                for i, url in enumerate(media_urls):
                    # Download image to cached file
                    temp_path = self._download_image(url)
                    if not temp_path:
                        error_msg = f"Failed to download image: {url}"
                        logger.warning(f"Skipping media upload for {url} due to download failure")
                        if self.notifier:
                            self.notifier.notify_post_failure(
                                "Media Download Failed",
                                self.account_name,
                                "Bluesky",
                                error_msg
                            )
                        continue
                    
                    # Get description for this image if available
                    description = ""
                    if media_descriptions and i < len(media_descriptions):
                        description = media_descriptions[i]
                    
                    # Upload to Bluesky
                    try:
                        with open(temp_path, 'rb') as f:
                            upload_result = self.api.upload_blob(f.read())
                        
                        # Add image with blob reference and alt text
                        images.append({
                            'blob': upload_result.blob,
                            'alt': description
                        })
                        logger.debug(f"Uploaded media {url} to Bluesky")
                    except Exception as e:
                        error_msg = f"Failed to upload media {url}: {e}"
                        logger.error(error_msg)
                        if self.notifier:
                            self.notifier.notify_post_failure(
                                "Media Upload Failed",
                                self.account_name,
                                "Bluesky",
                                error_msg
                            )
                
                # Create embed with images if any were successfully uploaded
                if images:
                    embed = self.api.get_embed_images(images)
            
            # Send post using the ATProto client
            result = self.api.send_post(text_builder, embed=embed)
            
            logger.info(f"Successfully posted to Bluesky '{self.account_name}': {result.uri}")
            return {
                "uri": result.uri,
                "cid": result.cid
            }
        except Exception as e:
            error_msg = f"Failed to post to Bluesky '{self.account_name}': {e}"
            logger.error(error_msg)
            if self.notifier:
                self.notifier.notify_post_failure(
                    content[:100] + "..." if len(content) > 100 else content,
                    self.account_name,
                    "Bluesky",
                    str(e)
                )
            return None
    
    def verify_credentials(self) -> Optional[Dict[str, Any]]:
        """Verify Bluesky credentials.
        
        Returns:
            Dictionary with account info including handle and DID, or None if verification failed
            
        Example:
            >>> account = client.verify_credentials()
            >>> if account:
            ...     print(f"Authenticated as: @{account["handle"]}")
        """
        if not self.enabled or not self.api:
            logger.warning(f"Cannot verify credentials for Bluesky '{self.account_name}': client not enabled")
            return None
        
        try:
            # Get the authenticated user's DID
            if not self.api.me:
                error_msg = "No session"
                logger.error(f"Failed to verify credentials for Bluesky '{self.account_name}': {error_msg}")
                if self.notifier:
                    self.notifier.notify_post_failure(
                        "Credential Verification Failed",
                        self.account_name,
                        "Bluesky",
                        error_msg
                    )
                return None
            
            # Get profile information
            profile = self.api.get_profile(actor=self.api.me.did)
            
            logger.info(f"Verified credentials for Bluesky '{self.account_name}': @{profile.handle}")
            return {
                "handle": profile.handle,
                "did": profile.did,
                "display_name": profile.display_name
            }
        except Exception as e:
            logger.error(f"Failed to verify credentials for Bluesky '{self.account_name}': {e}")
            return None
