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
- **Multi-Account Mastodon Support**: Post to multiple Mastodon accounts:
  - Configure unlimited Mastodon accounts
  - Simple access token authentication
  - Secure credential management with Docker secrets
  - Status posting with visibility controls
- **Multi-Account Bluesky Support**: Post to multiple Bluesky accounts:
  - Configure unlimited Bluesky accounts
  - Session string authentication via ATProto
  - Secure credential management with Docker secrets
  - Status posting and credential verification
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
- [x] multi-account support for Mastodon and Bluesky
- [x] authenticate and post to Bluesky account
- [ ] integrate Mastodon posting with Ghost webhook flow
- [ ] integrate Bluesky posting with Ghost webhook flow

## Configuration

### Application Configuration

POSSE uses a `config.yml` file for application settings. The configuration file is located in the project root directory.

#### Account Configuration

POSSE supports multiple accounts for both Mastodon and Bluesky.

**config.yml:**
```yaml
# Pushover Push Notifications
pushover:
  enabled: true
  app_token_file: /run/secrets/pushover_app_token
  user_key_file: /run/secrets/pushover_user_key

# Mastodon Configuration
mastodon:
  accounts:
    - name: "personal"
      instance_url: "https://mastodon.social"
      access_token_file: "/run/secrets/mastodon_personal_access_token"
    
    - name: "professional"
      instance_url: "https://fosstodon.org"
      access_token_file: "/run/secrets/mastodon_professional_access_token"
    
    - name: "all_posts"
      instance_url: "https://mastodon.example.com"
      access_token_file: "/run/secrets/mastodon_all_access_token"

# Bluesky Configuration (same structure)
bluesky:
  accounts:
    - name: "main"
      instance_url: "https://bsky.social"
      access_token_file: "/run/secrets/bluesky_main_access_token"
```

**Single Account Configuration:**

For a single account setup, simply configure one account in the accounts array:

```yaml
mastodon:
  accounts:
    - name: "main"
      instance_url: "https://mastodon.social"
      access_token_file: "/run/secrets/mastodon_access_token"
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
    
    - name: "professional"
      instance_url: "https://fosstodon.org"
      access_token_file: "/run/secrets/mastodon_professional_access_token"
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

### Bluesky Integration

POSSE supports multiple Bluesky accounts using session strings for authentication. This allows you to:
- Post content to multiple Bluesky accounts
- Maintain separate personal and professional presences
- Route posts based on tags or other criteria

#### Step 1: Obtain Session String(s)

For **each** Bluesky account you want to use, you need to generate a session string:

**Option A: Using Python directly**

```python
from atproto import Client

client = Client()
# Login with your Bluesky handle and app password
profile = client.login('your.handle.bsky.social', 'your-app-password')
# Export and save the session string
session_string = client.export_session_string()
print(session_string)
```

**Option B: Using the provided helper script**

Create a file `scripts/get_bluesky_session.py`:
```python
#!/usr/bin/env python3
"""Helper script to generate Bluesky session strings."""
from atproto import Client
import sys

if len(sys.argv) != 3:
    print("Usage: python scripts/get_bluesky_session.py <handle> <password>")
    print("Example: python scripts/get_bluesky_session.py myhandle.bsky.social mypassword")
    sys.exit(1)

handle = sys.argv[1]
password = sys.argv[2]

try:
    client = Client()
    profile = client.login(handle, password)
    session_string = client.export_session_string()
    
    print(f"\n✅ Successfully authenticated as @{profile.handle}")
    print(f"\nYour session string (save this securely):")
    print(session_string)
    print(f"\nAdd this to your secrets file:")
    print(f"echo '{session_string}' > secrets/bluesky_ACCOUNTNAME_access_token.txt")
except Exception as e:
    print(f"\n❌ Authentication failed: {e}")
    sys.exit(1)
```

**Note:** For security, Bluesky recommends using [App Passwords](https://bsky.app/settings/app-passwords) instead of your main password. Generate an app password in your Bluesky settings and use it here.

#### Step 2: Store Session Strings

Create secret files using the naming convention: `bluesky_{account_name}_access_token.txt`

```bash
mkdir -p secrets

# Main Bluesky account
echo "your_main_session_string_here" > secrets/bluesky_main_access_token.txt

# Professional Bluesky account
echo "your_professional_session_string_here" > secrets/bluesky_professional_access_token.txt
```

#### Step 3: Configure Accounts in config.yml

```yaml
bluesky:
  accounts:
    - name: "main"
      instance_url: "https://bsky.social"
      access_token_file: "/run/secrets/bluesky_main_access_token"
    
    - name: "professional"
      instance_url: "https://bsky.social"
      access_token_file: "/run/secrets/bluesky_professional_access_token"
```

#### Step 4: Update Docker Compose

Add Bluesky secrets to your `docker-compose.yml`:

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
      - bluesky_main_access_token
      - bluesky_professional_access_token
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
  bluesky_main_access_token:
    file: ./secrets/bluesky_main_access_token.txt
  bluesky_professional_access_token:
    file: ./secrets/bluesky_professional_access_token.txt
```

**Important Notes:**
- Session strings should be kept secure like passwords
- Session strings expire when you change your password
- If authentication fails, regenerate a new session string
- Use app passwords instead of your main password for better security

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
