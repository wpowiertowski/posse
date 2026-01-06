"""
Mastodon Client for POSSE.

This module provides functionality to post content to Mastodon accounts 
from Ghost blog posts, including full OAuth authentication flow.

Mastodon Configuration:
    Configure via config.yml:
    - mastodon.enabled: Set to true to enable Mastodon posting
    - mastodon.instance_url: URL of the Mastodon instance (e.g., https://mastodon.social)
    - mastodon.access_token_file: Path to Docker secret for access token

Usage (Production with access token):
    >>> from config import load_config
    >>> config = load_config()
    >>> client = MastodonClient.from_config(config)
    >>> if client.enabled:
    ...     result = client.post("Hello from POSSE!")
    ...     print(f"Posted: {result['url']}")

OAuth Setup (One-time interactive):
    1. Register app:
        >>> MastodonClient.register_app(
        ...     app_name='POSSE',
        ...     instance_url='https://mastodon.social',
        ...     to_file='clientcred.secret'
        ... )
    
    2. Get authorization URL and login:
        >>> client = MastodonClient.create_for_oauth(
        ...     client_credential_file='clientcred.secret',
        ...     instance_url='https://mastodon.social'
        ... )
        >>> auth_url = client.get_auth_request_url()
        >>> print(f"Visit: {auth_url}")
        >>> # User authorizes and gets code
        >>> code = input("Enter code: ")
        >>> client.login_with_code(code, to_file='usercred.secret')
    
    3. Use the access token from usercred.secret in production

API Reference:
    Mastodon API: https://docs.joinmastodon.org/api/
    Mastodon.py: https://mastodonpy.readthedocs.io/

Security:
    - Client credentials and access tokens are loaded from Docker secrets in production
    - For OAuth setup, credentials are stored in files
    - Never commit credential files to version control
"""
import logging
from typing import Optional, Dict, Any, List
from mastodon import Mastodon, MastodonError

from social.base_client import SocialMediaClient


logger = logging.getLogger(__name__)


