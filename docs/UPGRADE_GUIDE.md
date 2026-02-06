# Upgrade Guide

This guide summarizes high-impact changes introduced after `v1.1.0` and what operators should verify during upgrades.

## Highlights since v1.1.0

- Interaction payload storage migrated from JSON files to **SQLite** (`data/interactions/interactions.db`).
- New one-time migration script: `scripts/migrate_interactions_to_sqlite.py`.
- Interactions API security hardening:
  - referrer allow-list validation
  - per-IP rate limiting
  - global discovery rate limiting
  - per-post discovery cooldown
- Internal token comparison hardened using constant-time checks.
- Bluesky posting improvements:
  - re-authentication before syndication
  - image compression for blob size limits
- Post update webhook support for catch-up syndication workflows.

## Required operator actions

### 1) Migrate interaction data to SQLite

Run once in your deployment environment:

```bash
python scripts/migrate_interactions_to_sqlite.py --storage-path ./data/interactions
```

Optional dry run:

```bash
python scripts/migrate_interactions_to_sqlite.py --storage-path ./data/interactions --dry-run
```

### 2) Review `config.yml` security settings

Ensure you explicitly configure:

- `security.allowed_referrers`
- `security.rate_limit_enabled`
- `security.discovery_rate_limit_enabled`
- `security.internal_api_token` or `security.internal_api_token_file`

Use `config.example.yml` as the reference.

### 3) Confirm webhook events in Ghost

For best behavior, configure both:

- `post.published`
- `post.edited`

This allows new publication syndication and catch-up sync after edits.

### 4) Validate reverse proxy setup for interactions API

If exposing `/api/interactions/<post_id>`, ensure your proxy forwards real client IP and restricts origins/methods as documented in `docs/SECURITY_HARDENING.md`.

## Post-upgrade verification checklist

- Service starts cleanly and loads config.
- Existing interaction records are returned via `/api/interactions/<post_id>`.
- `/sync` access is denied without valid internal token (if configured).
- Widget still renders interaction stats for known syndicated posts.

## Rollback note

If rollback is required, keep your pre-migration interaction JSON backups. SQLite migration is additive/idempotent but code-level rollback may expect previous behavior.
