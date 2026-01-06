"""
Mastodon Client for POSSE.

This module provides functionality to authenticate with Mastodon instances
and post content to Mastodon accounts from Ghost blog posts.

Mastodon Configuration:
    Configure via config.yml:
    - mastodon.enabled: Set to true to enable Mastodon posting
    - mastodon.instance_url: URL of the Mastodon instance (e.g., https://mastodon.social)
    - mastodon.client_id_file: Path to Docker secret for client ID
    - mastodon.client_secret_file: Path to Docker secret for client secret
    - mastodon.access_token_file: Path to Docker secret for access token

Usage:
    >>> from config import load_config
    >>> config = load_config()
    >>> client = MastodonClient.from_config(config)
    >>> if client.enabled:
    ...     result = client.post_status("Hello from POSSE!")
    ...     print(f"Posted: {result['url']}")

Authentication Flow:
    1. Register app with Mastodon instance using register_app()
       - Returns client_id and client_secret
    2. Generate authorization URL using get_authorization_url()
       - User visits URL and authorizes the app
    3. Exchange authorization code for access token using get_access_token()
       - Returns access_token for API calls
    4. Store credentials securely in Docker secrets

API Reference:
    Mastodon API: https://docs.joinmastodon.org/api/
    Mastodon.py: https://mastodonpy.readthedocs.io/

Security:
    - Credentials are loaded from Docker secrets
    - No credentials are logged or stored in code
    - Client credentials and access tokens should be kept secret
"""
import os
import logging
from typing import Optional, Dict, Any, Tuple
from mastodon import Mastodon, MastodonError

from config import read_secret_file


logger = logging.getLogger(__name__)


