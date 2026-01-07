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
- **Multi-Account Mastodon Support**: Post to multiple Mastodon accounts with smart filtering:
  - Configure unlimited Mastodon accounts
  - Per-account filters based on tags, visibility, featured status, etc.
  - Simple access token authentication
  - Secure credential management with Docker secrets
  - Status posting with visibility controls
- **Multi-Account Bluesky Support**: Same flexible multi-account support for Bluesky (coming soon)
- **Smart Post Filtering**: Route posts to specific accounts based on criteria:
  - Filter by Ghost post tags (include or exclude)
  - Filter by visibility (public, members, paid)
  - Filter by featured status
  - Filter by publication status
  - Combine multiple filters with AND/OR logic
- **Robust Validation**: JSON Schema validation for all incoming webhooks
- **Production Ready**: Gunicorn server with comprehensive logging
- **Docker Support**: Easy deployment with Docker and Docker Compose
- **Automated Docker Hub Publishing**: Automatically publishes Docker images to Docker Hub when CI tests pass

## TODO
- [x] build and test flow
- [x] flask server to receive POST requests from Ghost with contents of the published post
- [x] Pushover notifications for main events (post received, queued, validation errors)
- [x] automated Docker Hub publishing on successful CI builds
- [x] implement Mastodon app registration and user authentication
- [x] multi-account support for Mastodon and Bluesky with per-account filters
- [ ] integrate Mastodon posting with Ghost webhook flow
- [ ] authenticate and post to Bluesky account

## Configuration

### Application Configuration

POSSE uses a `config.yml` file for application settings. The configuration file is located in the project root directory.

#### Multi-Account Configuration (Recommended)

POSSE supports multiple accounts for both Mastodon and Bluesky, with per-account filters to control which posts get syndicated where.

**config.yml (Multi-Account):**
```yaml
# Pushover Push Notifications
pushover:
  enabled: true
  app_token_file: /run/secrets/pushover_app_token
  user_key_file: /run/secrets/pushover_user_key

# Mastodon Multi-Account Configuration
mastodon:
  accounts:
    - name: "personal"
      instance_url: "https://mastodon.social"
      access_token_file: "/run/secrets/mastodon_personal_access_token"
      filters:
        tags: ["personal", "tech", "photography"]  # Include posts with ANY of these tags
        visibility: ["public"]                      # Only public posts
    
    - name: "professional"
      instance_url: "https://fosstodon.org"
      access_token_file: "/run/secrets/mastodon_professional_access_token"
      filters:
        tags: ["work", "security", "tech"]
        exclude_tags: ["personal"]  # Don't cross-post personal content
        visibility: ["public"]
    
    - name: "all_posts"
      instance_url: "https://mastodon.example.com"
      access_token_file: "/run/secrets/mastodon_all_access_token"
      filters: {}  # Empty filters = syndicate all posts

# Bluesky Multi-Account Configuration (same structure)
bluesky:
  accounts:
    - name: "main"
      instance_url: "https://bsky.social"
      access_token_file: "/run/secrets/bluesky_main_access_token"
      filters:
        visibility: ["public"]
```

#### Legacy Single-Account Configuration (Still Supported)

For backward compatibility, the original single-account format still works:

**config.yml (Legacy):**
```yaml
# Pushover Push Notifications
pushover:
  enabled: false
  app_token_file: /run/secrets/pushover_app_token
  user_key_file: /run/secrets/pushover_user_key

# Mastodon Single Account (Legacy)
mastodon:
  enabled: false
  instance_url: https://mastodon.social
  access_token_file: /run/secrets/mastodon_access_token
```

#### Filter Options

Filters control which Ghost posts get syndicated to each account:

- **`tags`**: Array of tag slugs to include (OR logic - post matches if ANY tag matches)
- **`exclude_tags`**: Array of tag slugs to exclude (takes precedence over `tags`)
- **`visibility`**: Array of visibility values (`"public"`, `"members"`, `"paid"`)
- **`featured`**: Boolean - only featured posts (`true`) or non-featured (`false`)
- **`status`**: Array of status values (`"draft"`, `"published"`, `"scheduled"`)

