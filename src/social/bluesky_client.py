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

Rich Text Formatting:
    The client automatically detects and formats:
    - URLs: Converted to clickable links
    - Hashtags: Made searchable (e.g., #python, #atproto)
    
    Example:
    >>> client.post("Check out https://atproto.blue #python #sdk")
    # Results in a post with a clickable link and searchable hashtags

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
import io
import logging
import re
from typing import Optional, Dict, Any, List, TYPE_CHECKING

from PIL import Image
from atproto import Client, client_utils, models

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
    
    # Bluesky character limit (300 characters)
    MAX_POST_LENGTH = 300

    # Bluesky blob size limit (976.56KB = 1,000,000 bytes)
    MAX_BLOB_SIZE = 1_000_000

    # Maximum pixel dimension for image compression (longest side)
    IMAGE_MAX_DIMENSION = 2500
    
    def __init__(
        self,
        instance_url: str,
        handle: Optional[str] = None,
        app_password: Optional[str] = None,
        access_token: Optional[str] = None,  # For compatibility with base class
        config_enabled: bool = True,
        account_name: Optional[str] = None,
        notifier: Optional["PushoverNotifier"] = None,
        tags: Optional[List[str]] = None,
        max_post_length: Optional[int] = None,
        split_multi_image_posts: bool = False
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
            max_post_length: Optional maximum post length for this account (uses platform default if None)
            split_multi_image_posts: Whether to split posts with multiple images into separate posts (default: False)
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
            tags=tags,
            max_post_length=max_post_length,
            split_multi_image_posts=split_multi_image_posts
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
    
    def _build_rich_text(self, content: str) -> client_utils.TextBuilder:
        """Build rich text with proper formatting for links and hashtags.
        
        This method parses the content to detect URLs and hashtags, then uses
        TextBuilder to properly format them as rich text facets. This ensures
        that links are clickable and hashtags are searchable in Bluesky.
        
        Args:
            content: Plain text content to parse and format
            
        Returns:
            TextBuilder instance with properly formatted rich text
            
        Example:
            >>> content = "Check out https://example.com #python #atproto"
            >>> text_builder = self._build_rich_text(content)
            >>> # text_builder now has clickable links and searchable hashtags
        """
        text_builder = client_utils.TextBuilder()
        
        # Regular expressions for detecting URLs and hashtags
        # URL pattern matches http(s):// URLs, excluding common trailing punctuation
        # This prevents URLs like "Visit https://example.com." from including the period
        url_pattern = r'https?://[^\s]+'
        # Hashtag pattern matches # followed by word characters (letters, numbers, underscores)
        # This follows standard social media conventions: #python, #python3, #my_tag
        hashtag_pattern = r'#\w+'
        
        # Find all URLs and hashtags with their positions
        urls = [(m.group(), m.start(), m.end()) for m in re.finditer(url_pattern, content)]
        hashtags = [(m.group(), m.start(), m.end()) for m in re.finditer(hashtag_pattern, content)]
        
        # Post-process URLs to remove common trailing punctuation
        processed_urls = []
        for url, start, end in urls:
            # Remove trailing punctuation that's likely not part of the URL
            while url and url[-1] in '.,;!?)':
                url = url[:-1]
                end -= 1
            if url:  # Only add if URL is not empty after stripping
                processed_urls.append((url, start, end))
        
        # Combine and sort all matches by position
        all_matches = []
        for url, start, end in processed_urls:
            all_matches.append(('url', url, start, end))
        for hashtag, start, end in hashtags:
            all_matches.append(('hashtag', hashtag, start, end))
        all_matches.sort(key=lambda x: x[2])  # Sort by start position
        
        # Build the rich text by processing content in order
        last_pos = 0
        for match_type, match_text, start, end in all_matches:
            # Add any plain text before this match
            if start > last_pos:
                text_builder.text(content[last_pos:start])
            
            # Add the formatted match
            if match_type == 'url':
                # For URLs, the display text is the URL itself
                text_builder.link(match_text, match_text)
            elif match_type == 'hashtag':
                # For hashtags, remove the # for the tag value
                tag_value = match_text[1:]  # Remove leading #
                text_builder.tag(match_text, tag_value)
            
            last_pos = end
        
        # Add any remaining text after the last match
        if last_pos < len(content):
            text_builder.text(content[last_pos:])
        
        return text_builder
    
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
            max_post_length = account_config.get("max_post_length")
            split_multi_image_posts = account_config.get("split_multi_image_posts", False)

            # Account is enabled if it has required fields
            enabled = bool(instance_url and handle and app_password)

            client = cls(
                instance_url=instance_url,
                handle=handle,
                app_password=app_password,
                config_enabled=enabled,
                account_name=account_name,
                notifier=notifier,
                tags=tags,
                max_post_length=max_post_length,
                split_multi_image_posts=split_multi_image_posts
            )
            clients.append(client)
        
        return clients
    
    @staticmethod
    def _compress_image(image_data: bytes, max_size: int = 1_000_000, max_dimension: int = 2500) -> bytes:
        """Compress an image to fit within Bluesky's blob size limit.

        First resizes the image so the longest dimension is at most max_dimension
        pixels, then reduces JPEG quality 1% at a time until the file is under
        max_size bytes.

        Args:
            image_data: Raw image bytes
            max_size: Maximum file size in bytes (default: 1,000,000 = 976.56KB)
            max_dimension: Maximum pixel dimension for longest side (default: 2500)

        Returns:
            Image bytes that fit within max_size, or the original data if
            compression is not needed or fails
        """
        if len(image_data) <= max_size:
            return image_data

        try:
            img = Image.open(io.BytesIO(image_data))
        except Exception as e:
            logger.warning(f"Could not open image for compression: {e}")
            return image_data

        # Convert to RGB if necessary (JPEG doesn't support alpha)
        if img.mode in ('RGBA', 'P', 'LA', 'PA'):
            img = img.convert('RGB')
        elif img.mode != 'RGB':
            img = img.convert('RGB')

        # Resize if longest dimension exceeds max_dimension
        width, height = img.size
        if max(width, height) > max_dimension:
            if width >= height:
                new_width = max_dimension
                new_height = int(height * (max_dimension / width))
            else:
                new_height = max_dimension
                new_width = int(width * (max_dimension / height))
            img = img.resize((new_width, new_height), Image.LANCZOS)
            logger.debug(
                f"Resized image from {width}x{height} to {new_width}x{new_height}"
            )

        # Try saving as JPEG, reducing quality until under the limit
        quality = 100
        compressed_data = image_data
        while quality > 0:
            buffer = io.BytesIO()
            img.save(buffer, format='JPEG', quality=quality)
            compressed_data = buffer.getvalue()
            if len(compressed_data) <= max_size:
                logger.info(
                    f"Compressed image from {len(image_data)} to "
                    f"{len(compressed_data)} bytes (quality={quality})"
                )
                return compressed_data
            quality -= 1

        logger.warning(
            f"Could not compress image below {max_size} bytes "
            f"(final size: {len(compressed_data)} bytes)"
        )
        return compressed_data

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

        # Re-authenticate before each post to avoid ExpiredToken errors
        # Bluesky tokens can expire between posts, especially for queued syndication
        if not self.re_authenticate():
            logger.error(f"Failed to re-authenticate before posting to Bluesky '{self.account_name}'")
            return None

        try:
            # Build rich text with proper formatting for links and hashtags
            text_builder = self._build_rich_text(content)
            
            # Prepare embed for images if provided
            embed = None
            if media_urls:
                # Bluesky has a limit of 4 images per post
                MAX_IMAGES = 4
                if len(media_urls) > MAX_IMAGES:
                    logger.warning(
                        f"Bluesky '{self.account_name}': Post has {len(media_urls)} images, "
                        f"limiting to {MAX_IMAGES} (Bluesky maximum)"
                    )
                    media_urls = media_urls[:MAX_IMAGES]
                    if media_descriptions:
                        media_descriptions = media_descriptions[:MAX_IMAGES]
                
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
                        description = media_descriptions[i] or ""
                    
                    # Upload to Bluesky (compress if needed)
                    try:
                        with open(temp_path, 'rb') as f:
                            image_data = f.read()
                        image_data = self._compress_image(
                            image_data,
                            max_size=self.MAX_BLOB_SIZE,
                            max_dimension=self.IMAGE_MAX_DIMENSION
                        )
                        upload_result = self.api.upload_blob(image_data)
                        
                        # Create Image object with blob reference and alt text
                        images.append(
                            models.AppBskyEmbedImages.Image(
                                alt=description,
                                image=upload_result.blob
                            )
                        )
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
                    embed = models.AppBskyEmbedImages.Main(images=images)
            
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
    
    def re_authenticate(self) -> bool:
        """Re-authenticate the client by logging in again.

        This method should be called when the token has expired or been revoked.
        It will create a new API client and attempt to login with the stored credentials.

        Returns:
            True if re-authentication succeeded, False otherwise

        Example:
            >>> if "ExpiredToken" in error_message:
            ...     if client.re_authenticate():
            ...         # Retry the operation
            ...         client.post(content)
        """
        if not self.handle or not self.app_password:
            logger.error(f"Cannot re-authenticate Bluesky '{self.account_name}': missing credentials")
            return False

        try:
            logger.info(f"Re-authenticating Bluesky '{self.account_name}'")
            # Create a new client and login
            self.api = Client(base_url=self.instance_url)
            self.api.login(login=self.handle, password=self.app_password)
            logger.info(f"Successfully re-authenticated Bluesky '{self.account_name}'")
            return True
        except Exception as e:
            logger.error(f"Failed to re-authenticate Bluesky '{self.account_name}': {e}")
            if self.notifier:
                self.notifier.notify_post_failure(
                    "Re-authentication Failed",
                    self.account_name,
                    "Bluesky",
                    str(e)
                )
            return False

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

    def get_recent_posts(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent posts from the authenticated user's feed.

        This method retrieves the user's own posts from their author feed.
        Useful for discovering syndication mappings by searching for posts that
        link back to Ghost posts.

        Args:
            limit: Maximum number of posts to retrieve (default: 50, max: 100)

        Returns:
            List of post dictionaries, each containing:
                - uri: Post URI (AT Protocol URI)
                - cid: Content identifier
                - text: Plain text content
                - created_at: Creation timestamp
                - url: Web URL to the post

        Example:
            >>> posts = client.get_recent_posts(limit=30)
            >>> for post in posts:
            ...     print(f"Post {post['uri']}: {post.get('url', '')}")
        """
        if not self.enabled or not self.api:
            logger.warning(f"Cannot get recent posts for Bluesky '{self.account_name}': client not enabled")
            return []

        try:
            # Get the authenticated user's DID
            if not self.api.me:
                logger.error(f"No session for Bluesky '{self.account_name}'")
                return []

            # Get the user's author feed (their posts)
            feed_response = self.api.app.bsky.feed.get_author_feed({
                "actor": self.api.me.did,
                "limit": min(limit, 100),  # API max is 100
                "filter": "posts_no_replies"  # Only get original posts, not replies
            })

            posts = []
            for feed_item in feed_response.feed:
                if hasattr(feed_item, 'post'):
                    post = feed_item.post
                    author = post.author

                    # Extract post URI parts to build web URL
                    # URI format: at://did:plc:xxx/app.bsky.feed.post/yyy
                    uri_parts = post.uri.split('/')
                    if len(uri_parts) >= 2:
                        post_id = uri_parts[-1]
                        post_url = f"https://bsky.app/profile/{author.handle}/post/{post_id}"
                    else:
                        post_url = ""

                    posts.append({
                        "uri": post.uri,
                        "cid": post.cid,
                        "text": post.record.text if hasattr(post.record, 'text') else "",
                        "created_at": post.record.created_at if hasattr(post.record, 'created_at') else "",
                        "url": post_url,
                        "author_handle": author.handle
                    })

            logger.debug(f"Retrieved {len(posts)} recent posts from Bluesky '{self.account_name}'")
            return posts

        except Exception as e:
            logger.error(f"Failed to get recent posts from Bluesky '{self.account_name}': {e}")
            return []
