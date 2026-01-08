"""
Bluesky Client for POSSE.

This module provides functionality to post content to Bluesky accounts
from Ghost blog posts using the ATProto library.

Bluesky Configuration:
    Configure via config.yml:
    - bluesky.accounts: List of Bluesky accounts
    - Each account has: name, instance_url, access_token_file
    - access_token_file: Path to Docker secret containing session string

Usage:
    >>> from config import load_config
    >>> config = load_config()
    >>> clients = BlueskyClient.from_config(config)
    >>> for client in clients:
    ...     if client.enabled:
    ...         result = client.post("Hello from POSSE!")
    ...         print(f"Posted: {result['uri']}")

Authentication:
    Bluesky uses session strings for authentication. To obtain a session string:
    1. Login with username and password once:
       >>> from atproto import Client
       >>> client = Client()
       >>> client.login('your.handle', 'your_password')
       >>> session_string = client.export_session_string()
    2. Store the session_string in a Docker secret
    3. Use the session_string for subsequent authentications

API Reference:
    ATProto: https://github.com/MarshalX/atproto
    Bluesky API: https://docs.bsky.app/

Security:
    - Session string is loaded from Docker secrets
    - No credentials are logged or stored in code
    - Session string should be kept secret
"""
import logging
from typing import Optional, Dict, Any
from atproto import Client
from atproto.exceptions import AtProtocolError

from social.base_client import SocialMediaClient


logger = logging.getLogger(__name__)


class BlueskyClient(SocialMediaClient):
    """Client for posting to Bluesky.
    
    This class extends SocialMediaClient to provide Bluesky-specific
    functionality using the ATProto library.
    
    Attributes:
        instance_url: URL of the Bluesky instance (e.g., https://bsky.social)
        access_token: Session string for authenticated API calls
        enabled: Whether Bluesky posting is enabled
        api: ATProto Client instance (None if not enabled)
        
    Example:
        >>> client = BlueskyClient(
        ...     instance_url="https://bsky.social",
        ...     access_token="session_string_here"
        ... )
        >>> if client.enabled:
        ...     client.post("Hello Bluesky!")
    """
    
    def _initialize_api(self) -> None:
        """Initialize the Bluesky ATProto client.
        
        Sets up the ATProto client with the session string.
        
        Note:
            The base class uses access_token as a generic credential field.
            For Bluesky, we store the session string in this field, which
            provides equivalent functionality to access tokens but uses
            ATProto's session-based authentication instead.
        
        Raises:
            Exception: If API initialization fails
        """
        self.api = Client()
        # Use the access_token field (which contains the session_string for Bluesky)
        self.api.login(session_string=self.access_token)
    
    @classmethod
    def from_config(cls, config: Dict[str, Any]) -> list['BlueskyClient']:
        """Create BlueskyClient instances from configuration dictionary.
        
        This factory method reads configuration from config.yml and loads
        session strings from Docker secrets. Supports multiple accounts.
        
        Args:
            config: Configuration dictionary from load_config()
            
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
        return super(BlueskyClient, cls).from_config(config, 'bluesky')
    
    def post(
        self,
        content: str,
        **kwargs
    ) -> Optional[Dict[str, Any]]:
        """Post content to Bluesky.
        
        Args:
            content: Text content to post (max ~300 characters for most Bluesky posts)
            **kwargs: Bluesky-specific options (reply_to, embed, langs, facets, etc.)
            
        Returns:
            Dictionary with post information including 'uri' and 'cid', or None if posting failed
            
        Example:
            >>> result = client.post("Hello from POSSE!")
            >>> if result:
            ...     print(f"Posted with URI: {result['uri']}")
        """
        if not self.enabled or not self.api:
            logger.warning("Cannot post to Bluesky: client not enabled")
            return None
        
        try:
            # Use send_post method from atproto Client
            result = self.api.send_post(text=content)
            logger.info(f"Successfully posted to Bluesky '{self.account_name}': {result.uri}")
            # Return a dictionary with the post information
            return {
                'uri': result.uri,
                'cid': result.cid
            }
        except AtProtocolError as e:
            logger.error(f"Failed to post to Bluesky '{self.account_name}': {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error posting to Bluesky '{self.account_name}': {e}")
            return None
    
    def verify_credentials(self) -> Optional[Dict[str, Any]]:
        """Verify Bluesky credentials and get account information.
        
        This method tests the connection and credentials by fetching the
        authenticated user's profile information.
        
        Returns:
            Dictionary containing account information with 'handle' and 'did', 
            or None if verification failed
            
        Example:
            >>> account = client.verify_credentials()
            >>> if account:
            ...     print(f"Authenticated as: @{account['handle']}")
        """
        if not self.enabled or not self.api:
            logger.warning("Cannot verify credentials: client not enabled")
            return None
        
        try:
            # Get the authenticated user's DID (Decentralized Identifier)
            if not self.api.me or not self.api.me.did:
                logger.error("No authenticated session found")
                return None
            
            # Get profile information for the authenticated user
            profile = self.api.get_profile(self.api.me.did)
            logger.info(f"Verified credentials for @{profile.handle}")
            
            return {
                'handle': profile.handle,
                'did': profile.did,
                'display_name': profile.display_name if hasattr(profile, 'display_name') else None
            }
        except AtProtocolError as e:
            logger.error(f"Failed to verify credentials: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error verifying credentials: {e}")
            return None
