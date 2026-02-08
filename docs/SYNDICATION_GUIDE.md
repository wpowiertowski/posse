# Syndication Guide

## Overview

POSSE receives Ghost webhooks and syndicates published posts to configured Mastodon and Bluesky accounts. This guide covers account routing, media behavior, and catch-up syndication for missed accounts.

## 1. Configure Platform Accounts

Add one or more accounts per platform in `config.yml`.

```yaml
timezone: "UTC"

mastodon:
  accounts:
    - name: "personal"
      instance_url: "https://mastodon.social"
      access_token_file: "/run/secrets/mastodon_personal_access_token"
      tags: ["personal", "life"]
      max_post_length: 500
      split_multi_image_posts: false

bluesky:
  accounts:
    - name: "main"
      instance_url: "https://bsky.social"
      handle: "user.bsky.social"
      app_password_file: "/run/secrets/bluesky_main_app_password"
      tags: ["tech", "python"]
      max_post_length: 300
      split_multi_image_posts: true
```

Account options:

- `name`: account label used in logs and mapping storage
- `instance_url`: server URL
- `access_token_file` (Mastodon) / `app_password_file` (Bluesky): credential file path
- `tags`: optional tag slugs that gate routing
- `max_post_length`: optional per-account post length override
- `split_multi_image_posts`: optional per-account image splitting

## 2. Configure Ghost Webhooks

Create integrations in Ghost Admin:

- Primary webhook: `POST /webhook/ghost` on publish
- Optional catch-up webhook: `POST /webhook/ghost/post-updated` on post updates

The update webhook is useful when an account was added later or a publish-time syndication failed.

## 3. Routing Rules

POSSE routes each post per account:

- If account `tags` is empty or omitted, that account receives all posts
- If account `tags` is set, POSSE matches against Ghost tag slugs (case-insensitive)
- No matching tags means the account is skipped for that post

## 4. Post Formatting Rules

POSSE builds outgoing content from Ghost data:

- Uses `custom_excerpt` when available, otherwise title
- Appends hashtags derived from Ghost tags whose names already include `#`
- Removes internal control tags from outgoing hashtags: `#nosplit`, `#dont-duplicate-feature`
- Appends `#posse` and the canonical Ghost post URL

## 5. Media Behavior

### Image selection

- Only local images on the same domain as the Ghost post are included
- External images are skipped
- `feature_image` is placed first when available

### Alt text

- Existing Ghost alt text is reused
- Missing alt text can be generated through optional LLM integration

```yaml
llm:
  enabled: true
  url: "llama-vision"
  port: 5000
  # timeout: 60
```

### Bluesky image limits

Before upload, Bluesky images are compressed when needed to fit blob limits:

- Target size: <= 1,000,000 bytes
- Longest dimension capped at 2500 px

### Multi-image splitting

If `split_multi_image_posts: true`, POSSE creates one post per image for that account.

To force a single post for a specific Ghost article, add the `#nosplit` tag.

## 6. Catch-Up Syndication on Post Updates

`POST /webhook/ghost/post-updated` checks existing syndication mappings in SQLite and only queues missing platform/account pairs.

This prevents duplicate posts while filling gaps.

## 7. Storage Model

Runtime state is SQLite-only and stored under `interactions.cache_directory`:

- Database file: `<cache_directory>/interactions.db`
- Syndication mappings table: `syndication_mappings`
- Interaction payload table: `interaction_data`

This mapping data is also used by interaction sync and widget APIs.

## 8. Validate Setup

Basic checks:

```bash
curl -sS http://localhost:5000/health
```

Watch logs while publishing/updating a Ghost post to confirm account routing and posting results.
