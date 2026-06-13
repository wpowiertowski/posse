"""Manual dead-link sweep for POSSE.

Scans every syndication mapping for deleted Mastodon posts and suppresses the dead
links (flagging them ``deleted: true`` while retaining the record). This is the
on-demand counterpart to the scheduler's periodic sweep — useful for an immediate
cleanup without waiting for / restarting the running service.

Run inside the container:

    docker compose exec ghost-posse poetry run python -m posse.prune_dead_links

Outage-safe: only definitive HTTP 404s (confirmed across the configured strike
threshold) suppress a link; timeouts/5xx/network errors never do.
"""
import logging
import sys

from config import load_config, get_timezone_name
from social.mastodon_client import MastodonClient
from interactions.interaction_sync import InteractionSyncService

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("posse.prune_dead_links")


def main() -> int:
    config = load_config()
    timezone_name = get_timezone_name(config)

    interactions_config = config.get("interactions", {})
    storage_path = interactions_config.get("cache_directory", "./data")
    dead_link_confirm_threshold = interactions_config.get("dead_link_confirm_threshold", 2)
    dead_link_recheck_days = interactions_config.get("dead_link_recheck_days", 7)

    mastodon_clients = MastodonClient.from_config(config)
    enabled = [c for c in mastodon_clients if c.enabled]
    if not enabled:
        logger.error("No enabled Mastodon clients configured; nothing to check.")
        return 1
    logger.info(f"Checking dead links with {len(enabled)} enabled Mastodon client(s)")

    service = InteractionSyncService(
        mastodon_clients=mastodon_clients,
        storage_path=storage_path,
        timezone_name=timezone_name,
        dead_link_confirm_threshold=dead_link_confirm_threshold,
        dead_link_recheck_days=dead_link_recheck_days,
    )

    stats = service.prune_dead_links()
    logger.info(
        "Dead-link sweep finished: "
        f"checked={stats['checked']}, newly_suppressed={stats['newly_suppressed']}, "
        f"resurrected={stats['resurrected']}, pending_strikes={stats['pending_strikes']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
