"""
Ghost Content API Client.

This module provides a client for interacting with the Ghost Content API
to retrieve blog post information for syndication interaction sync.
"""
import logging
import requests
from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)


class GhostContentAPIClient:
    """
    Client for Ghost Content API to retrieve blog post information.

    The Ghost Content API provides read-only access to published content.
    This client is used to retrieve recent posts for interaction syncing.

    Attributes:
        api_url: Base URL of the Ghost API (e.g., https://blog.example.com)
        api_key: Ghost Content API key
        api_version: Ghost API version (default: v5.0)
    """

    def __init__(
        self,
        api_url: str,
        api_key: str,
        api_version: str = "v5.0",
        timeout: int = 30
    ):
        """
        Initialize the Ghost Content API client.

        Args:
            api_url: Base URL of the Ghost blog (e.g., https://blog.example.com)
            api_key: Ghost Content API key
            api_version: Ghost API version (default: v5.0)
            timeout: Request timeout in seconds
        """
        self.api_url = api_url.rstrip('/')
        self.api_key = api_key
        self.api_version = api_version
        self.timeout = timeout
        self.enabled = bool(api_url and api_key)

        if self.enabled:
            logger.info(f"GhostContentAPIClient initialized for {self.api_url}")
        else:
            logger.warning("GhostContentAPIClient disabled - missing api_url or api_key")

    @classmethod
    def from_config(cls, config: Dict[str, Any]) -> "GhostContentAPIClient":
        """
        Create a GhostContentAPIClient from configuration dictionary.

        Args:
            config: Configuration dictionary with ghost.content_api settings

        Returns:
            Configured GhostContentAPIClient instance
        """
        ghost_config = config.get("ghost", {})
        content_api_config = ghost_config.get("content_api", {})

        api_url = content_api_config.get("url", "")
        api_key = content_api_config.get("key", "")

        # Support reading API key from file (for Docker secrets)
        api_key_file = content_api_config.get("key_file")
        if api_key_file:
            try:
                with open(api_key_file, 'r') as f:
                    api_key = f.read().strip()
            except Exception as e:
                logger.error(f"Failed to read Ghost API key from {api_key_file}: {e}")

        return cls(
            api_url=api_url,
            api_key=api_key,
            api_version=content_api_config.get("version", "v5.0"),
            timeout=content_api_config.get("timeout", 30)
        )

    def _build_url(self, endpoint: str) -> str:
        """Build full API URL for an endpoint."""
        return f"{self.api_url}/ghost/api/content/{endpoint}"

    def _make_request(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """
        Make a request to the Ghost Content API.

        Args:
            endpoint: API endpoint (e.g., "posts")
            params: Optional query parameters

        Returns:
            JSON response dictionary or None if request failed
        """
        if not self.enabled:
            logger.warning("Ghost Content API client is not enabled")
            return None

        url = self._build_url(endpoint)
        request_params = params or {}
        request_params["key"] = self.api_key

        try:
            response = requests.get(url, params=request_params, timeout=self.timeout)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.Timeout:
            logger.error(f"Timeout requesting Ghost API: {url}")
            return None
        except requests.exceptions.HTTPError as e:
            logger.error(f"HTTP error from Ghost API: {e}")
            return None
        except requests.exceptions.RequestException as e:
            logger.error(f"Request error from Ghost API: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error from Ghost API: {e}")
            return None

    def get_posts(
        self,
        limit: int = 15,
        page: int = 1,
        fields: Optional[List[str]] = None,
        include: Optional[List[str]] = None,
        filter_str: Optional[str] = None,
        order: str = "published_at desc"
    ) -> List[Dict[str, Any]]:
        """
        Retrieve posts from the Ghost Content API.

        Args:
            limit: Maximum number of posts to retrieve (max 15 per page)
            page: Page number for pagination
            fields: List of fields to include in response
            include: List of relations to include (e.g., ["tags", "authors"])
            filter_str: NQL filter string (e.g., "tag:syndicate")
            order: Order string (e.g., "published_at desc")

        Returns:
            List of post dictionaries

        Example:
            >>> client = GhostContentAPIClient(url, key)
            >>> posts = client.get_posts(limit=10, include=["tags"])
        """
        params = {
            "limit": min(limit, 15),  # Ghost API max is 15 per page
            "page": page,
            "order": order
        }

        if fields:
            params["fields"] = ",".join(fields)
        if include:
            params["include"] = ",".join(include)
        if filter_str:
            params["filter"] = filter_str

        response = self._make_request("posts", params)
        if response and "posts" in response:
            return response["posts"]
        return []

    def get_post_by_id(self, post_id: str, include: Optional[List[str]] = None) -> Optional[Dict[str, Any]]:
        """
        Retrieve a specific post by ID.

        Args:
            post_id: Ghost post ID
            include: List of relations to include

        Returns:
            Post dictionary or None if not found
        """
        params = {}
        if include:
            params["include"] = ",".join(include)

        response = self._make_request(f"posts/{post_id}", params)
        if response and "posts" in response and len(response["posts"]) > 0:
            return response["posts"][0]
        return None

    def get_post_by_slug(self, slug: str, include: Optional[List[str]] = None) -> Optional[Dict[str, Any]]:
        """
        Retrieve a specific post by slug.

        Args:
            slug: Post slug
            include: List of relations to include

        Returns:
            Post dictionary or None if not found
        """
        params = {}
        if include:
            params["include"] = ",".join(include)

        response = self._make_request(f"posts/slug/{slug}", params)
        if response and "posts" in response and len(response["posts"]) > 0:
            return response["posts"][0]
        return None

    def get_recent_posts(
        self,
        max_age_days: int = 30,
        max_posts: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Retrieve recent posts within a maximum age.

        Fetches posts published within the specified number of days,
        up to the maximum number of posts specified.

        Args:
            max_age_days: Maximum age of posts in days
            max_posts: Maximum number of posts to retrieve

        Returns:
            List of recent post dictionaries with id, url, slug, title, published_at

        Example:
            >>> client = GhostContentAPIClient(url, key)
            >>> recent_posts = client.get_recent_posts(max_age_days=7)
        """
        if not self.enabled:
            logger.warning("Ghost Content API client is not enabled")
            return []

        # Calculate cutoff date
        cutoff_date = datetime.now(ZoneInfo("UTC")) - timedelta(days=max_age_days)
        cutoff_str = cutoff_date.strftime("%Y-%m-%d")

        # Build filter for published posts after cutoff date
        filter_str = f"published_at:>='{cutoff_str}'"

        all_posts = []
        page = 1

        while len(all_posts) < max_posts:
            posts = self.get_posts(
                limit=15,
                page=page,
                fields=["id", "uuid", "slug", "title", "url", "published_at"],
                filter_str=filter_str
            )

            if not posts:
                break

            all_posts.extend(posts)
            page += 1

            # Safety check to prevent infinite loops
            if page > 20:
                logger.warning("Reached maximum page limit when fetching recent posts")
                break

        # Trim to max_posts
        return all_posts[:max_posts]

    def check_health(self) -> bool:
        """
        Check if the Ghost API is accessible.

        Returns:
            True if API is accessible, False otherwise
        """
        if not self.enabled:
            return False

        # Try to fetch a single post to verify connectivity
        posts = self.get_posts(limit=1, fields=["id"])
        return posts is not None
