
[![CI](https://github.com/wpowiertowski/posse/workflows/CI/badge.svg)](https://github.com/wpowiertowski/posse/actions)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python 3.14+](https://img.shields.io/badge/python-3.14%2B-blue)](https://www.python.org/downloads/)
[![Poetry](https://img.shields.io/badge/poetry-managed-blue.svg)](https://python-poetry.org/)
[![Docker](https://img.shields.io/badge/docker-ready-blue.svg)](https://www.docker.com/)

# POSSE

POSSE stands for **Post Own Site, Syndicate Elsewhere**. This project implements the POSSE philosophy by automatically retrieving the latest posts from a Ghost blog and reposting them to both Mastodon and Bluesky accounts.

## Prerequisites

The only prerequisite required to run this project is **Docker**.

## Project Structure

```
posse/
├── src/
│   ├── posse/          # Main POSSE orchestration package
│   │   └── posse.py    # Entry point that starts webhook receiver
│   ├── ghost/          # Ghost webhook receiver
│   │   ├── ghost.py    # Flask app with validation and logging
│   │   └── gunicorn_config.py  # Production server configuration
│   ├── notifications/  # Push notification services
│   │   └── pushover.py # Pushover notification client
│   └── schema/         # JSON Schema validation
│       ├── schema.py   # Schema loading utilities
│       └── ghost_post_schema.json  # Ghost post schema definition
├── tests/
│   ├── test_posse.py   # POSSE integration tests
│   ├── test_ghost.py   # Webhook receiver tests
│   ├── test_pushover.py # Pushover notification tests
│   └── fixtures/
│       └── valid_ghost_post.json  # Test data
├── Dockerfile          # Container configuration
├── docker-compose.yml  # Service orchestration
├── pyproject.toml      # Python dependencies and project metadata
├── poetry.lock         # Locked dependency versions
└── Makefile            # Development commands
```

## How It Works

This project automates the POSSE workflow by:

1. Retrieving the latest published posts from a configured Ghost blog via [webhook](https://docs.ghost.org/webhooks)
2. Sending push notifications via Pushover for main events (post received, queued, errors)
3. Reposting them to your Mastodon account (coming soon)
4. Reposting them to your Bluesky account (coming soon)

This ensures your content is syndicated across multiple platforms while maintaining your Ghost blog as the primary source of truth.

## Features

- **Ghost Webhook Integration**: Receives and validates Ghost post webhooks
- **Pushover Notifications**: Real-time push notifications for important events:
  - 📝 New post received and validated
  - ✅ Post queued for syndication
  - ⚠️ Validation errors
- **Robust Validation**: JSON Schema validation for all incoming webhooks
- **Production Ready**: Gunicorn server with comprehensive logging
- **Docker Support**: Easy deployment with Docker and Docker Compose

## TODO
- [x] build and test flow
- [x] flask server to receive POST requests from Ghost with contents of the published post
- [x] Pushover notifications for main events (post received, queued, validation errors)
- [ ] authenticate and post to Mastodon account
- [ ] authenticate and post to Bluesky account

## Configuration

### Application Configuration

POSSE uses a `config.yml` file for application settings. The configuration file is located in the project root directory.

**config.yml:**
```yaml
# Pushover Push Notifications
pushover:
  enabled: false  # Set to true to enable notifications
  app_token_file: /run/secrets/pushover_app_token
  user_key_file: /run/secrets/pushover_user_key
```

### Pushover Notifications (Optional)

To enable push notifications via [Pushover](https://pushover.net/):

1. **Create a Pushover account** and install the mobile app
2. **Create an application** in Pushover to get an API token and user key
3. **Create secret files** with your credentials:
   ```bash
   echo "your_app_token_here" > pushover_app_token.txt
   echo "your_user_key_here" > pushover_user_key.txt
   ```
4. **Update config.yml** and set `pushover.enabled: true`
5. **Update docker-compose.yml** to mount the secrets (uncomment the secrets sections)

**Docker Compose with Secrets:**

```yaml
services:
  app:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: posse
    volumes:
      - .:/app
      - ./config.yml:/app/config.yml:ro
    secrets:
      - pushover_app_token
      - pushover_user_key
    command: poetry run posse

secrets:
  pushover_app_token:
    file: ./pushover_app_token.txt
  pushover_user_key:
    file: ./pushover_user_key.txt
```

If Pushover is not enabled in config.yml, the application will run normally without sending notifications.

### Notifications Sent

The following notifications are sent automatically:

- **📝 Post Received**: When a Ghost post is successfully received and validated
- **✅ Post Queued**: When a post is queued for syndication (includes link to post)
- **⚠️ Validation Error**: When a webhook fails validation (high priority)

## Getting Started

Ensure Docker is installed on your system, then use Docker Compose to run the application:

```bash
docker compose up
```

Refer to the Makefile for additional development and utility commands.