class MastodonClient:
    """Client for posting to Mastodon instances.
    
    This class encapsulates Mastodon API interactions using the Mastodon.py
    library and provides methods for authentication and posting.
    
    Attributes:
        instance_url: URL of the Mastodon instance (e.g., https://mastodon.social)
        client_id: OAuth client ID for the registered app
        client_secret: OAuth client secret for the registered app
        access_token: OAuth access token for authenticated API calls
        enabled: Whether Mastodon posting is enabled
        api: Mastodon API client instance (None if not enabled)
        
    Example:
        >>> client = MastodonClient(
        ...     instance_url="https://mastodon.social",
        ...     client_id="...",
        ...     client_secret="...",
        ...     access_token="..."
        ... )
        >>> if client.enabled:
        ...     client.post_status("Hello Mastodon!")
    """
    
    # Default app name for registration
    DEFAULT_APP_NAME = "POSSE"
    
    # Default scopes for OAuth
    DEFAULT_SCOPES = ['read', 'write:statuses']
    
    def __init__(
        self,
        instance_url: str,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        access_token: Optional[str] = None,
        config_enabled: bool = True
    ):
        """Initialize Mastodon client with credentials.
        
        Args:
            instance_url: URL of the Mastodon instance (e.g., https://mastodon.social)
            client_id: OAuth client ID (obtained from app registration)
            client_secret: OAuth client secret (obtained from app registration)
            access_token: OAuth access token (obtained from user authorization)
            config_enabled: Whether Mastodon is enabled in config.yml (default: True)
            
        Note:
            Mastodon posting will be disabled if:
            - config_enabled is False
            - instance_url is not provided
            - Any required credential is missing
        """
        self.instance_url = instance_url
        self.client_id = client_id
        self.client_secret = client_secret
        self.access_token = access_token
        self.api: Optional[Mastodon] = None
        
        # Determine if client is enabled
        self.enabled = bool(
            config_enabled and
            instance_url and  # Check for non-empty string
            client_id is not None and
            client_secret is not None and
            access_token is not None
        )
        
        if not config_enabled:
            logger.info("Mastodon posting disabled via config.yml")
        elif not self.enabled:
            logger.warning(
                "Mastodon posting disabled: missing instance URL or credentials"
            )
        else:
            try:
                # Initialize Mastodon API client
                self.api = Mastodon(
                    client_id=self.client_id,
                    client_secret=self.client_secret,
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
        
        # Read credentials from Docker secrets
        client_id_file = mastodon_config.get('client_id_file')
        client_secret_file = mastodon_config.get('client_secret_file')
        access_token_file = mastodon_config.get('access_token_file')
        
        client_id = read_secret_file(client_id_file) if client_id_file else None
        client_secret = read_secret_file(client_secret_file) if client_secret_file else None
        access_token = read_secret_file(access_token_file) if access_token_file else None
        
        return cls(
            instance_url=instance_url,
            client_id=client_id,
            client_secret=client_secret,
            access_token=access_token,
            config_enabled=enabled
        )
    
    @staticmethod
    def register_app(
        instance_url: str,
        app_name: str = DEFAULT_APP_NAME,
        scopes: list = None
    ) -> Tuple[str, str]:
        """Register a new application with a Mastodon instance.
        
        This method creates a new OAuth application on the Mastodon instance
        and returns the client credentials needed for authentication.
        
        Args:
            instance_url: URL of the Mastodon instance (e.g., https://mastodon.social)
            app_name: Name of the application (default: "POSSE")
            scopes: List of OAuth scopes (default: ['read', 'write:statuses'])
            
        Returns:
            Tuple of (client_id, client_secret)
            
        Raises:
            MastodonError: If app registration fails
            
        Example:
            >>> client_id, client_secret = MastodonClient.register_app(
            ...     "https://mastodon.social"
            ... )
            >>> # Store these credentials securely
        """
        if scopes is None:
            scopes = MastodonClient.DEFAULT_SCOPES
        
        try:
            client_id, client_secret = Mastodon.create_app(
                app_name,
                scopes=scopes,
                api_base_url=instance_url
            )
            logger.info(f"Successfully registered app '{app_name}' on {instance_url}")
            return client_id, client_secret
        except MastodonError as e:
            logger.error(f"Failed to register app on {instance_url}: {e}")
            raise
    
    def get_authorization_url(self, redirect_uri: str = 'urn:ietf:wg:oauth:2.0:oob') -> str:
        """Generate OAuth authorization URL for user authentication.
        
        This method generates the URL where users need to go to authorize
        the application to access their Mastodon account.
        
        Args:
            redirect_uri: OAuth redirect URI (default: 'urn:ietf:wg:oauth:2.0:oob' for manual code entry)
            
        Returns:
            Authorization URL string
            
        Raises:
            ValueError: If client is not properly initialized with client credentials
            
        Example:
            >>> client = MastodonClient(instance_url="...", client_id="...", client_secret="...")
            >>> auth_url = client.get_authorization_url()
            >>> print(f"Visit this URL to authorize: {auth_url}")
        """
        if not self.client_id or not self.client_secret:
            raise ValueError("Client ID and secret required to generate authorization URL")
        
        # Create a temporary Mastodon instance for authorization
        mastodon = Mastodon(
            client_id=self.client_id,
            client_secret=self.client_secret,
            api_base_url=self.instance_url
        )
        
        return mastodon.auth_request_url(
            scopes=self.DEFAULT_SCOPES,
            redirect_uris=redirect_uri
        )
    
    def get_access_token(
        self,
        authorization_code: str,
        redirect_uri: str = 'urn:ietf:wg:oauth:2.0:oob'
    ) -> str:
        """Exchange authorization code for access token.
        
        After the user authorizes the app and receives an authorization code,
        this method exchanges it for an access token that can be used for API calls.
        
        Args:
            authorization_code: Code received after user authorization
            redirect_uri: OAuth redirect URI (must match the one used in authorization URL)
            
        Returns:
            Access token string
            
        Raises:
            ValueError: If client is not properly initialized with client credentials
            MastodonError: If token exchange fails
            
        Example:
            >>> code = input("Enter authorization code: ")
            >>> token = client.get_access_token(code)
            >>> # Store this token securely
        """
        if not self.client_id or not self.client_secret:
            raise ValueError("Client ID and secret required to get access token")
        
        try:
            # Create a temporary Mastodon instance for token exchange
            mastodon = Mastodon(
                client_id=self.client_id,
                client_secret=self.client_secret,
                api_base_url=self.instance_url
            )
            
            access_token = mastodon.log_in(
                code=authorization_code,
                redirect_uri=redirect_uri,
                scopes=self.DEFAULT_SCOPES
            )
            
            logger.info("Successfully obtained access token")
            return access_token
        except MastodonError as e:
            logger.error(f"Failed to get access token: {e}")
            raise
    
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
