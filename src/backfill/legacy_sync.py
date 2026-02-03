"""
Legacy Post Syndication Backfill.

This module provides functionality to backfill syndication mappings for posts
that were syndicated before the tracking system was implemented.

It searches through Mastodon and Bluesky accounts for posts containing links
to the Ghost blog and creates syndication mapping files.

Usage:
    Run as a Flask endpoint:
        curl -X POST http://localhost:5000/api/backfill/sync?ghost_url=https://yourblog.com

    Or import and use directly:
        >>> from backfill.legacy_sync import LegacyBackfillService
        >>> service = LegacyBackfillService(mastodon_clients, bluesky_clients, "https://blog.com")
        >>> results = service.backfill_all()
"""

import json
import logging
import os
import re
from datetime import datetime
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)


class LegacyBackfillService:
    """Service to backfill syndication mappings for legacy posts."""

    def __init__(
        self,
        mastodon_clients: List[Any],
        bluesky_clients: List[Any],
        ghost_url: str,
        mappings_path: str = "./data/syndication_mappings",
        max_posts_per_account: int = 200
    ):
        """Initialize the backfill service.

        Args:
            mastodon_clients: List of MastodonClient instances
            bluesky_clients: List of BlueskyClient instances
            ghost_url: Base URL of the Ghost blog (e.g., https://yourblog.com)
            mappings_path: Directory for syndication mapping files
            max_posts_per_account: Maximum posts to fetch per account
        """
        self.mastodon_clients = [c for c in mastodon_clients if c.enabled]
        self.bluesky_clients = [c for c in bluesky_clients if c.enabled]
        self.ghost_url = ghost_url.rstrip('/')
        self.mappings_path = mappings_path
        self.max_posts_per_account = max_posts_per_account

        os.makedirs(self.mappings_path, mode=0o755, exist_ok=True)
        logger.info(
            f"LegacyBackfillService initialized with {len(self.mastodon_clients)} "
            f"Mastodon and {len(self.bluesky_clients)} Bluesky clients"
        )

    def backfill_all(self) -> Dict[str, Any]:
        """Run backfill for all configured accounts.

        Returns:
            Dictionary with backfill results per platform and account
        """
        results = {
            "ghost_url": self.ghost_url,
            "started_at": datetime.now(ZoneInfo("UTC")).isoformat(),
            "mastodon": {},
            "bluesky": {},
            "total_mappings_created": 0
        }

        # Process Mastodon accounts
        for client in self.mastodon_clients:
            try:
                account_results = self._backfill_mastodon(client)
                results["mastodon"][client.account_name] = account_results
                results["total_mappings_created"] += account_results["mappings_created"]
            except Exception as e:
                logger.error(f"Failed to backfill Mastodon account {client.account_name}: {e}")
                results["mastodon"][client.account_name] = {"error": str(e)}

        # Process Bluesky accounts
        for client in self.bluesky_clients:
            try:
                account_results = self._backfill_bluesky(client)
                results["bluesky"][client.account_name] = account_results
                results["total_mappings_created"] += account_results["mappings_created"]
            except Exception as e:
                logger.error(f"Failed to backfill Bluesky account {client.account_name}: {e}")
                results["bluesky"][client.account_name] = {"error": str(e)}

        results["completed_at"] = datetime.now(ZoneInfo("UTC")).isoformat()
        return results

    def _backfill_mastodon(self, client: Any) -> Dict[str, Any]:
        """Backfill syndication mappings for a Mastodon account.

        Args:
            client: MastodonClient instance

        Returns:
            Dictionary with backfill results
        """
        logger.info(f"Backfilling Mastodon account: {client.account_name}")

        results = {
            "posts_scanned": 0,
            "posts_matched": 0,
            "mappings_created": 0,
            "mappings_updated": 0,
            "matched_posts": []
        }

        # Get account ID
        account = client.api.account_verify_credentials()
        account_id = account["id"]

        # Fetch statuses with pagination
        statuses = []
        max_id = None

        while len(statuses) < self.max_posts_per_account:
            batch = client.api.account_statuses(
                account_id,
                limit=40,
                max_id=max_id,
                exclude_reblogs=True
            )
            if not batch:
                break
            statuses.extend(batch)
            max_id = batch[-1]["id"]

        results["posts_scanned"] = len(statuses)
        logger.info(f"Scanned {len(statuses)} Mastodon posts for {client.account_name}")

        # Find posts with Ghost URLs
        for status in statuses:
            ghost_post_url = self._extract_ghost_url(status.get("content", ""))
            if ghost_post_url:
                results["posts_matched"] += 1
                ghost_post_id = self._extract_ghost_post_id(ghost_post_url)

                if ghost_post_id:
                    created, updated = self._store_mapping(
                        ghost_post_id=ghost_post_id,
                        ghost_post_url=ghost_post_url,
                        platform="mastodon",
                        account_name=client.account_name,
                        post_data={
                            "status_id": str(status["id"]),
                            "post_url": status["url"]
                        },
                        syndicated_at=status.get("created_at")
                    )
                    if created:
                        results["mappings_created"] += 1
                    if updated:
                        results["mappings_updated"] += 1

                    results["matched_posts"].append({
                        "ghost_url": ghost_post_url,
                        "social_url": status["url"],
                        "created_at": status.get("created_at")
                    })

        return results

    def _backfill_bluesky(self, client: Any) -> Dict[str, Any]:
        """Backfill syndication mappings for a Bluesky account.

        Args:
            client: BlueskyClient instance

        Returns:
            Dictionary with backfill results
        """
        logger.info(f"Backfilling Bluesky account: {client.account_name}")

        results = {
            "posts_scanned": 0,
            "posts_matched": 0,
            "mappings_created": 0,
            "mappings_updated": 0,
            "matched_posts": []
        }

        # Fetch posts with pagination
        posts = []
        cursor = None

        while len(posts) < self.max_posts_per_account:
            response = client.api.get_author_feed(
                actor=client.handle,
                limit=50,
                cursor=cursor
            )
            feed = response.feed if hasattr(response, 'feed') else []
            if not feed:
                break

            # Filter to only include original posts (not reposts)
            for item in feed:
                post = item.post if hasattr(item, 'post') else item
                # Skip reposts
                if hasattr(item, 'reason') and item.reason:
                    continue
                posts.append(post)

            cursor = response.cursor if hasattr(response, 'cursor') else None
            if not cursor:
                break

        results["posts_scanned"] = len(posts)
        logger.info(f"Scanned {len(posts)} Bluesky posts for {client.account_name}")

        # Find posts with Ghost URLs
        for post in posts:
            # Get text content from the post record
            record = post.record if hasattr(post, 'record') else {}
            text = record.text if hasattr(record, 'text') else ""

            # Also check facets for link URLs
            facets = record.facets if hasattr(record, 'facets') else []
            urls_in_facets = []
            for facet in facets or []:
                for feature in facet.features or []:
                    if hasattr(feature, 'uri'):
                        urls_in_facets.append(feature.uri)

            # Search in text and facet URLs
            ghost_post_url = self._extract_ghost_url(text)
            if not ghost_post_url:
                for url in urls_in_facets:
                    if self.ghost_url in url:
                        ghost_post_url = url
                        break

            if ghost_post_url:
                results["posts_matched"] += 1
                ghost_post_id = self._extract_ghost_post_id(ghost_post_url)

                if ghost_post_id:
                    # Build Bluesky post URL
                    uri = post.uri if hasattr(post, 'uri') else ""
                    # Extract rkey from at:// URI
                    rkey = uri.split('/')[-1] if uri else ""
                    post_url = f"https://bsky.app/profile/{client.handle}/post/{rkey}"

                    created_at = None
                    if hasattr(record, 'created_at'):
                        created_at = record.created_at
                    elif hasattr(record, 'createdAt'):
                        created_at = record.createdAt

                    created, updated = self._store_mapping(
                        ghost_post_id=ghost_post_id,
                        ghost_post_url=ghost_post_url,
                        platform="bluesky",
                        account_name=client.account_name,
                        post_data={
                            "post_uri": uri,
                            "post_url": post_url
                        },
                        syndicated_at=created_at
                    )
                    if created:
                        results["mappings_created"] += 1
                    if updated:
                        results["mappings_updated"] += 1

                    results["matched_posts"].append({
                        "ghost_url": ghost_post_url,
                        "social_url": post_url,
                        "created_at": created_at
                    })

        return results

    def _extract_ghost_url(self, content: str) -> Optional[str]:
        """Extract Ghost blog URL from post content.

        Args:
            content: Post content (may contain HTML)

        Returns:
            Ghost post URL if found, None otherwise
        """
        # Remove HTML tags
        text = re.sub(r'<[^>]+>', ' ', content)

        # Pattern to match Ghost URLs
        # Matches: https://yourblog.com/post-slug/ or https://yourblog.com/post-slug
        pattern = rf'{re.escape(self.ghost_url)}/[\w\-]+/?'

        match = re.search(pattern, text)
        if match:
            url = match.group(0)
            # Normalize URL (ensure trailing slash)
            if not url.endswith('/'):
                url += '/'
            return url

        return None

    def _extract_ghost_post_id(self, ghost_url: str) -> Optional[str]:
        """Extract or generate a post ID from Ghost URL.

        Since we don't have the Ghost post ID, we use the URL slug as identifier.
        This creates a deterministic ID that can be matched later.

        Args:
            ghost_url: Full Ghost post URL

        Returns:
            Post identifier (URL slug hash or slug itself)
        """
        # Extract slug from URL
        # https://blog.com/my-post-slug/ -> my-post-slug
        path = ghost_url.replace(self.ghost_url, '').strip('/')

        if not path:
            return None

        # Use slug as the identifier (simple and readable)
        # For proper Ghost integration, you'd want to query Ghost API
        return f"legacy-{path}"

    def _store_mapping(
        self,
        ghost_post_id: str,
        ghost_post_url: str,
        platform: str,
        account_name: str,
        post_data: Dict[str, Any],
        syndicated_at: Optional[str] = None
    ) -> tuple[bool, bool]:
        """Store syndication mapping to file.

        Args:
            ghost_post_id: Ghost post identifier
            ghost_post_url: Full Ghost post URL
            platform: Platform name (mastodon/bluesky)
            account_name: Account name
            post_data: Platform-specific post data
            syndicated_at: Original syndication timestamp

        Returns:
            Tuple of (created, updated) booleans
        """
        mapping_file = os.path.join(self.mappings_path, f"{ghost_post_id}.json")
        created = False
        updated = False

        # Load existing or create new
        if os.path.exists(mapping_file):
            with open(mapping_file, 'r') as f:
                mapping = json.load(f)
        else:
            created = True
            mapping = {
                "ghost_post_id": ghost_post_id,
                "ghost_post_url": ghost_post_url,
                "syndicated_at": syndicated_at or datetime.now(ZoneInfo("UTC")).isoformat(),
                "platforms": {}
            }

        # Ensure platform exists
        if platform not in mapping["platforms"]:
            mapping["platforms"][platform] = {}

        # Check if this account already has an entry
        if account_name not in mapping["platforms"][platform]:
            mapping["platforms"][platform][account_name] = post_data
            updated = True
            logger.info(f"Added {platform}/{account_name} mapping for {ghost_post_id}")
        else:
            logger.debug(f"Mapping already exists for {platform}/{account_name}/{ghost_post_id}")

        # Save mapping
        with open(mapping_file, 'w') as f:
            json.dump(mapping, f, indent=2)

        return created, updated


