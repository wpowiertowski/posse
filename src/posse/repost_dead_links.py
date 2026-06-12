"""Repost dead Mastodon syndications for POSSE.

Re-syndicates blog posts whose Mastodon syndication was deleted server-side (e.g. by
Mastodon auto-delete) and flagged ``deleted: true`` by the dead-link sweep
(``posse.prune_dead_links`` / the scheduler). Reuses the normal syndication path so the
reposts are formatted identically to live posts.

Prerequisite: turn OFF Mastodon auto-delete first, otherwise the reposts get deleted
again. See REPOST_PLAN.md.

Run inside the container:

    # Preview what would be reposted (no posting):
    docker compose exec ghost-posse poetry run python -m posse.repost_dead_links --dry-run

    # Repost the 10 most recent dead posts, 5s apart:
    docker compose exec ghost-posse poetry run python -m posse.repost_dead_links --limit 10 --delay 5

    # Only a specific account:
    docker compose exec ghost-posse poetry run python -m posse.repost_dead_links --account personal

For each reposted entry, a successful post overwrites the dead mapping entry with the new
``status_id``/``post_url`` (clearing the ``deleted`` flag) and refreshes the interaction
data so the widget immediately shows the new live link.
"""
import argparse
import logging
import sys
import time
from typing import Any, Dict, List, Optional

from config import load_config, get_timezone_name
from social.mastodon_client import MastodonClient
from ghost.ghost_api import GhostContentAPIClient
from interactions.storage import InteractionDataStore
from interactions.interaction_sync import InteractionSyncService, store_syndication_mapping
from posse.posse import _extract_post_data, _format_post_content

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("posse.repost_dead_links")


def _build_worklist(
    store: InteractionDataStore,
    account_filter: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Collect dead Mastodon mapping entries to repost, newest syndication first."""
    worklist: List[Dict[str, Any]] = []
    for mapping in store.list_syndication_mappings():
        ghost_post_id = str(mapping.get("ghost_post_id", ""))
        ghost_post_url = mapping.get("ghost_post_url", "")
        if not ghost_post_id:
            continue
        mastodon_accounts = mapping.get("platforms", {}).get("mastodon", {})
        for account_name, entry in mastodon_accounts.items():
            if account_filter and account_name != account_filter:
                continue
            if not InteractionSyncService._is_account_deleted(entry):
                continue
            worklist.append({
                "ghost_post_id": ghost_post_id,
                "ghost_post_url": ghost_post_url,
                "syndicated_at": mapping.get("syndicated_at", ""),
                "account_name": account_name,
            })
    # Newest syndication first so --limit takes the most recent posts.
    worklist.sort(key=lambda w: w.get("syndicated_at", ""), reverse=True)
    return worklist


def _repost_one(
    item: Dict[str, Any],
    ghost_api: GhostContentAPIClient,
    clients_by_name: Dict[str, MastodonClient],
    storage_path: str,
    timezone_name: str,
) -> bool:
    """Repost a single dead entry. Returns True on success."""
    ghost_post_id = item["ghost_post_id"]
    account_name = item["account_name"]

    client = clients_by_name.get(account_name)
    if not client or not client.enabled or not client.api:
        logger.warning(f"Skipping {ghost_post_id}: Mastodon account '{account_name}' not available")
        return False

    post = ghost_api.get_post_by_id(ghost_post_id, include=["tags"])
    if not post:
        logger.warning(f"Skipping {ghost_post_id}: post not found via Ghost API (deleted?)")
        return False

    title, url, excerpt, images, media_descriptions, tags = _extract_post_data(post)
    if not url:
        logger.warning(f"Skipping {ghost_post_id}: Ghost post has no URL")
        return False

    content = _format_post_content(title, url, excerpt, tags, client.max_post_length, ref="mastodon")
    result = client.post(
        content=content,
        media_urls=images if images else None,
        media_descriptions=media_descriptions if media_descriptions else None,
    )
    if not isinstance(result, dict) or not result.get("id"):
        logger.error(f"Repost failed for {ghost_post_id} on '{account_name}'")
        return False

    store_syndication_mapping(
        ghost_post_id=ghost_post_id,
        ghost_post_url=url,
        platform="mastodon",
        account_name=account_name,
        post_data={"status_id": str(result["id"]), "post_url": result.get("url", "")},
        storage_path=storage_path,
        timezone_name=timezone_name,
    )
    logger.info(f"Reposted {ghost_post_id} to '{account_name}': {result.get('url', '')}")
    return True


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Repost dead Mastodon syndications.")
    parser.add_argument("--dry-run", action="store_true",
                        help="List what would be reposted without posting.")
    parser.add_argument("--limit", type=int, default=None,
                        help="Maximum number of posts to repost (newest first).")
    parser.add_argument("--account", default=None,
                        help="Only repost entries for this Mastodon account name.")
    parser.add_argument("--delay", type=float, default=5.0,
                        help="Seconds to wait between reposts (default: 5).")
    args = parser.parse_args(argv)

    config = load_config()
    timezone_name = get_timezone_name(config)
    interactions_config = config.get("interactions", {})
    storage_path = interactions_config.get("cache_directory", "./data")

    store = InteractionDataStore(storage_path)
    worklist = _build_worklist(store, account_filter=args.account)
    if args.limit is not None:
        worklist = worklist[:args.limit]

    if not worklist:
        logger.info("No dead Mastodon syndications to repost. "
                    "Run `python -m posse.prune_dead_links` first if you expect some.")
        return 0

    logger.info(f"{len(worklist)} dead syndication(s) selected for repost:")
    for item in worklist:
        logger.info(f"  - {item['ghost_post_id']} -> {item['account_name']} "
                    f"({item['ghost_post_url']})")

    if args.dry_run:
        logger.info("Dry run: nothing was posted.")
        return 0

    ghost_api = GhostContentAPIClient.from_config(config)
    if not ghost_api.enabled:
        logger.error("Ghost Content API is not configured; cannot fetch posts to repost.")
        return 1

    clients_by_name = {c.account_name: c for c in MastodonClient.from_config(config)}
    if not any(c.enabled for c in clients_by_name.values()):
        logger.error("No enabled Mastodon clients configured.")
        return 1

    succeeded = 0
    failed = 0
    for index, item in enumerate(worklist):
        try:
            if _repost_one(item, ghost_api, clients_by_name, storage_path, timezone_name):
                succeeded += 1
            else:
                failed += 1
        except Exception as e:
            failed += 1
            logger.error(f"Error reposting {item['ghost_post_id']}: {e}", exc_info=True)

        # Throttle between actual posts (not after the last one).
        if args.delay > 0 and index < len(worklist) - 1:
            time.sleep(args.delay)

    logger.info(f"Repost complete: succeeded={succeeded}, failed={failed}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
