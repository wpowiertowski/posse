[![CI](https://github.com/wpowiertowski/posse/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/wpowiertowski/posse/actions?query=branch%3Amain)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python 3.14+](https://img.shields.io/badge/python-3.14%2B-blue)](https://www.python.org/downloads/)
[![Poetry](https://img.shields.io/badge/poetry-managed-blue.svg)](https://python-poetry.org/)
[![Docker](https://img.shields.io/badge/docker-ready-blue.svg)](https://www.docker.com/)

# POSSE

**Publish Own Site, Syndicate Elsewhere** for Ghost.

POSSE is a Docker-ready Python service that receives Ghost webhooks, syndicates posts to Mastodon and Bluesky, and can sync social interactions back to your blog.

## Feature Guides

Use the README for quick setup, then follow the focused guides:

- [Syndication Guide](docs/SYNDICATION_GUIDE.md) - multi-account posting, tag routing, media handling, catch-up syndication
- [Social Interaction Sync Guide](docs/INTERACTION_SYNC_README.md) - syncing likes/reposts/replies back to Ghost
- [Webmention Reply Guide](docs/WEBMENTION_REPLY_GUIDE.md) - self-hosted reply form and webmention publishing
- [Webmention Sending Guide](docs/WEBMENTION_SENDING_GUIDE.md) - tag-triggered webmention sending to configurable targets
- [Security Hardening Guide](docs/SECURITY_HARDENING.md) - endpoint protection and deployment hardening
- [Interaction Sync Architecture](docs/INTERACTION_SYNC_ARCHITECTURE.md) - internals and data flow
- [Widget Documentation](widget/docs/README.md) - embedding the social interactions widget

## Core Capabilities

- Ghost webhook receiver with JSON schema validation
- Multi-account Mastodon and Bluesky syndication with per-account tag filters
- Optional image splitting for multi-image posts (with `#nosplit` override)
- Optional LLM-generated alt text for missing image descriptions
- Automatic Bluesky image compression to fit blob size limits
- Social interaction sync API for Ghost widgets
- Tag-triggered webmention sending to configurable targets (e.g. IndieWeb News)
- Optional self-hosted webmention reply form and W3C-compliant receiver (`/webmention`)
- Optional Pushover notifications for syndication events and new social interaction replies

## Quick Start

Prerequisite: Docker installed locally.

1. Clone and configure:

```bash
git clone https://github.com/wpowiertowski/posse.git
cd posse
cp config.example.yml config.yml
mkdir -p secrets
```

2. Add at least one platform credential:

```bash
echo "your_mastodon_token" > secrets/mastodon_access_token.txt
# or
echo "your_bluesky_app_password" > secrets/bluesky_app_password.txt
```

3. Set platform accounts in `config.yml`.

4. Start POSSE:

```bash
docker compose up -d
```

5. Configure Ghost webhook(s):

- `POST http://your-posse-host:5000/webhook/ghost` for publish events
- Optional catch-up: `POST http://your-posse-host:5000/webhook/ghost/post-updated`

## Base Configuration

Start with a minimal config and add optional sections from the feature guides.

```yaml
timezone: "UTC"

mastodon:
  accounts:
    - name: "personal"
      instance_url: "https://mastodon.social"
      access_token_file: "/run/secrets/mastodon_personal_access_token"
      # tags: ["tech", "python"]
      # max_post_length: 500
      # split_multi_image_posts: false

bluesky:
  accounts:
    - name: "main"
      instance_url: "https://bsky.social"
      handle: "user.bsky.social"
      app_password_file: "/run/secrets/bluesky_main_app_password"
      # tags: ["tech", "python"]
      # max_post_length: 300
      # split_multi_image_posts: false
```

### Secrets

POSSE expects credentials in files (typically Docker secrets), for example:

```bash
mkdir -p secrets
echo "token" > secrets/mastodon_personal_access_token
echo "app-password" > secrets/bluesky_main_app_password
```

Reference those files from `config.yml` or mount them at `/run/secrets/...` in Docker.

## Optional Features

- Interaction sync and widget: [docs/INTERACTION_SYNC_README.md](docs/INTERACTION_SYNC_README.md)
- Webmention reply form: [docs/WEBMENTION_REPLY_GUIDE.md](docs/WEBMENTION_REPLY_GUIDE.md)
- Webmention receiver: [docs/WEBMENTION_RECEIVER_DESIGN.md](docs/WEBMENTION_RECEIVER_DESIGN.md)
- Webmention sending: [docs/WEBMENTION_SENDING_GUIDE.md](docs/WEBMENTION_SENDING_GUIDE.md)
- Security controls and reverse proxy hardening: [docs/SECURITY_HARDENING.md](docs/SECURITY_HARDENING.md)

## Runtime Endpoints

- `POST /webhook/ghost`: primary Ghost publish webhook
- `POST /webhook/ghost/post-updated`: catch-up webhook for already-published posts
- `GET /health`: liveness endpoint
- `GET /api/interactions/<ghost_post_id>`: interaction payload for a Ghost post
- `POST /api/interactions/<ghost_post_id>/sync`: manual sync trigger (protected with `X-Internal-Token` when configured)
- `GET /webmention`: reply form page (when `webmention_reply` is enabled)
- `POST /webmention`: W3C webmention receiver — accepts incoming webmentions from external sites (when `webmention_receiver` is enabled)
- `POST /api/webmention/reply`: reply submission endpoint (when `webmention_reply` is enabled)
- `GET /reply/<reply_id>`: published h-entry source page for a reply
- `GET /api/webmentions?target=<url>`: query verified received webmentions for a target URL (when `webmention_receiver` is enabled)

## Development

Common commands:

```bash
make help
make build
make up
make down
make test
make test-verbose
make shell
```

## Deployment Reference

For a complete production stack (Ghost + POSSE + supporting services), see:

- [Ghost Docker Compose example](https://github.com/wpowiertowski/docker/blob/main/ghost/compose.yml)

## License

MIT. See [LICENSE](LICENSE).