**Filter Logic:**
- Empty filters (`{}`) or omitted filters match **all posts**
- All specified filter criteria must match (AND logic)
- Within `tags` filter, ANY tag can match (OR logic)
- `exclude_tags` takes precedence over `tags`

**Examples:**

```yaml
# Only featured, public posts with tech tag
filters:
  tags: ["tech"]
  visibility: ["public"]
  featured: true

# All posts except drafts and personal content
filters:
  exclude_tags: ["draft", "personal"]
  status: ["published"]

# All public and members posts
filters:
  visibility: ["public", "members"]
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

### Mastodon Integration

POSSE supports multiple Mastodon accounts with per-account filters. This allows you to:
- Post different content to different Mastodon accounts
- Route posts based on tags, visibility, featured status, etc.
- Maintain separate personal and professional presences

#### Step 1: Create Application(s) in Mastodon

For **each** Mastodon account you want to use:

1. Go to your Mastodon instance (e.g., https://mastodon.social, https://fosstodon.org)
2. Navigate to **Settings** → **Development** → **New Application**
3. Fill in the application details:
   - **Application name**: POSSE (or customize per account)
   - **Scopes**: Select `write:statuses` (minimum required)
4. Click **Submit**
5. Copy the **Your access token** value

#### Step 2: Store Access Tokens

Create secret files using the naming convention: `{platform}_{account_name}_{credential_type}`

```bash
mkdir -p secrets

# Personal Mastodon account
echo "your_personal_token_here" > secrets/mastodon_personal_access_token.txt

# Professional Mastodon account
echo "your_professional_token_here" > secrets/mastodon_professional_access_token.txt
```

#### Step 3: Configure Accounts in config.yml

```yaml
mastodon:
  accounts:
    - name: "personal"
      instance_url: "https://mastodon.social"
      access_token_file: "/run/secrets/mastodon_personal_access_token"
      filters:
        tags: ["personal", "photography", "travel"]
        visibility: ["public"]
    
    - name: "professional"
      instance_url: "https://fosstodon.org"
      access_token_file: "/run/secrets/mastodon_professional_access_token"
      filters:
        tags: ["tech", "security", "work"]
        exclude_tags: ["personal"]
        visibility: ["public"]
```

#### Step 4: Update Docker Compose

Add Mastodon secrets to your `docker-compose.yml`:

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
      - mastodon_personal_access_token
      - mastodon_professional_access_token
    command: poetry run posse

secrets:
  pushover_app_token:
    file: ./secrets/pushover_app_token.txt
  pushover_user_key:
    file: ./secrets/pushover_user_key.txt
  mastodon_personal_access_token:
    file: ./secrets/mastodon_personal_access_token.txt
  mastodon_professional_access_token:
    file: ./secrets/mastodon_professional_access_token.txt
```

#### Legacy Single-Account Configuration

The original single-account format is still supported for backward compatibility:

```yaml
mastodon:
  enabled: true
  instance_url: https://mastodon.social
  access_token_file: /run/secrets/mastodon_access_token
```

With corresponding Docker Compose secrets:

```yaml
secrets:
  mastodon_access_token:
    file: ./secrets/mastodon_access_token.txt
```

If Mastodon is not enabled in config.yml, the application will run normally without posting to Mastodon.

## Getting Started

Ensure Docker is installed on your system, then use Docker Compose to run the application:

```bash
docker compose up
```

Refer to the Makefile for additional development and utility commands.

## Example Usage

For a complete production example of POSSE integrated with a Ghost blog, including webhook configuration and deployment setup, see:

**[Ghost Blog Docker Compose Example](https://github.com/wpowiertowski/docker/blob/main/ghost/compose.yml)**

This example demonstrates:
- Running POSSE alongside a Ghost blog and MySQL database
- Using Docker secrets for secure credential management
- Network configuration for service communication
- Production-ready deployment with a Cloudflare tunnel