def create_backfill_blueprint(
    mastodon_clients: List[Any],
    bluesky_clients: List[Any],
    mappings_path: str = "./data/syndication_mappings"
):
    """Create Flask blueprint for backfill endpoints.

    Args:
        mastodon_clients: List of MastodonClient instances
        bluesky_clients: List of BlueskyClient instances
        mappings_path: Directory for syndication mapping files

    Returns:
        Flask Blueprint with backfill endpoints
    """
    from flask import Blueprint, jsonify, request

    bp = Blueprint('backfill', __name__, url_prefix='/api/backfill')

    @bp.route('/sync', methods=['POST'])
    def trigger_backfill():
        """Trigger legacy post backfill.

        Query Parameters:
            ghost_url: Required. Base URL of Ghost blog (e.g., https://yourblog.com)
            max_posts: Optional. Max posts to scan per account (default: 200)

        Returns:
            JSON with backfill results

        Example:
            curl -X POST "http://localhost:5000/api/backfill/sync?ghost_url=https://yourblog.com"
        """
        ghost_url = request.args.get('ghost_url')
        if not ghost_url:
            return jsonify({"error": "ghost_url parameter is required"}), 400

        max_posts = request.args.get('max_posts', 200, type=int)

        service = LegacyBackfillService(
            mastodon_clients=mastodon_clients,
            bluesky_clients=bluesky_clients,
            ghost_url=ghost_url,
            mappings_path=mappings_path,
            max_posts_per_account=max_posts
        )

        results = service.backfill_all()
        return jsonify(results)

    @bp.route('/status', methods=['GET'])
    def backfill_status():
        """Get current syndication mappings status.

        Returns:
            JSON with count and list of existing mappings
        """
        mappings = []
        if os.path.exists(mappings_path):
            for filename in os.listdir(mappings_path):
                if filename.endswith('.json'):
                    filepath = os.path.join(mappings_path, filename)
                    with open(filepath, 'r') as f:
                        mapping = json.load(f)
                        mappings.append({
                            "ghost_post_id": mapping.get("ghost_post_id"),
                            "ghost_post_url": mapping.get("ghost_post_url"),
                            "platforms": list(mapping.get("platforms", {}).keys())
                        })

        return jsonify({
            "total_mappings": len(mappings),
            "mappings": mappings
        })

    return bp