class MastodonClient(SocialMediaClient):
    """Client for posting to Mastodon instances with OAuth support.
    
    This class extends SocialMediaClient to provide Mastodon-specific
    functionality using the Mastodon.py library, including full OAuth flow.
    
    Attributes:
        instance_url: URL of the Mastodon instance (e.g., https://mastodon.social)
        access_token: Access token for authenticated API calls
        enabled: Whether Mastodon posting is enabled
        api: Mastodon API client instance (None if not enabled)
        
    Example:
        >>> # Production use with access token
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
    
    @staticmethod
    def register_app(
        app_name: str,
        instance_url: str,
        to_file: Optional[str] = None,
        scopes: Optional[List[str]] = None,
        redirect_uris: str = 'urn:ietf:wg:oauth:2.0:oob',
        website: Optional[str] = None
    ) -> tuple:
        """Register a new Mastodon application (Step 1 of OAuth).
        
        This creates a new OAuth application on the Mastodon instance and
        returns client credentials. This only needs to be done once per
        application per instance.
        
        Args:
            app_name: Name of your application
            instance_url: URL of the Mastodon instance (e.g., 'https://mastodon.social')
            to_file: Optional file path to save client credentials
            scopes: List of OAuth scopes (default: ['read', 'write'])
            redirect_uris: OAuth redirect URI (default: 'urn:ietf:wg:oauth:2.0:oob' for manual code entry)
            website: Optional website URL for your app
            
        Returns:
            Tuple of (client_id, client_secret)
            
        Raises:
            MastodonError: If app registration fails
            
        Example:
            >>> # Interactive Docker command:
            >>> # docker run -it --rm -v $(pwd)/secrets:/secrets \\
            >>> #   posse python3 -c "
            >>> # from mastodon_client import MastodonClient
            >>> # MastodonClient.register_app(
            >>> #     'POSSE',
            >>> #     'https://mastodon.social',
            >>> #     to_file='/secrets/clientcred.secret'
            >>> # )"
            >>>
            >>> client_id, client_secret = MastodonClient.register_app(
            ...     app_name='POSSE',
            ...     instance_url='https://mastodon.social',
            ...     to_file='clientcred.secret'
            ... )
        """
        if scopes is None:
            scopes = ['read', 'write']
        
        try:
            result = Mastodon.create_app(
                client_name=app_name,
                scopes=scopes,
                redirect_uris=redirect_uris,
                website=website,
                api_base_url=instance_url,
                to_file=to_file
            )
            
            if to_file:
                logger.info(f"Registered app '{app_name}' on {instance_url}, credentials saved to {to_file}")
            else:
                logger.info(f"Registered app '{app_name}' on {instance_url}")
            
            return result
        except MastodonError as e:
            logger.error(f"Failed to register app '{app_name}' on {instance_url}: {e}")
            raise
    
    @classmethod
    def create_for_oauth(
        cls,
        client_credential_file: str,
        instance_url: str
    ) -> 'MastodonClient':
        """Create a MastodonClient instance for OAuth flow (Step 2).
        
        This creates a client that can be used to get an authorization URL
        and exchange authorization codes for access tokens.
        
        Args:
            client_credential_file: Path to file containing client credentials
                                   (created by register_app)
            instance_url: URL of the Mastodon instance
            
        Returns:
            MastodonClient instance configured for OAuth
            
        Example:
            >>> # After running register_app
            >>> client = MastodonClient.create_for_oauth(
            ...     client_credential_file='clientcred.secret',
            ...     instance_url='https://mastodon.social'
            ... )
            >>> auth_url = client.get_auth_request_url()
        """
        # Create a special instance that bypasses normal initialization
        instance = cls.__new__(cls)
        instance.instance_url = instance_url
        instance.access_token = None
        instance.enabled = True  # Enable for OAuth operations
        instance.api = Mastodon(
            client_id=client_credential_file,
            api_base_url=instance_url
        )
        logger.info(f"Created OAuth client for {instance_url}")
        return instance
    
    def get_auth_request_url(
        self,
        scopes: Optional[List[str]] = None,
        redirect_uris: str = 'urn:ietf:wg:oauth:2.0:oob',
        force_login: bool = False
    ) -> str:
        """Get the OAuth authorization URL for user to visit (Step 2a).
        
        The user must visit this URL, authorize the application, and
        receive an authorization code to exchange for an access token.
        
        Args:
            scopes: List of OAuth scopes (default: ['read', 'write'])
            redirect_uris: OAuth redirect URI
            force_login: Force the user to re-login
            
        Returns:
            Authorization URL string
            
        Raises:
            ValueError: If client is not properly initialized
            
        Example:
            >>> # Interactive Docker command:
            >>> # docker run -it --rm -v $(pwd)/secrets:/secrets \\
            >>> #   posse python3 -c "
            >>> # from mastodon_client import MastodonClient
            >>> # client = MastodonClient.create_for_oauth(
            >>> #     '/secrets/clientcred.secret',
            >>> #     'https://mastodon.social'
            >>> # )
            >>> # print('Visit:', client.get_auth_request_url())
            >>> # "
            >>>
            >>> auth_url = client.get_auth_request_url()
            >>> print(f"Visit this URL to authorize: {auth_url}")
        """
        if not self.api:
            raise ValueError("Client not initialized for OAuth")
        
        if scopes is None:
            scopes = ['read', 'write']
        
        return self.api.auth_request_url(
            scopes=scopes,
            redirect_uris=redirect_uris,
            force_login=force_login
        )
    
    def login_with_code(
        self,
        code: str,
        to_file: Optional[str] = None,
        scopes: Optional[List[str]] = None,
        redirect_uri: str = 'urn:ietf:wg:oauth:2.0:oob'
    ) -> str:
        """Exchange authorization code for access token (Step 2b).
        
        After the user authorizes the app and receives a code, use this
        method to exchange it for an access token.
        
        Args:
            code: Authorization code from user authorization
            to_file: Optional file path to save access token
            scopes: List of OAuth scopes (default: ['read', 'write'])
            redirect_uri: OAuth redirect URI (must match auth request)
            
        Returns:
            Access token string
            
        Raises:
            MastodonError: If login fails
            
        Example:
            >>> # Interactive Docker command:
            >>> # docker run -it --rm -v $(pwd)/secrets:/secrets \\
            >>> #   posse python3 -c "
            >>> # from mastodon_client import MastodonClient
            >>> # client = MastodonClient.create_for_oauth(
            >>> #     '/secrets/clientcred.secret',
            >>> #     'https://mastodon.social'
            >>> # )
            >>> # print('Visit:', client.get_auth_request_url())
            >>> # code = input('Enter code: ')
            >>> # client.login_with_code(code, to_file='/secrets/usercred.secret')
            >>> # print('Access token saved!')
            >>> # "
            >>>
            >>> code = input("Enter authorization code: ")
            >>> access_token = client.login_with_code(
            ...     code=code,
            ...     to_file='usercred.secret'
            ... )
        """
        if not self.api:
            raise ValueError("Client not initialized for OAuth")
        
        if scopes is None:
            scopes = ['read', 'write']
        
        try:
            access_token = self.api.log_in(
                code=code,
                redirect_uri=redirect_uri,
                scopes=scopes,
                to_file=to_file
            )
            
            if to_file:
                logger.info(f"Access token saved to {to_file}")
            else:
                logger.info("Access token obtained successfully")
            
            # Update this instance with the access token
            self.access_token = access_token
            
            return access_token
        except MastodonError as e:
            logger.error(f"Failed to exchange authorization code: {e}")
            raise
    
    def post(
        self,
        content: str,
        visibility: str = 'public',
        sensitive: bool = False,
        spoiler_text: Optional[str] = None,
        **kwargs
    ) -> Optional[Dict[str, Any]]:
        """Post content to Mastodon (toot).
        
        Args:
            content: Text content of the status (max 500 characters for most instances)
            visibility: Post visibility ('public', 'unlisted', 'private', 'direct')
            sensitive: Whether to mark the post as sensitive content
            spoiler_text: Content warning text (if provided, post will be hidden behind CW)
            **kwargs: Additional Mastodon-specific options
            
        Returns:
            Dictionary containing the posted status information, or None if posting failed
            
        Example:
            >>> # Interactive Docker command for testing:
            >>> # docker run -it --rm -v $(pwd)/secrets:/secrets \\
            >>> #   -e MASTODON_ACCESS_TOKEN=$(cat secrets/usercred.secret) \\
            >>> #   posse python3 -c "
            >>> # from mastodon_client import MastodonClient
            >>> # import os
            >>> # client = MastodonClient(
            >>> #     instance_url='https://mastodon.social',
            >>> #     access_token=os.environ['MASTODON_ACCESS_TOKEN']
            >>> # )
            >>> # result = client.post('Hello from POSSE! 🚀')
            >>> # print('Posted:', result['url'])
            >>> # "
            >>>
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
    
    # Alias for backward compatibility and Mastodon terminology
    def toot(self, content: str, **kwargs) -> Optional[Dict[str, Any]]:
        """Alias for post() using Mastodon terminology.
        
        Args:
            content: Text content to post
            **kwargs: Additional options passed to post()
            
        Returns:
            Dictionary containing the posted status information, or None if failed
        """
        return self.post(content, **kwargs)
    
    # Maintain backward compatibility with old method name
    def post_status(
        self,
        status: str,
        visibility: str = 'public',
        sensitive: bool = False,
        spoiler_text: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Post a status to Mastodon (backward compatibility method).
        
        This method is maintained for backward compatibility and delegates
        to the post() method.
        
        Args:
            status: Text content of the status
            visibility: Post visibility ('public', 'unlisted', 'private', 'direct')
            sensitive: Whether to mark the post as sensitive content
            spoiler_text: Content warning text
            
        Returns:
            Dictionary containing the posted status information, or None if posting failed
        """
        return self.post(
            content=status,
            visibility=visibility,
            sensitive=sensitive,
            spoiler_text=spoiler_text
        )
    
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
