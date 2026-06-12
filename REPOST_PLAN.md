# Reposting dead Mastodon syndications — plan

## Background

Mastodon's auto-delete removed most older mastodon.social syndications. Pixelfed and
Bluesky are unaffected. POSSE now **detects** these dead links during periodic updates
and suppresses them from the social-interactions widget (see the dead-link sweep:
`InteractionSyncService.prune_dead_links()` and `src/posse/prune_dead_links.py`), while
**keeping the mapping record** — each dead entry is flagged `deleted: true` but retains
its `ghost_post_id`, `ghost_post_url`, old `status_id` and `post_url`.

This document is the plan for the *next* step: re-syndicating (reposting) the dead posts
to Mastodon so the widget shows live links again. **Implementing the repost tooling is a
deliberate follow-up — this is the plan only.**

## Prerequisite (do this first)

**Turn OFF Mastodon auto-delete** in your mastodon.social account settings
(Preferences → Automated post deletion). If it is still on, anything reposted will be
auto-deleted again and this effort is wasted. (Confirmed disabled per the project
decision.)

## Step 1 — Let the sweep build the worklist

Run the dead-link sweep so every gone post is flagged:

```bash
docker compose exec ghost-posse poetry run python -m posse.prune_dead_links
```

(or just restart the container — the scheduler runs a sweep at startup and every
`dead_link_sweep_interval_hours`.)

Then read the worklist straight from SQLite (`<cache_directory>/interactions.db`,
`syndication_mappings` table). Each row's JSON `payload` lists
`platforms.mastodon.<account>` entries; the ones to repost are those with
`"deleted": true`. The retained `ghost_post_id` / `ghost_post_url` identify exactly which
blog post to re-syndicate to which account.

> A confirmed-dead entry only appears after the 404 is seen across
> `dead_link_confirm_threshold` sweeps (default 2), so the worklist excludes transient
> outages by construction.

## Step 2 — Repost mechanics (reuse existing code)

For each dead entry, re-create the Mastodon post using the **existing** syndication path
rather than new bespoke logic:

1. Fetch the Ghost post (title, url, excerpt, tags, feature image) via the Ghost Content
   API client (`GHOST_API_CLIENT`) using the stored `ghost_post_id` / `ghost_post_url`.
2. Format the status with `_format_post_content(title, url, excerpt, tags,
   client.max_post_length, ref="mastodon")` — see
   [posse.py:590](src/posse/posse.py#L590). This preserves the `?ref=mastodon`
   analytics tagging.
3. Post with `MastodonClient.post(content, media_urls=..., media_descriptions=...)`
   ([mastodon_client.py:142](src/social/mastodon_client.py#L142)).
4. On success, call `store_syndication_mapping(ghost_post_id, ghost_post_url,
   "mastodon", account_name, {"status_id": new_id, "post_url": new_url}, ...)`
   ([interaction_sync.py:1108](src/interactions/interaction_sync.py#L1108)). This
   **overwrites the dead entry** (clearing the `deleted`/`dead_strikes` state) and
   refreshes `interaction_data` so the widget immediately shows the new live link.

Because `store_syndication_mapping` already updates `interaction_data` via
`update_interaction_data_on_syndication`, no extra widget plumbing is needed.

## Step 3 — Selection & throttling

- **Dry-run first:** list what *would* be reposted (post title, account, old URL) without
  posting. Verify the list looks right.
- **Batch & rate-limit:** repost in small batches (e.g. newest N first, or only posts
  above a traffic threshold) with a delay between posts (a few seconds) to stay within
  Mastodon rate limits. Posting all historical posts at once would both hit limits and
  flood your followers' timelines.
- **Idempotency:** reposting is keyed by `(ghost_post_id, account)`. Once an entry is
  overwritten with a live `status_id`, it drops off the worklist, so re-running the tool
  is safe.

## Caveats

- Reposts are **new** Mastodon posts with new URLs and current timestamps. The original
  favourites / boosts / replies on the deleted posts are **not recoverable**.
- The Ghost post's own `published_at` is unchanged; only the Mastodon side is new.
- Reposting surfaces old content at the top of your Mastodon timeline — pace it
  accordingly, and consider whether very old/low-value posts are worth reposting at all.

## Recommended rollout

1. Disable Mastodon auto-delete.
2. Run the sweep (`python -m posse.prune_dead_links`) → dead links flagged & suppressed.
3. Inspect the worklist (mappings with `deleted: true`).
4. Run the (future) repost tool in **dry-run**; sanity-check the list.
5. Repost in small batches; watch logs / rate limits.
6. Reload a few blog posts → confirm fresh Mastodon links appear in the interactions box.

## Implementation note (follow-up)

A repost command would live alongside `src/posse/prune_dead_links.py` (e.g.
`src/posse/repost_dead_links.py`), reusing `GhostContentAPIClient`, `_format_post_content`,
`MastodonClient.post`, and `store_syndication_mapping`. It should support `--dry-run`,
`--limit`, `--account`, and an inter-post delay.
