"""
Interaction Sync Service for POSSE.

This module retrieves interactions (comments, likes, reposts) from syndicated
posts on Mastodon and Bluesky and stores them for display in Ghost widgets.
"""
import logging
import json
import os
from typing import Dict, Any, List, Optional
from datetime import datetime
from zoneinfo import ZoneInfo
from requests.exceptions import Timeout, RequestException

logger = logging.getLogger(__name__)


class InteractionSyncService:
    """
    Service for syncing social media interactions back to Ghost posts.

    This service retrieves interactions (favorites, reblogs, replies) from
    Mastodon and (likes, reposts, replies) from Bluesky for syndicated posts.

    Attributes:
        mastodon_clients: List of MastodonClient instances
        bluesky_clients: List of BlueskyClient instances
        storage_path: Path to store interaction data files
        mappings_path: Path to syndication mapping files
    """

    def __init__(
        self,
        mastodon_clients: Optional[List[Any]] = None,
        bluesky_clients: Optional[List[Any]] = None,
        storage_path: str = "./data/interactions",
        mappings_path: str = "./data/syndication_mappings"
    ):
        """Initialize the interaction sync service.

        Args:
            mastodon_clients: List of MastodonClient instances
            bluesky_clients: List of BlueskyClient instances
            storage_path: Directory path for storing interaction data
            mappings_path: Directory path for syndication mapping files
        """
        self.mastodon_clients = mastodon_clients or []
        self.bluesky_clients = bluesky_clients or []
        self.storage_path = storage_path
        self.mappings_path = mappings_path

        # Create storage directories if they don't exist
        os.makedirs(self.storage_path, mode=0o755, exist_ok=True)
        os.makedirs(self.mappings_path, mode=0o755, exist_ok=True)

        logger.info(
            f"InteractionSyncService initialized with "
            f"{len(self.mastodon_clients)} Mastodon clients and "
            f"{len(self.bluesky_clients)} Bluesky clients"
        )

    def sync_post_interactions(self, ghost_post_id: str) -> Dict[str, Any]:
        """
        Sync interactions for a specific Ghost post.

        Retrieves interactions from all platforms where this post was syndicated
        and stores the aggregated data. Preserves existing interaction data for
        platforms that fail to sync.

        Args:
            ghost_post_id: Ghost post ID to sync interactions for

        Returns:
            Dictionary containing all interactions from Mastodon and Bluesky, with structure:
            {
              "ghost_post_id": "abc123",
              "updated_at": "2026-01-27T10:00:00Z",
              "syndication_links": {
                "mastodon": {
                  "account_name": {"post_url": "https://..."}
                },
                "bluesky": {
                  "account_name": {"post_url": "https://..."}
                }
              },
              "platforms": {
                "mastodon": {...interaction data...},
                "bluesky": {...interaction data...}
              }
            }

        Example:
            >>> service = InteractionSyncService(mastodon_clients, bluesky_clients)
            >>> interactions = service.sync_post_interactions("abc123")
            >>> print(interactions['syndication_links']['mastodon'])
            >>> print(interactions['platforms']['mastodon'])
        """
        logger.info(f"Syncing interactions for Ghost post: {ghost_post_id}")

        # Load syndication mappings
        mapping = self._load_syndication_mapping(ghost_post_id)
        if not mapping:
            logger.warning(f"No syndication mapping found for post: {ghost_post_id}")
            return self._empty_interaction_data(ghost_post_id)

        # Load existing interaction data to preserve data for platforms that fail to sync
        existing_data = self._load_existing_interaction_data(ghost_post_id)

        # Check if we have existing data to preserve
        has_existing_mastodon = bool(existing_data.get("platforms", {}).get("mastodon", {}))
        has_existing_bluesky = bool(existing_data.get("platforms", {}).get("bluesky", {}))

        if has_existing_mastodon or has_existing_bluesky:
            logger.debug(
                f"Preserving existing interaction data for post {ghost_post_id} "
                f"(Mastodon: {has_existing_mastodon}, Bluesky: {has_existing_bluesky})"
            )

        # Initialize result structure, preserving existing data as fallback
        interactions = {
            "ghost_post_id": ghost_post_id,
            "updated_at": datetime.now(ZoneInfo("UTC")).isoformat(),
            "syndication_links": {
                "mastodon": existing_data.get("syndication_links", {}).get("mastodon", {}),
                "bluesky": existing_data.get("syndication_links", {}).get("bluesky", {})
            },
            "platforms": {
                "mastodon": existing_data.get("platforms", {}).get("mastodon", {}),
                "bluesky": existing_data.get("platforms", {}).get("bluesky", {})
            }
        }

        # Sync Mastodon interactions
        if "mastodon" in mapping.get("platforms", {}):
            for account_name, account_data in mapping["platforms"]["mastodon"].items():
                try:
                    # Handle split posts (account_data is a list) or single posts (account_data is dict)
                    if isinstance(account_data, list):
                        # Split posts - aggregate interactions from all split entries
                        mastodon_data = self._sync_mastodon_split_interactions(
                            account_name=account_name,
                            split_entries=account_data
                        )
                    else:
                        # Single post
                        mastodon_data = self._sync_mastodon_interactions(
                            account_name=account_name,
                            status_id=account_data["status_id"],
                            post_url=account_data["post_url"]
                        )
                    if mastodon_data:
                        interactions["platforms"]["mastodon"][account_name] = mastodon_data
                        # Add to syndication_links summary
                        if "is_split" in mastodon_data and mastodon_data["is_split"]:
                            # For split posts, include all split post URLs
                            interactions["syndication_links"]["mastodon"][account_name] = [
                                {
                                    "post_url": split["post_url"],
                                    "split_index": split["split_index"]
                                }
                                for split in mastodon_data.get("split_posts", [])
                            ]
                        else:
                            # For single posts, just include the post URL
                            interactions["syndication_links"]["mastodon"][account_name] = {
                                "post_url": mastodon_data.get("post_url")
                            }
                except Exception as e:
                    logger.error(
                        f"Failed to sync Mastodon interactions for {account_name}: {e}",
                        exc_info=True
                    )

        # Sync Bluesky interactions
        if "bluesky" in mapping.get("platforms", {}):
            for account_name, account_data in mapping["platforms"]["bluesky"].items():
                try:
                    # Handle split posts (account_data is a list) or single posts (account_data is dict)
                    if isinstance(account_data, list):
                        # Split posts - aggregate interactions from all split entries
                        bluesky_data = self._sync_bluesky_split_interactions(
                            account_name=account_name,
                            split_entries=account_data
                        )
                    else:
                        # Single post
                        bluesky_data = self._sync_bluesky_interactions(
                            account_name=account_name,
                            post_uri=account_data["post_uri"],
                            post_url=account_data["post_url"]
                        )
                    if bluesky_data:
                        interactions["platforms"]["bluesky"][account_name] = bluesky_data
                        # Add to syndication_links summary
                        if "is_split" in bluesky_data and bluesky_data["is_split"]:
                            # For split posts, include all split post URLs
                            interactions["syndication_links"]["bluesky"][account_name] = [
                                {
                                    "post_url": split["post_url"],
                                    "split_index": split["split_index"]
                                }
                                for split in bluesky_data.get("split_posts", [])
                            ]
                        else:
                            # For single posts, just include the post URL
                            interactions["syndication_links"]["bluesky"][account_name] = {
                                "post_url": bluesky_data.get("post_url")
                            }
                except Exception as e:
                    logger.error(
                        f"Failed to sync Bluesky interactions for {account_name}: {e}",
                        exc_info=True
                    )

        # Store the interaction data
        self._store_interaction_data(ghost_post_id, interactions)

        logger.info(f"Successfully synced interactions for post: {ghost_post_id}")
        return interactions

    def _sync_mastodon_interactions(
        self,
        account_name: str,
        status_id: str,
        post_url: str
    ) -> Optional[Dict[str, Any]]:
        """
        Retrieve interactions from a Mastodon status.

        Args:
            account_name: Name of the Mastodon account
            status_id: Mastodon status ID
            post_url: URL of the Mastodon post

        Returns:
            Dictionary with Mastodon interaction data or None if failed
        """
        # Find the matching client
        client = self._find_mastodon_client(account_name)
        if not client or not client.enabled or not client.api:
            logger.warning(f"Mastodon client '{account_name}' not available")
            return None

        try:
            # Get the status
            status = client.api.status(status_id)

            # Get favourites (with pagination for accounts) - limit to avoid timeouts
            try:
                favourited_by = client.api.status_favourited_by(status_id, limit=80)
            except (Timeout, RequestException) as e:
                logger.warning(f"Timeout fetching favourites for status {status_id}: {e}")
                favourited_by = []

            # Get reblogs (with pagination for accounts) - limit to avoid timeouts
            try:
                reblogged_by = client.api.status_reblogged_by(status_id, limit=80)
            except (Timeout, RequestException) as e:
                logger.warning(f"Timeout fetching reblogs for status {status_id}: {e}")
                reblogged_by = []

            # Get context (replies)
            try:
                context = client.api.status_context(status_id)
            except (Timeout, RequestException) as e:
                logger.warning(f"Timeout fetching context for status {status_id}: {e}")
                context = {}

            # Extract reply previews (limit to 10 most recent)
            reply_previews = []
            for reply in context.get("descendants", [])[:10]:
                # Only include direct replies, not replies to replies
                if reply.get("in_reply_to_id") == status_id:
                    reply_previews.append({
                        "author": f"@{reply['account']['acct']}",
                        "author_url": reply['account']['url'],
                        "author_avatar": reply['account']['avatar'],
                        "content": self._strip_html(reply.get("content", "")),
                        "created_at": reply.get("created_at", ""),
                        "url": reply.get("url", "")
                    })

            return {
                "status_id": status_id,
                "post_url": post_url,
                "favorites": status.get("favourites_count", 0),
                "reblogs": status.get("reblogs_count", 0),
                "replies": status.get("replies_count", 0),
                "reply_previews": reply_previews,
                "updated_at": datetime.now(ZoneInfo("UTC")).isoformat()
            }

        except Timeout as e:
            logger.error(f"Timeout syncing Mastodon status {status_id}: {e}")
            return None
        except Exception as e:
            logger.error(f"Error syncing Mastodon status {status_id}: {e}")
            return None

    def _sync_mastodon_split_interactions(
        self,
        account_name: str,
        split_entries: List[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        """
        Aggregate interactions from multiple split Mastodon posts.

        Args:
            account_name: Name of the Mastodon account
            split_entries: List of split post entries with status_id, post_url, etc.

        Returns:
            Aggregated dictionary with Mastodon interaction data or None if all failed
        """
        total_favorites = 0
        total_reblogs = 0
        total_replies = 0
        all_reply_previews = []
        split_posts = []
        successful_syncs = 0

        for entry in split_entries:
            status_id = entry.get("status_id")
            post_url = entry.get("post_url")
            split_index = entry.get("split_index", 0)

            if not status_id:
                continue

            # Sync this individual split post
            data = self._sync_mastodon_interactions(
                account_name=account_name,
                status_id=status_id,
                post_url=post_url
            )

            if data:
                successful_syncs += 1
                total_favorites += data.get("favorites", 0)
                total_reblogs += data.get("reblogs", 0)
                total_replies += data.get("replies", 0)

                # Add reply previews with split context
                for reply in data.get("reply_previews", []):
                    reply_with_context = {
                        **reply,
                        "split_index": split_index,
                        "split_post_url": post_url
                    }
                    all_reply_previews.append(reply_with_context)

                # Track individual split post data
                split_posts.append({
                    "status_id": status_id,
                    "post_url": post_url,
                    "split_index": split_index,
                    "favorites": data.get("favorites", 0),
                    "reblogs": data.get("reblogs", 0),
                    "replies": data.get("replies", 0)
                })

        if successful_syncs == 0:
            return None

        # Sort replies by created_at (chronological - oldest first)
        all_reply_previews.sort(
            key=lambda r: r.get("created_at", ""),
            reverse=False  # Oldest first for chronological order
        )

        return {
            "is_split": True,
            "total_splits": len(split_entries),
            "synced_splits": successful_syncs,
            "split_posts": split_posts,
            "favorites": total_favorites,
            "reblogs": total_reblogs,
            "replies": total_replies,
            "reply_previews": all_reply_previews[:20],  # Limit to 20 across all splits
            "updated_at": datetime.now(ZoneInfo("UTC")).isoformat()
        }

    def _sync_bluesky_interactions(
        self,
        account_name: str,
        post_uri: str,
        post_url: str
    ) -> Optional[Dict[str, Any]]:
        """
        Retrieve interactions from a Bluesky post.

        Args:
            account_name: Name of the Bluesky account
            post_uri: Bluesky post URI (AT Protocol URI)
            post_url: URL of the Bluesky post

        Returns:
            Dictionary with Bluesky interaction data or None if failed
        """
        # Find the matching client
        client = self._find_bluesky_client(account_name)
        if not client or not client.enabled or not client.api:
            logger.warning(f"Bluesky client '{account_name}' not available")
            return None

        try:
            # Get post thread (includes the post and replies)
            thread_response = client.api.app.bsky.feed.get_post_thread({"uri": post_uri})
            thread = thread_response.thread

            # Get likes
            likes_response = client.api.app.bsky.feed.get_likes({
                "uri": post_uri,
                "limit": 100
            })

            # Get reposts
            reposts_response = client.api.app.bsky.feed.get_reposted_by({
                "uri": post_uri,
                "limit": 100
            })

            # Extract reply previews from thread
            reply_previews = []
            if hasattr(thread, 'replies') and thread.replies:
                for reply in thread.replies[:10]:  # Limit to 10 most recent
                    if hasattr(reply, 'post'):
                        post = reply.post
                        author = post.author
                        reply_previews.append({
                            "author": f"@{author.handle}",
                            "author_url": f"https://bsky.app/profile/{author.handle}",
                            "author_avatar": author.avatar if hasattr(author, 'avatar') else None,
                            "content": post.record.text if hasattr(post.record, 'text') else "",
                            "created_at": post.record.created_at if hasattr(post.record, 'created_at') else "",
                            "url": f"https://bsky.app/profile/{author.handle}/post/{post.uri.split('/')[-1]}"
                        })

            # Count interactions
            like_count = len(likes_response.likes) if hasattr(likes_response, 'likes') else 0
            repost_count = len(reposts_response.reposted_by) if hasattr(reposts_response, 'reposted_by') else 0

            # Get reply count from thread post
            reply_count = 0
            if hasattr(thread, 'post') and hasattr(thread.post, 'reply_count'):
                reply_count = thread.post.reply_count
            elif hasattr(thread, 'replies'):
                reply_count = len(thread.replies)

            return {
                "post_uri": post_uri,
                "post_url": post_url,
                "likes": like_count,
                "reposts": repost_count,
                "replies": reply_count,
                "reply_previews": reply_previews,
                "updated_at": datetime.now(ZoneInfo("UTC")).isoformat()
            }

        except Exception as e:
            logger.error(f"Error syncing Bluesky post {post_uri}: {e}")
            return None

    def _sync_bluesky_split_interactions(
        self,
        account_name: str,
        split_entries: List[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        """
        Aggregate interactions from multiple split Bluesky posts.

        Args:
            account_name: Name of the Bluesky account
            split_entries: List of split post entries with post_uri, post_url, etc.

        Returns:
            Aggregated dictionary with Bluesky interaction data or None if all failed
        """
        total_likes = 0
        total_reposts = 0
        total_replies = 0
        all_reply_previews = []
        split_posts = []
        successful_syncs = 0

        for entry in split_entries:
            post_uri = entry.get("post_uri")
            post_url = entry.get("post_url")
            split_index = entry.get("split_index", 0)

            if not post_uri:
                continue

            # Sync this individual split post
            data = self._sync_bluesky_interactions(
                account_name=account_name,
                post_uri=post_uri,
                post_url=post_url
            )

            if data:
                successful_syncs += 1
                total_likes += data.get("likes", 0)
                total_reposts += data.get("reposts", 0)
                total_replies += data.get("replies", 0)

                # Add reply previews with split context
                for reply in data.get("reply_previews", []):
                    reply_with_context = {
                        **reply,
                        "split_index": split_index,
                        "split_post_url": post_url
                    }
                    all_reply_previews.append(reply_with_context)

                # Track individual split post data
                split_posts.append({
                    "post_uri": post_uri,
                    "post_url": post_url,
                    "split_index": split_index,
                    "likes": data.get("likes", 0),
                    "reposts": data.get("reposts", 0),
                    "replies": data.get("replies", 0)
                })

        if successful_syncs == 0:
            return None

        # Sort replies by created_at (chronological - oldest first)
        all_reply_previews.sort(
            key=lambda r: r.get("created_at", ""),
            reverse=False  # Oldest first for chronological order
        )

        return {
            "is_split": True,
            "total_splits": len(split_entries),
            "synced_splits": successful_syncs,
            "split_posts": split_posts,
            "likes": total_likes,
            "reposts": total_reposts,
            "replies": total_replies,
            "reply_previews": all_reply_previews[:20],  # Limit to 20 across all splits
            "updated_at": datetime.now(ZoneInfo("UTC")).isoformat()
        }

    def _find_mastodon_client(self, account_name: str) -> Optional[Any]:
        """Find Mastodon client by account name."""
        for client in self.mastodon_clients:
            if client.account_name == account_name:
                return client
        return None

    def _find_bluesky_client(self, account_name: str) -> Optional[Any]:
        """Find Bluesky client by account name."""
        for client in self.bluesky_clients:
            if client.account_name == account_name:
                return client
        return None

    def _load_syndication_mapping(self, ghost_post_id: str) -> Optional[Dict[str, Any]]:
        """
        Load syndication mapping for a Ghost post.

        Args:
            ghost_post_id: Ghost post ID

        Returns:
            Mapping dictionary or None if not found
        """
        mapping_file = os.path.join(self.mappings_path, f"{ghost_post_id}.json")

        if not os.path.exists(mapping_file):
            return None

        try:
            with open(mapping_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load mapping file {mapping_file}: {e}")
            return None

    def _load_existing_interaction_data(self, ghost_post_id: str) -> Dict[str, Any]:
        """
        Load existing interaction data for a Ghost post.

        This is used to preserve existing data when a sync fails for some platforms,
        preventing data loss during partial sync failures.

        Args:
            ghost_post_id: Ghost post ID

        Returns:
            Existing interaction data dictionary, or empty structure if not found
        """
        interaction_file = os.path.join(self.storage_path, f"{ghost_post_id}.json")

        if not os.path.exists(interaction_file):
            return self._empty_interaction_data(ghost_post_id)

        try:
            with open(interaction_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load existing interaction data {interaction_file}: {e}")
            return self._empty_interaction_data(ghost_post_id)

    def _store_interaction_data(self, ghost_post_id: str, data: Dict[str, Any]) -> None:
        """
        Store interaction data to file.

        Args:
            ghost_post_id: Ghost post ID
            data: Interaction data to store
        """
        output_file = os.path.join(self.storage_path, f"{ghost_post_id}.json")

        try:
            with open(output_file, 'w') as f:
                json.dump(data, f, indent=2)
            logger.debug(f"Stored interaction data to {output_file}")
        except Exception as e:
            logger.error(f"Failed to store interaction data to {output_file}: {e}")

    def _empty_interaction_data(self, ghost_post_id: str) -> Dict[str, Any]:
        """Return empty interaction data structure."""
        return {
            "ghost_post_id": ghost_post_id,
            "updated_at": datetime.now(ZoneInfo("UTC")).isoformat(),
            "syndication_links": {
                "mastodon": {},
                "bluesky": {}
            },
            "platforms": {
                "mastodon": {},
                "bluesky": {}
            }
        }

    def discover_syndication_mapping(
        self,
        ghost_post_id: str,
        ghost_post_url: str,
        max_posts_to_search: int = 50
    ) -> bool:
        """
        Discover syndication mapping by searching recent posts for Ghost post URL.

        This method searches through recent Mastodon and Bluesky posts to find
        any that link back to the specified Ghost post. If found, it creates
        a syndication mapping file for future use.

        IMPORTANT: This method preserves existing mappings. If a mapping already
        exists for an account, that account is skipped during discovery to avoid
        unnecessary API calls and potential data overwrites.

        Args:
            ghost_post_id: Ghost post ID to discover mapping for
            ghost_post_url: URL of the Ghost post to search for
            max_posts_to_search: Maximum number of posts to search per account (default: 50)

        Returns:
            True if at least one mapping was discovered and stored, False otherwise

        Example:
            >>> service = InteractionSyncService(mastodon_clients, bluesky_clients)
            >>> found = service.discover_syndication_mapping(
            ...     "abc123",
            ...     "https://blog.example.com/my-post/"
            ... )
            >>> if found:
            ...     print("Mapping discovered!")
        """
        logger.info(
            f"Searching for syndication mapping for Ghost post {ghost_post_id} "
            f"(URL: {ghost_post_url})"
        )

        # Normalize the Ghost post URL for comparison (remove trailing slash, query params)
        normalized_ghost_url = ghost_post_url.rstrip('/').split('?')[0].split('#')[0]

        # Load existing mapping to avoid overwriting existing accounts
        existing_mapping = self._load_syndication_mapping(ghost_post_id)
        existing_mastodon_accounts = set()
        existing_bluesky_accounts = set()

        if existing_mapping:
            logger.info(f"Found existing syndication mapping for post {ghost_post_id}")
            if "mastodon" in existing_mapping.get("platforms", {}):
                existing_mastodon_accounts = set(existing_mapping["platforms"]["mastodon"].keys())
                logger.info(f"  - Existing Mastodon accounts: {', '.join(existing_mastodon_accounts)}")
            if "bluesky" in existing_mapping.get("platforms", {}):
                existing_bluesky_accounts = set(existing_mapping["platforms"]["bluesky"].keys())
                logger.info(f"  - Existing Bluesky accounts: {', '.join(existing_bluesky_accounts)}")

        mapping_found = False

        # Search Mastodon posts
        for client in self.mastodon_clients:
            if not client.enabled:
                continue

            # Skip if this account already has a mapping (preserve existing data)
            if client.account_name in existing_mastodon_accounts:
                logger.debug(
                    f"Skipping Mastodon account '{client.account_name}' - "
                    f"mapping already exists (preserving existing data)"
                )
                continue

            try:
                posts = client.get_recent_posts(limit=max_posts_to_search)
                logger.debug(
                    f"Searching {len(posts)} recent Mastodon posts from "
                    f"'{client.account_name}' for Ghost post URL"
                )

                for post in posts:
                    # Extract URLs from post content (HTML)
                    content = post.get('content', '')
                    if not content:
                        continue

                    # Simple URL extraction from HTML (looks for href attributes)
                    import re
                    urls = re.findall(r'href=["\']([^"\']+)["\']', content)

                    # Also check plain text content for URLs
                    plain_text = self._strip_html(content)
                    text_urls = re.findall(r'https?://[^\s]+', plain_text)
                    urls.extend(text_urls)

                    # Normalize and check each URL
                    for url in urls:
                        normalized_url = url.rstrip('/').split('?')[0].split('#')[0]
                        if normalized_url == normalized_ghost_url:
                            # Found a match! Store the syndication mapping
                            logger.info(
                                f"Found Mastodon post linking to Ghost post: "
                                f"{post.get('url', post.get('id'))}"
                            )

                            post_data = {
                                "status_id": str(post.get('id')),
                                "post_url": post.get('url', '')
                            }

                            store_syndication_mapping(
                                ghost_post_id=ghost_post_id,
                                ghost_post_url=ghost_post_url,
                                platform="mastodon",
                                account_name=client.account_name,
                                post_data=post_data,
                                mappings_path=self.mappings_path
                            )

                            mapping_found = True
                            break  # Found mapping for this account, move to next

            except Exception as e:
                logger.error(
                    f"Error searching Mastodon posts from '{client.account_name}': {e}",
                    exc_info=True
                )

        # Search Bluesky posts
        for client in self.bluesky_clients:
            if not client.enabled:
                continue

            # Skip if this account already has a mapping (preserve existing data)
            if client.account_name in existing_bluesky_accounts:
                logger.debug(
                    f"Skipping Bluesky account '{client.account_name}' - "
                    f"mapping already exists (preserving existing data)"
                )
                continue

            try:
                posts = client.get_recent_posts(limit=max_posts_to_search)
                logger.debug(
                    f"Searching {len(posts)} recent Bluesky posts from "
                    f"'{client.account_name}' for Ghost post URL"
                )

                for post in posts:
                    # Extract URLs from post text
                    text = post.get('text', '')
                    if not text:
                        continue

                    # Extract URLs from text
                    import re
                    urls = re.findall(r'https?://[^\s]+', text)

                    # Normalize and check each URL
                    for url in urls:
                        # Clean up URL (remove trailing punctuation)
                        url = url.rstrip('.,;!?)')
                        normalized_url = url.rstrip('/').split('?')[0].split('#')[0]

                        if normalized_url == normalized_ghost_url:
                            # Found a match! Store the syndication mapping
                            logger.info(
                                f"Found Bluesky post linking to Ghost post: "
                                f"{post.get('url', post.get('uri'))}"
                            )

                            post_data = {
                                "post_uri": post.get('uri'),
                                "post_url": post.get('url', '')
                            }

                            store_syndication_mapping(
                                ghost_post_id=ghost_post_id,
                                ghost_post_url=ghost_post_url,
                                platform="bluesky",
                                account_name=client.account_name,
                                post_data=post_data,
                                mappings_path=self.mappings_path
                            )

                            mapping_found = True
                            break  # Found mapping for this account, move to next

            except Exception as e:
                logger.error(
                    f"Error searching Bluesky posts from '{client.account_name}': {e}",
                    exc_info=True
                )

        # Load final mapping to report on what was preserved and what was discovered
        final_mapping = self._load_syndication_mapping(ghost_post_id)

        if mapping_found:
            logger.info(
                f"Successfully discovered syndication mapping for Ghost post {ghost_post_id}"
            )
            # Log summary of preserved vs discovered
            if final_mapping:
                preserved_count = len(existing_mastodon_accounts) + len(existing_bluesky_accounts)
                if preserved_count > 0:
                    logger.info(
                        f"  - Preserved {preserved_count} existing account mapping(s)"
                    )
                new_mastodon = set(final_mapping.get("platforms", {}).get("mastodon", {}).keys()) - existing_mastodon_accounts
                new_bluesky = set(final_mapping.get("platforms", {}).get("bluesky", {}).keys()) - existing_bluesky_accounts
                new_count = len(new_mastodon) + len(new_bluesky)
                if new_count > 0:
                    logger.info(f"  - Discovered {new_count} new account mapping(s)")
                    if new_mastodon:
                        logger.info(f"    • Mastodon: {', '.join(new_mastodon)}")
                    if new_bluesky:
                        logger.info(f"    • Bluesky: {', '.join(new_bluesky)}")
        else:
            if existing_mapping:
                logger.info(
                    f"No new syndication mappings discovered for Ghost post {ghost_post_id}, "
                    f"but existing mappings were preserved"
                )
            else:
                logger.info(
                    f"No syndication mapping found for Ghost post {ghost_post_id} "
                    f"in recent posts"
                )

        return mapping_found

    @staticmethod
    def _strip_html(html_content: str) -> str:
        """
        Strip HTML tags from content.

        Simple implementation - for production, consider using a library like BeautifulSoup.

        Args:
            html_content: HTML string

        Returns:
            Plain text with HTML tags removed
        """
        import re
        # Remove HTML tags
        text = re.sub(r'<[^>]+>', '', html_content)
        # Decode HTML entities
        text = text.replace('&lt;', '<').replace('&gt;', '>').replace('&amp;', '&')
        text = text.replace('&quot;', '"').replace('&#39;', "'")
        return text.strip()


def store_syndication_mapping(
    ghost_post_id: str,
    ghost_post_url: str,
    platform: str,
    account_name: str,
    post_data: Dict[str, Any],
    mappings_path: str = "./data/syndication_mappings",
    split_info: Optional[Dict[str, Any]] = None
) -> None:
    """
    Store syndication mapping when a post is syndicated to a platform.

    This function should be called after successfully posting to a social media platform.
    For split posts (multi-image posts split into individual posts), each split post
    is stored as a separate entry with split metadata.

    IMPORTANT: This function preserves existing mappings. It only updates the specific
    platform/account_name combination being added and does not modify or delete mappings
    for other platforms or accounts.

    Args:
        ghost_post_id: Ghost post ID
        ghost_post_url: URL of the Ghost post
        platform: Platform name ("mastodon" or "bluesky")
        account_name: Account name on the platform
        post_data: Platform-specific post data (status_id, post_url for Mastodon;
                  post_uri, post_url for Bluesky)
        mappings_path: Directory path for storing mapping files
        split_info: Optional split post metadata:
            - is_split: True if this is part of a split post
            - split_index: Index of this post in the split (0-based)
            - total_splits: Total number of split posts
            - image_url: URL of the image for this split

    Example:
        >>> # After posting to Mastodon (non-split)
        >>> store_syndication_mapping(
        ...     ghost_post_id="abc123",
        ...     ghost_post_url="https://blog.example.com/post/",
        ...     platform="mastodon",
        ...     account_name="personal",
        ...     post_data={"status_id": "123456", "post_url": "https://..."}
        ... )
        >>> # After posting a split post to Mastodon
        >>> store_syndication_mapping(
        ...     ghost_post_id="abc123",
        ...     ghost_post_url="https://blog.example.com/post/",
        ...     platform="mastodon",
        ...     account_name="archive",
        ...     post_data={"status_id": "789012", "post_url": "https://..."},
        ...     split_info={"is_split": True, "split_index": 0, "total_splits": 3}
        ... )
    """
    os.makedirs(mappings_path, mode=0o755, exist_ok=True)
    mapping_file = os.path.join(mappings_path, f"{ghost_post_id}.json")

    # Load existing mapping or create new
    if os.path.exists(mapping_file):
        try:
            with open(mapping_file, 'r') as f:
                mapping = json.load(f)
        except Exception as e:
            logger.error(f"Failed to load existing mapping {mapping_file}: {e}")
            mapping = {
                "ghost_post_id": ghost_post_id,
                "ghost_post_url": ghost_post_url,
                "syndicated_at": datetime.now(ZoneInfo("UTC")).isoformat(),
                "platforms": {}
            }
    else:
        mapping = {
            "ghost_post_id": ghost_post_id,
            "ghost_post_url": ghost_post_url,
            "syndicated_at": datetime.now(ZoneInfo("UTC")).isoformat(),
            "platforms": {}
        }

    # Ensure platform exists in mapping
    if platform not in mapping["platforms"]:
        mapping["platforms"][platform] = {}

    # Handle split posts - store as list of entries per account
    if split_info and split_info.get("is_split"):
        # Add split metadata to post_data
        post_data_with_split = {
            **post_data,
            "is_split": True,
            "split_index": split_info.get("split_index", 0),
            "total_splits": split_info.get("total_splits", 1),
            "image_url": split_info.get("image_url")
        }

        # Check if this account already has entries
        existing = mapping["platforms"][platform].get(account_name)

        if existing is None:
            # First split post for this account - create list
            mapping["platforms"][platform][account_name] = [post_data_with_split]
        elif isinstance(existing, list):
            # Already a list - append if not duplicate
            existing_ids = {
                entry.get("status_id") or entry.get("post_uri")
                for entry in existing
            }
            new_id = post_data.get("status_id") or post_data.get("post_uri")
            if new_id not in existing_ids:
                existing.append(post_data_with_split)
        else:
            # Was a single entry (non-split), convert to list with both
            mapping["platforms"][platform][account_name] = [existing, post_data_with_split]

        logger.info(
            f"Stored split syndication mapping for {platform}/{account_name} "
            f"(split {split_info.get('split_index', 0) + 1}/{split_info.get('total_splits', 1)}) "
            f"to {mapping_file}"
        )
    else:
        # Non-split post - store as single entry (original behavior)
        mapping["platforms"][platform][account_name] = post_data

        logger.info(f"Stored syndication mapping for {platform}/{account_name} to {mapping_file}")

    # Save mapping
    try:
        with open(mapping_file, 'w') as f:
            json.dump(mapping, f, indent=2)
    except Exception as e:
        logger.error(f"Failed to store syndication mapping to {mapping_file}: {e}")
