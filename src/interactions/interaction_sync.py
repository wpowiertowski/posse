"""
Interaction Sync Service for POSSE.

This module retrieves interactions (comments, likes, reposts) from syndicated
posts on Mastodon and Bluesky and stores them for display in Ghost widgets.
"""
import logging
import os
import re
from typing import Dict, Any, List, Optional
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from requests.exceptions import Timeout, RequestException
from mastodon import MastodonNotFoundError

from interactions.storage import InteractionDataStore

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
    """

    def __init__(
        self,
        mastodon_clients: Optional[List[Any]] = None,
        bluesky_clients: Optional[List[Any]] = None,
        storage_path: str = "./data",
        timezone_name: str = "UTC",
        notifier: Optional[Any] = None,
        dead_link_confirm_threshold: int = 2,
    ):
        """Initialize the interaction sync service.

        Args:
            mastodon_clients: List of MastodonClient instances
            bluesky_clients: List of BlueskyClient instances
            storage_path: Directory path for storing interaction data
            timezone_name: IANA timezone name used for generated timestamps
            notifier: Optional PushoverNotifier instance for new-reply notifications
            dead_link_confirm_threshold: Number of consecutive sweeps a Mastodon status
                must return 404 before its syndication link is suppressed. Guards against
                a single fluke 404 hiding a link that actually exists.
        """
        self.mastodon_clients = mastodon_clients or []
        self.bluesky_clients = bluesky_clients or []
        self.storage_path = storage_path
        self.timezone_name = self._normalize_timezone_name(timezone_name)
        self.timezone = ZoneInfo(self.timezone_name)
        self.notifier = notifier
        self.dead_link_confirm_threshold = max(1, int(dead_link_confirm_threshold))

        # Create storage directory if it doesn't exist
        os.makedirs(self.storage_path, mode=0o755, exist_ok=True)
        self.data_store = InteractionDataStore(self.storage_path)

        logger.info(
            f"InteractionSyncService initialized with "
            f"{len(self.mastodon_clients)} Mastodon clients and "
            f"{len(self.bluesky_clients)} Bluesky clients "
            f"(timezone={self.timezone_name})"
        )

    @staticmethod
    def _normalize_timezone_name(timezone_name: str) -> str:
        """Return a valid timezone name, falling back to UTC."""
        if not isinstance(timezone_name, str) or not timezone_name.strip():
            return "UTC"
        candidate = timezone_name.strip()
        try:
            ZoneInfo(candidate)
        except ZoneInfoNotFoundError:
            logger.warning(f"Unknown timezone '{candidate}' for interaction sync, falling back to UTC")
            return "UTC"
        return candidate

    def _now_isoformat(self) -> str:
        """Return current time in the configured timezone as ISO-8601."""
        return datetime.now(self.timezone).isoformat()

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

        # Capture previous reply URLs BEFORE any mutations occur, so we can detect
        # new replies after the sync completes.
        previous_reply_urls = self._collect_reply_urls(existing_data.get("platforms", {}))

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
            "updated_at": self._now_isoformat(),
            "syndication_links": {
                "mastodon": existing_data.get("syndication_links", {}).get("mastodon", {}),
                "bluesky": existing_data.get("syndication_links", {}).get("bluesky", {})
            },
            "platforms": {
                "mastodon": existing_data.get("platforms", {}).get("mastodon", {}),
                "bluesky": existing_data.get("platforms", {}).get("bluesky", {})
            }
        }

        # Track sync success/failure
        mastodon_accounts_to_sync = 0
        mastodon_accounts_synced = 0
        bluesky_accounts_to_sync = 0
        bluesky_accounts_synced = 0

        # Sync Mastodon interactions - wrapped to ensure Bluesky sync runs even if
        # Mastodon sync encounters an unexpected error
        try:
            if "mastodon" in mapping.get("platforms", {}):
                mastodon_accounts_to_sync = len(mapping["platforms"]["mastodon"])
                for account_name, account_data in mapping["platforms"]["mastodon"].items():
                    try:
                        # Skip accounts whose status was confirmed deleted by the
                        # dead-link sweep. Keep them suppressed without re-hitting the
                        # (gone) status every cycle.
                        if self._is_account_deleted(account_data):
                            self._drop_account(interactions, "mastodon", account_name)
                            mastodon_accounts_to_sync -= 1
                            continue
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
                            mastodon_accounts_synced += 1
                            interactions["platforms"]["mastodon"][account_name] = mastodon_data
                            # Add to syndication_links summary.
                            # For split posts use the post that contains the featured image
                            # (split_index 0, which is always the feature_image in Ghost).
                            if "is_split" in mastodon_data and mastodon_data["is_split"]:
                                split_posts = mastodon_data.get("split_posts", [])
                                featured = next(
                                    (s for s in split_posts if s.get("split_index") == 0),
                                    split_posts[0] if split_posts else None,
                                )
                                if featured:
                                    interactions["syndication_links"]["mastodon"][account_name] = {
                                        "post_url": featured["post_url"]
                                    }
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
        except Exception as e:
            logger.error(f"Unexpected error during Mastodon interaction sync: {e}", exc_info=True)

        # Sync Bluesky interactions - wrapped to ensure one platform's failure doesn't
        # prevent the other from syncing
        try:
            if "bluesky" in mapping.get("platforms", {}):
                bluesky_accounts_to_sync = len(mapping["platforms"]["bluesky"])
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
                            bluesky_accounts_synced += 1
                            interactions["platforms"]["bluesky"][account_name] = bluesky_data
                            # Add to syndication_links summary.
                            # For split posts use the post that contains the featured image
                            # (split_index 0, which is always the feature_image in Ghost).
                            if "is_split" in bluesky_data and bluesky_data["is_split"]:
                                split_posts = bluesky_data.get("split_posts", [])
                                featured = next(
                                    (s for s in split_posts if s.get("split_index") == 0),
                                    split_posts[0] if split_posts else None,
                                )
                                if featured:
                                    interactions["syndication_links"]["bluesky"][account_name] = {
                                        "post_url": featured["post_url"]
                                    }
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
        except Exception as e:
            logger.error(f"Unexpected error during Bluesky interaction sync: {e}", exc_info=True)

        # Notify about new replies before storing updated data
        if self.notifier:
            self._notify_new_replies(previous_reply_urls, interactions)

        # Store the interaction data
        self._store_interaction_data(ghost_post_id, interactions)

        # Log appropriate message based on sync results
        total_to_sync = mastodon_accounts_to_sync + bluesky_accounts_to_sync
        total_synced = mastodon_accounts_synced + bluesky_accounts_synced

        if total_synced == 0 and total_to_sync > 0:
            logger.warning(
                f"Failed to sync any interactions for post {ghost_post_id} "
                f"(0/{total_to_sync} accounts)"
            )
        elif total_synced < total_to_sync:
            logger.warning(
                f"Partially synced interactions for post {ghost_post_id} "
                f"({total_synced}/{total_to_sync} accounts: "
                f"Mastodon {mastodon_accounts_synced}/{mastodon_accounts_to_sync}, "
                f"Bluesky {bluesky_accounts_synced}/{bluesky_accounts_to_sync})"
            )
        else:
            logger.info(
                f"Successfully synced interactions for post {ghost_post_id} "
                f"({total_synced} accounts: "
                f"Mastodon {mastodon_accounts_synced}, "
                f"Bluesky {bluesky_accounts_synced})"
            )

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
        client = self._find_client(self.mastodon_clients, account_name)
        if not client or not client.enabled or not client.api:
            logger.warning(f"Mastodon client '{account_name}' not available")
            return None

        try:
            # Get the status
            status = client.api.status(status_id)

            # Get favourites (with pagination for accounts) - limit to avoid timeouts
            try:
                favourited_by = client.api.status_favourited_by(status_id)
            except (Timeout, RequestException, TypeError) as e:
                logger.warning(f"Error fetching favourites for status {status_id}: {e}")
                favourited_by = []

            # Get reblogs (with pagination for accounts) - limit to avoid timeouts
            try:
                reblogged_by = client.api.status_reblogged_by(status_id)
            except (Timeout, RequestException, TypeError) as e:
                logger.warning(f"Error fetching reblogs for status {status_id}: {e}")
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
                    # Convert datetime to ISO format string if needed
                    created_at = reply.get("created_at", "")
                    if hasattr(created_at, 'isoformat'):
                        created_at = created_at.isoformat()

                    reply_previews.append({
                        "author": f"@{reply['account']['acct']}",
                        "author_url": reply['account']['url'],
                        "author_avatar": reply['account']['avatar'],
                        "content": self._strip_html(reply.get("content", "")),
                        "created_at": created_at,
                        "url": reply.get("url", "")
                    })

            return {
                "status_id": status_id,
                "post_url": post_url,
                "favorites": status.get("favourites_count", 0),
                "reblogs": status.get("reblogs_count", 0),
                "replies": status.get("replies_count", 0),
                "reply_previews": reply_previews,
                "updated_at": self._now_isoformat()
            }

        except Timeout as e:
            logger.error(f"Timeout syncing Mastodon status {status_id}: {e}")
            return None
        except MastodonNotFoundError:
            # Status appears deleted. Do not suppress here — defer to the strike-gated
            # dead-link sweep so a transient/fluke 404 cannot hide a real link.
            logger.info(
                f"Mastodon status {status_id} not found (404); "
                f"deferring suppression to dead-link sweep"
            )
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
            "updated_at": self._now_isoformat()
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
        client = self._find_client(self.bluesky_clients, account_name)
        if not client or not client.enabled or not client.api:
            logger.warning(f"Bluesky client '{account_name}' not available")
            return None

        # Try to sync, with one retry if token is expired
        for attempt in range(2):
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
                    "updated_at": self._now_isoformat()
                }

            except Exception as e:
                error_str = str(e)
                # Check if this is an expired token error
                if attempt == 0 and ("ExpiredToken" in error_str or "Token has been revoked" in error_str):
                    logger.warning(f"Bluesky token expired for '{account_name}', attempting to re-authenticate")
                    if hasattr(client, 're_authenticate') and client.re_authenticate():
                        logger.info(f"Re-authentication successful, retrying sync for {post_uri}")
                        continue  # Retry the operation
                    else:
                        logger.error(f"Re-authentication failed for '{account_name}'")

                # Either not a token error, or retry failed
                logger.error(f"Error syncing Bluesky post {post_uri}: {e}")
                return None

        # Should not reach here, but return None if we do
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
            "updated_at": self._now_isoformat()
        }

    def _collect_reply_urls(self, platforms_data: Dict[str, Any]) -> set:
        """Collect all reply URLs from platforms interaction data.

        Args:
            platforms_data: The 'platforms' dict from interaction data

        Returns:
            Set of reply URL strings
        """
        urls: set = set()
        for _platform_name, accounts in platforms_data.items():
            if not isinstance(accounts, dict):
                continue
            for _account_name, account_data in accounts.items():
                if not isinstance(account_data, dict):
                    continue
                for reply in account_data.get("reply_previews", []):
                    url = reply.get("url")
                    if url:
                        urls.add(url)
        return urls

    def _notify_new_replies(
        self,
        previous_reply_urls: set,
        new_data: Dict[str, Any],
    ) -> None:
        """Send notifications for replies that were not present in the previous sync.

        Args:
            previous_reply_urls: Set of reply URLs already known before this sync
            new_data: Freshly synced interaction data
        """
        for platform_name, accounts in new_data.get("platforms", {}).items():
            if not isinstance(accounts, dict):
                continue
            for account_name, account_data in accounts.items():
                if not isinstance(account_data, dict):
                    continue
                for reply in account_data.get("reply_previews", []):
                    url = reply.get("url")
                    if not url or url in previous_reply_urls:
                        continue
                    # This is a new reply — send a notification
                    try:
                        self.notifier.notify_new_social_reply(
                            platform=platform_name.capitalize(),
                            account_name=account_name,
                            author=reply.get("author", "unknown"),
                            content_snippet=reply.get("content", ""),
                            reply_url=url,
                        )
                    except Exception as e:
                        logger.error(
                            f"Failed to send new-reply notification for {url}: {e}"
                        )

    def _find_client(self, clients: List[Any], account_name: str) -> Optional[Any]:
        """Find client by account name from a list of clients.

        Args:
            clients: List of social media client instances
            account_name: Name of the account to find

        Returns:
            Matching client or None if not found
        """
        for client in clients:
            if client.account_name == account_name:
                return client
        return None

    def _mastodon_status_exists(self, account_name: str, status_id: str) -> Optional[bool]:
        """Check whether a Mastodon status still exists.

        Distinguishes a definitive deletion from a transient outage so that a
        Mastodon outage never causes us to suppress links that actually exist.

        Args:
            account_name: Name of the Mastodon account that owns the status
            status_id: Mastodon status ID to check

        Returns:
            True  - the status exists,
            False - the status is gone (HTTP 404),
            None  - unknown (no/disabled client, timeout, 5xx, network error). Callers
                    must treat None as "do not change state".
        """
        client = self._find_client(self.mastodon_clients, account_name)
        if not client or not client.enabled or not client.api:
            return None

        try:
            client.api.status(status_id)
            return True
        except MastodonNotFoundError:
            return False
        except Exception as e:
            logger.warning(
                f"Could not verify Mastodon status {status_id} for '{account_name}' "
                f"(treating as unknown, not deleted): {e}"
            )
            return None

    @staticmethod
    def _is_account_deleted(account_data: Any) -> bool:
        """Return True if a mapping account entry is confirmed deleted.

        For split posts (list) the account counts as deleted only when every
        sub-entry is flagged deleted.
        """
        if isinstance(account_data, list):
            return bool(account_data) and all(
                isinstance(e, dict) and e.get("deleted") for e in account_data
            )
        if isinstance(account_data, dict):
            return bool(account_data.get("deleted"))
        return False

    @staticmethod
    def _featured_post_url(account_data: Any) -> Optional[str]:
        """Return the post URL to present for a (possibly split) account entry.

        Prefers a live (not-deleted) sub-entry; for splits, the featured image post
        (split_index 0) when available.
        """
        if isinstance(account_data, list):
            alive = [e for e in account_data if isinstance(e, dict) and not e.get("deleted")]
            if not alive:
                return None
            featured = next((e for e in alive if e.get("split_index") == 0), alive[0])
            return featured.get("post_url")
        if isinstance(account_data, dict):
            if account_data.get("deleted"):
                return None
            return account_data.get("post_url")
        return None

    @staticmethod
    def _drop_account(interactions: Dict[str, Any], platform: str, account_name: str) -> None:
        """Remove an account from both presentation sections of interaction data."""
        for section in ("platforms", "syndication_links"):
            interactions.get(section, {}).get(platform, {}).pop(account_name, None)

    def prune_dead_links(self) -> Dict[str, int]:
        """Scan all syndication mappings for deleted Mastodon posts and suppress them.

        Bypasses the scheduler age window (auto-deleted posts are almost always already
        too old to be re-synced) and performs only a cheap existence check per status.

        Outage-safe and self-healing:
        - A definitive HTTP 404 increments a per-entry ``dead_strikes`` counter; the link
          is only suppressed once it reaches ``dead_link_confirm_threshold`` consecutive
          sweeps, so a single fluke 404 cannot hide a real link.
        - Any non-404 failure (timeout, 5xx, network, no client) is treated as unknown
          and produces no state change.
        - A previously suppressed entry that becomes reachable again is resurrected.

        Records are never purged — entries are only flagged ``deleted: true`` while
        retaining ``status_id``/``post_url``.

        Returns:
            Stats dict with ``checked``, ``newly_suppressed``, ``resurrected`` and
            ``pending_strikes`` counts.
        """
        stats = {"checked": 0, "newly_suppressed": 0, "resurrected": 0, "pending_strikes": 0}

        if not self.mastodon_clients:
            logger.debug("Dead-link sweep skipped: no Mastodon clients configured")
            return stats

        mappings = self.data_store.list_syndication_mappings()
        logger.info(f"Dead-link sweep starting over {len(mappings)} syndication mapping(s)")

        for mapping in mappings:
            ghost_post_id = str(mapping.get("ghost_post_id", ""))
            if not ghost_post_id:
                continue
            mastodon_accounts = mapping.get("platforms", {}).get("mastodon", {})
            if not mastodon_accounts:
                continue

            mapping_changed = False
            for account_name, account_data in list(mastodon_accounts.items()):
                was_deleted = self._is_account_deleted(account_data)
                entries = account_data if isinstance(account_data, list) else [account_data]
                account_changed = False

                for entry in entries:
                    if not isinstance(entry, dict):
                        continue
                    status_id = entry.get("status_id")
                    if not status_id:
                        continue

                    stats["checked"] += 1
                    exists = self._mastodon_status_exists(account_name, status_id)

                    if exists is None:
                        # Outage / unknown — never advance toward suppression.
                        continue
                    if exists:
                        # Resurrect: clear any accumulated dead state.
                        if any(k in entry for k in ("deleted", "dead_strikes", "first_seen_dead")):
                            entry.pop("deleted", None)
                            entry.pop("dead_strikes", None)
                            entry.pop("first_seen_dead", None)
                            account_changed = True
                        continue

                    # Confirmed 404 — record a strike.
                    strikes = int(entry.get("dead_strikes", 0)) + 1
                    entry["dead_strikes"] = strikes
                    entry.setdefault("first_seen_dead", self._now_isoformat())
                    account_changed = True
                    if strikes >= self.dead_link_confirm_threshold:
                        entry["deleted"] = True
                    else:
                        stats["pending_strikes"] += 1

                if account_changed:
                    mapping_changed = True

                now_deleted = self._is_account_deleted(account_data)
                if now_deleted and not was_deleted:
                    self._suppress_account_in_interaction_data(ghost_post_id, account_name)
                    stats["newly_suppressed"] += 1
                    logger.warning(
                        f"Suppressed dead Mastodon link for post {ghost_post_id} "
                        f"account '{account_name}' (confirmed 404)"
                    )
                elif was_deleted and not now_deleted:
                    self._restore_account_in_interaction_data(
                        ghost_post_id, account_name, account_data
                    )
                    stats["resurrected"] += 1
                    logger.info(
                        f"Restored Mastodon link for post {ghost_post_id} "
                        f"account '{account_name}' (status reachable again)"
                    )

            if mapping_changed:
                self.data_store.put_syndication_mapping(ghost_post_id, mapping)

        logger.info(
            f"Dead-link sweep complete: checked={stats['checked']}, "
            f"newly_suppressed={stats['newly_suppressed']}, "
            f"resurrected={stats['resurrected']}, "
            f"pending_strikes={stats['pending_strikes']}"
        )
        return stats

    def _suppress_account_in_interaction_data(self, ghost_post_id: str, account_name: str) -> None:
        """Remove a Mastodon account from stored interaction data so the widget hides it."""
        data = self.data_store.get(ghost_post_id)
        if not data:
            return
        before = (
            account_name in data.get("syndication_links", {}).get("mastodon", {})
            or account_name in data.get("platforms", {}).get("mastodon", {})
        )
        self._drop_account(data, "mastodon", account_name)
        if before:
            data["updated_at"] = self._now_isoformat()
            self.data_store.put(ghost_post_id, data)

    def _restore_account_in_interaction_data(
        self, ghost_post_id: str, account_name: str, account_data: Any
    ) -> None:
        """Restore a Mastodon syndication link after a status becomes reachable again.

        Only the syndication link is restored here; interaction counts (favourites,
        reblogs, replies) refill on the next regular sync.
        """
        post_url = self._featured_post_url(account_data)
        if not post_url:
            return
        data = self.data_store.get(ghost_post_id) or self._empty_interaction_data(ghost_post_id)
        links = data.setdefault("syndication_links", {"mastodon": {}, "bluesky": {}})
        links.setdefault("mastodon", {})[account_name] = {"post_url": post_url}
        data["updated_at"] = self._now_isoformat()
        self.data_store.put(ghost_post_id, data)

    def _load_syndication_mapping(self, ghost_post_id: str) -> Optional[Dict[str, Any]]:
        """
        Load syndication mapping for a Ghost post.

        Args:
            ghost_post_id: Ghost post ID

        Returns:
            Mapping dictionary or None if not found
        """
        return self.data_store.get_syndication_mapping(ghost_post_id)

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
        data = self.data_store.get(ghost_post_id)
        if data is None:
            return self._empty_interaction_data(ghost_post_id)
        return data

    def _store_interaction_data(self, ghost_post_id: str, data: Dict[str, Any]) -> None:
        """
        Store interaction data in SQLite.

        Args:
            ghost_post_id: Ghost post ID
            data: Interaction data to store
        """
        self.data_store.put(ghost_post_id, data)
        logger.debug(f"Stored interaction data in SQLite for {ghost_post_id}")

    def get_stored_interaction_data(self, ghost_post_id: str) -> Optional[Dict[str, Any]]:
        """Return stored interaction data for a post, if available."""
        return self.data_store.get(ghost_post_id)

    def _empty_interaction_data(self, ghost_post_id: str) -> Dict[str, Any]:
        """Return empty interaction data structure."""
        return {
            "ghost_post_id": ghost_post_id,
            "updated_at": self._now_isoformat(),
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
        any that link back to the specified Ghost post. If found, it stores
        syndication mappings in SQLite for future use.

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

        # Search Mastodon posts - wrapped in try-catch to ensure Bluesky discovery
        # continues even if Mastodon processing fails unexpectedly
        try:
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
                                    storage_path=self.storage_path,
                                    timezone_name=self.timezone_name,
                                )

                                mapping_found = True
                                break  # Found mapping for this account, move to next

                except Exception as e:
                    logger.error(
                        f"Error searching Mastodon posts from '{client.account_name}': {e}",
                        exc_info=True
                    )
        except Exception as e:
            logger.error(f"Unexpected error during Mastodon discovery: {e}", exc_info=True)

        # Search Bluesky posts - wrapped in try-catch to ensure one platform's failure
        # doesn't affect the other
        try:
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
                                    storage_path=self.storage_path,
                                    timezone_name=self.timezone_name,
                                )

                                mapping_found = True
                                break  # Found mapping for this account, move to next

                except Exception as e:
                    logger.error(
                        f"Error searching Bluesky posts from '{client.account_name}': {e}",
                        exc_info=True
                    )
        except Exception as e:
            logger.error(f"Unexpected error during Bluesky discovery: {e}", exc_info=True)

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
        # Remove HTML tags
        text = re.sub(r'<[^>]+>', '', html_content)
        # Decode HTML entities
        text = text.replace('&lt;', '<').replace('&gt;', '>').replace('&amp;', '&')
        text = text.replace('&quot;', '"').replace('&#39;', "'")
        return text.strip()


def update_interaction_data_on_syndication(
    ghost_post_id: str,
    platform: str,
    account_name: str,
    post_url: str,
    split_info: Optional[Dict[str, Any]] = None,
    storage_path: str = "./data",
    timezone_name: str = "UTC",
) -> None:
    """
    Update interaction_data table with syndication links immediately after syndication.

    This ensures the interaction_data table reflects the syndication link right
    away rather than waiting for the next periodic interaction sync.

    For split posts, only the post at split_index 0 is used as the interaction
    link because that post contains the featured image.  Posts at other split
    indices are ignored so the canonical link always points to the featured image.

    Args:
        ghost_post_id: Ghost post ID
        platform: Platform name ("mastodon" or "bluesky")
        account_name: Account name on the platform
        post_url: URL of the syndicated post
        split_info: Optional split post metadata dict (keys: is_split, split_index,
            total_splits, image_url).  When present and is_split is True, only
            split_index == 0 triggers an update.
        storage_path: Directory path for SQLite interaction storage
        timezone_name: IANA timezone name used for generated timestamps
    """
    # For split posts, only update on the featured image post (split_index 0)
    if split_info and split_info.get("is_split") and split_info.get("split_index", 0) != 0:
        return

    if not post_url:
        logger.warning(
            f"Skipping interaction_data update for {ghost_post_id}/{platform}/{account_name}: "
            f"no post_url available"
        )
        return

    data_store = InteractionDataStore(storage_path)
    tz_name = InteractionSyncService._normalize_timezone_name(timezone_name)
    now = datetime.now(ZoneInfo(tz_name)).isoformat()

    existing = data_store.get(ghost_post_id)
    if existing is None:
        existing = {
            "ghost_post_id": ghost_post_id,
            "updated_at": now,
            "syndication_links": {"mastodon": {}, "bluesky": {}},
            "platforms": {"mastodon": {}, "bluesky": {}},
        }

    existing["updated_at"] = now

    # Ensure structure is intact after loading (defensive, in case of partial data)
    if not isinstance(existing.get("syndication_links"), dict):
        existing["syndication_links"] = {"mastodon": {}, "bluesky": {}}
    for p in ("mastodon", "bluesky"):
        if p not in existing["syndication_links"]:
            existing["syndication_links"][p] = {}

    existing["syndication_links"][platform][account_name] = {"post_url": post_url}

    data_store.put(ghost_post_id, existing)
    logger.info(
        f"Updated interaction_data syndication_links for {ghost_post_id} "
        f"{platform}/{account_name}: {post_url}"
    )


def store_syndication_mapping(
    ghost_post_id: str,
    ghost_post_url: str,
    platform: str,
    account_name: str,
    post_data: Dict[str, Any],
    storage_path: str = "./data",
    split_info: Optional[Dict[str, Any]] = None,
    timezone_name: str = "UTC",
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
        storage_path: Directory path for SQLite interaction storage
        split_info: Optional split post metadata:
            - is_split: True if this is part of a split post
            - split_index: Index of this post in the split (0-based)
            - total_splits: Total number of split posts
            - image_url: URL of the image for this split
        timezone_name: IANA timezone name used for generated timestamps

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
    data_store = InteractionDataStore(storage_path)

    # Load existing mapping from SQLite
    mapping = data_store.get_syndication_mapping(ghost_post_id)

    if mapping is None:
        tz_name = InteractionSyncService._normalize_timezone_name(timezone_name)
        mapping = {
            "ghost_post_id": ghost_post_id,
            "ghost_post_url": ghost_post_url,
            "syndicated_at": datetime.now(ZoneInfo(tz_name)).isoformat(),
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
            f"to SQLite"
        )
    else:
        # Non-split post - store as single entry (original behavior)
        mapping["platforms"][platform][account_name] = post_data

        logger.info(f"Stored syndication mapping for {platform}/{account_name} to SQLite")

    # Normalize platform keys before persisting
    platforms = mapping.get("platforms", {})
    mapping["platforms"] = {
        "mastodon": platforms.get("mastodon", {}),
        "bluesky": platforms.get("bluesky", {}),
    }

    # Save mapping to SQLite
    data_store.put_syndication_mapping(ghost_post_id, mapping)

    # Immediately update interaction_data so the syndication link is visible
    # without waiting for the next periodic sync.
    update_interaction_data_on_syndication(
        ghost_post_id=ghost_post_id,
        platform=platform,
        account_name=account_name,
        post_url=post_data.get("post_url", ""),
        split_info=split_info,
        storage_path=storage_path,
        timezone_name=timezone_name,
    )
