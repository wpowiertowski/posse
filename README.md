[![CI](https://github.com/wpowiertowski/posse/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/wpowiertowski/posse/actions?query=branch%3Amain)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python 3.14+](https://img.shields.io/badge/python-3.14%2B-blue)](https://www.python.org/downloads/)
[![Poetry](https://img.shields.io/badge/poetry-managed-blue.svg)](https://python-poetry.org/)
[![Docker](https://img.shields.io/badge/docker-ready-blue.svg)](https://www.docker.com/)

# POSSE

POSSE stands for **Publish Own Site, Syndicate Elsewhere**. This project implements the POSSE philosophy by automatically retrieving the latest posts from a Ghost blog and reposting them to both Mastodon and Bluesky accounts.

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
- **Automated Docker Hub Publishing**: Automatically publishes Docker images to Docker Hub when CI tests pass

## TODO
- [x] build and test flow
- [x] flask server to receive POST requests from Ghost with contents of the published post
- [x] Pushover notifications for main events (post received, queued, validation errors)
- [x] automated Docker Hub publishing on successful CI builds
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
   mkdir -p secrets
   echo "your_app_token_here" > secrets/pushover_app_token.txt
   echo "your_user_key_here" > secrets/pushover_user_key.txt
   ```
4. **Update config.yml** and set `pushover.enabled: true`

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
    file: ./secrets/pushover_app_token.txt
  pushover_user_key:
    file: ./secrets/pushover_user_key.txt
```

If Pushover is not enabled in config.yml, the application will run normally without sending notifications.

### Notifications Sent

The following notifications are sent automatically:

- **📝 Post Received**: When a Ghost post is successfully received and validated
- **✅ Post Queued**: When a post is queued for syndication (includes link to post)
- **⚠️ Validation Error**: When a webhook fails validation (high priority)

## Getting Started

### Using Docker Hub Image (Recommended)

The easiest way to get started is by using the pre-built Docker image from Docker Hub:

```bash
docker pull wpowiertowski/posse:latest
docker run -p 5000:5000 -v $(pwd)/config.yml:/app/config.yml:ro wpowiertowski/posse:latest
```

**Note**: The Docker image will be published to Docker Hub after the first successful CI build on the main branch.

### Building from Source

Ensure Docker is installed on your system, then use Docker Compose to run the application:

```bash
docker compose up
```

Refer to the Makefile for additional development and utility commands.

## CI/CD Pipeline

This project uses GitHub Actions for continuous integration and deployment:

### CI Workflow
- Runs automatically on pushes to `main` and on pull requests
- Executes all tests using Docker Compose
- Must pass before Docker image publishing

### Docker Hub Publishing
- Automatically triggers after CI tests pass on the `main` branch
- Builds and pushes Docker images to Docker Hub
- Tags images with:
  - `latest` - The most recent build from main
  - `main-<sha>` - Build from specific commit SHA
  - `main` - Branch-specific tag

### Required GitHub Secrets

To enable Docker Hub publishing, configure the following secrets in your GitHub repository settings:

| Secret Name | Description |
|------------|-------------|
| `DOCKER_HUB_USERNAME` | Your Docker Hub username |
| `DOCKER_HUB_TOKEN` | Docker Hub access token (create at https://hub.docker.com/settings/security) |

**Note**: Never commit credentials directly to the repository. Always use GitHub Secrets for sensitive information.
