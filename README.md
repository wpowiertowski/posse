[![CI](https://github.com/wpowiertowski/posse/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/wpowiertowski/posse/actions?query=branch%3Amain)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python 3.14+](https://img.shields.io/badge/python-3.14%2B-blue)](https://www.python.org/downloads/)
[![Poetry](https://img.shields.io/badge/poetry-managed-blue.svg)](https://python-poetry.org/)
[![Docker](https://img.shields.io/badge/docker-ready-blue.svg)](https://www.docker.com/)

# POSSE

**Publish Own Site, Syndicate Elsewhere** for Ghost blogs.

POSSE receives Ghost webhooks, validates and processes published/updated posts, syndicates content to Mastodon and Bluesky, and can sync social interactions back to your site.

## Why newcomers pick POSSE

- **Ghost-first workflow**: your Ghost post remains the source of truth.
- **Multi-account syndication**: post to one or many Mastodon/Bluesky accounts with optional tag filters.
- **Interaction sync API + widget**: show likes/reposts/replies from syndicated posts on your Ghost pages.
- **Operational safety**: schema validation, API hardening, optional internal token auth, and rate limiting.
- **Production-ready runtime**: Docker + Compose support, structured logging, and test coverage.

## Quick start (Docker)

1. Clone and prepare config:
   ```bash
   git clone https://github.com/wpowiertowski/posse.git
   cd posse
   cp config.example.yml config.yml
   ```
2. Add at least one account credential in `secrets/`.
3. Start POSSE:
   ```bash
   docker compose up -d
   ```
4. In Ghost Admin, add a custom integration webhook:
   - **URL**: `http://your-posse-host:5000/webhook/ghost`
   - **Event**: `post.published` (and optionally `post.edited` for catch-up syndication)

## Minimum configuration to go live

- Configure at least one account under `mastodon.accounts` or `bluesky.accounts`.
- Point each account to its token/password file.
- (Recommended) configure `security.internal_api_token_file` and keep `/sync` protected.
- (Recommended for widget) enable `cors` and allow your Ghost origin.

Use [`config.example.yml`](config.example.yml) as the source of truth for all options.

## Documentation map

- **Interaction Sync setup**: [`docs/INTERACTION_SYNC_README.md`](docs/INTERACTION_SYNC_README.md)
- **Interaction architecture notes**: [`docs/INTERACTION_SYNC_ARCHITECTURE.md`](docs/INTERACTION_SYNC_ARCHITECTURE.md)
- **Security hardening + reverse proxy guidance**: [`docs/SECURITY_HARDENING.md`](docs/SECURITY_HARDENING.md)
- **Upgrade notes for recent releases**: [`docs/UPGRADE_GUIDE.md`](docs/UPGRADE_GUIDE.md)
- **Widget source**: [`widget/social-interactions-widget.html`](widget/social-interactions-widget.html)

## Development

Common commands:

```bash
make help
make up
make down
make test
make test-verbose
```

## License

MIT — see [`LICENSE`](LICENSE).
