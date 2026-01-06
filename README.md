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
- **Mastodon Integration**: Simple access token authentication:
  - Post to any Mastodon instance
  - Secure credential management with Docker secrets
  - Status posting with visibility controls
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
- [ ] integrate Mastodon posting with Ghost webhook flow
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

# Mastodon Configuration
mastodon:
  enabled: false  # Set to true to enable Mastodon posting
  instance_url: https://mastodon.social
  access_token_file: /run/secrets/mastodon_access_token
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

To enable posting to Mastodon, you can use either:
- **Option A**: OAuth Flow (Recommended for automation) - Full programmatic setup
- **Option B**: Manual Token (Quick start) - Get token from Mastodon UI

#### Option A: OAuth Flow Setup (Recommended)

This approach uses the Mastodon.py library's OAuth flow to programmatically register your app and obtain credentials.

##### Step 1: Register Your Application

Create a secrets directory and register POSSE as an OAuth application:

```bash
mkdir -p secrets

# Run app registration interactively
docker run -it --rm \
  -v $(pwd)/secrets:/secrets \
  --entrypoint python3 \
  wpowiertowski/posse:latest -c "
from mastodon_client.mastodon_client import MastodonClient

# Register app with your Mastodon instance
client_id, client_secret = MastodonClient.register_app(
    app_name='POSSE',
    instance_url='https://mastodon.social',  # Change to your instance
    to_file='/secrets/mastodon_client.secret'
)
print('✓ App registered successfully!')
print(f'Client credentials saved to secrets/mastodon_client.secret')
"
```

##### Step 2: Authorize and Get Access Token

Generate an authorization URL, authorize the app, and exchange the code for an access token:

```bash
# Run OAuth authorization flow interactively
docker run -it --rm \
  -v $(pwd)/secrets:/secrets \
  --entrypoint python3 \
  wpowiertowski/posse:latest -c "
from mastodon_client.mastodon_client import MastodonClient

# Create OAuth client
client = MastodonClient.create_for_oauth(
    client_credential_file='/secrets/mastodon_client.secret',
    instance_url='https://mastodon.social'  # Change to your instance
)

# Get authorization URL
auth_url = client.get_auth_request_url()
print('\\n📋 Step 1: Visit this URL to authorize POSSE:')
print(auth_url)
print('\\n📋 Step 2: After authorizing, copy the code and paste it below')

# Get authorization code from user
code = input('\\nEnter authorization code: ').strip()

# Exchange code for access token
access_token = client.login_with_code(
    code=code,
    to_file='/secrets/mastodon_access_token.txt'
)
print('\\n✓ Access token saved to secrets/mastodon_access_token.txt')
print('✓ Mastodon OAuth setup complete!')
"
```

##### Step 3: Test Your Setup

Verify everything works by posting a test toot:

```bash
# Test posting
docker run -it --rm \
  -v $(pwd)/secrets:/secrets \
  --entrypoint python3 \
  wpowiertowski/posse:latest -c "
from mastodon_client.mastodon_client import MastodonClient

# Read access token
with open('/secrets/mastodon_access_token.txt', 'r') as f:
    access_token = f.read().strip()

# Create client and post
client = MastodonClient(
    instance_url='https://mastodon.social',  # Change to your instance
    access_token=access_token
)

result = client.toot('🚀 Hello from POSSE! Testing OAuth integration.')
if result:
    print(f\"✓ Successfully posted! View at: {result['url']}\")
else:
    print('✗ Posting failed')
"
```

#### Option B: Manual Token Setup (Quick Start)

Alternatively, get an access token directly from your Mastodon instance:

##### Step 1: Create Application in Mastodon UI

1. Go to your Mastodon instance (e.g., https://mastodon.social)
2. Navigate to **Settings** → **Development** → **New Application**
3. Fill in the application details:
   - **Application name**: POSSE
   - **Scopes**: Select `write:statuses` (minimum required)
4. Click **Submit**
5. Copy the **Your access token** value

##### Step 2: Store Access Token

```bash
mkdir -p secrets
echo "your_access_token_here" > secrets/mastodon_access_token.txt
```

#### Configure POSSE for Production

After completing either Option A or B, configure POSSE to use your Mastodon credentials:

##### 1. Enable Mastodon in Configuration

Update `config.yml`:
```yaml
mastodon:
  enabled: true
  instance_url: https://mastodon.social  # Your Mastodon instance URL
  access_token_file: /run/secrets/mastodon_access_token
```

##### 2. Update Docker Compose

Add Mastodon secret to your `docker-compose.yml`:

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
      - mastodon_access_token
    command: poetry run posse

secrets:
  pushover_app_token:
    file: ./secrets/pushover_app_token.txt
  pushover_user_key:
    file: ./secrets/pushover_user_key.txt
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

**[Ghost Blog Docker Compose Example](https://github.com/wpowiertowski/docker/blob/main/ghost/ghost.yml)**

This example demonstrates:
- Running POSSE alongside a Ghost blog and MySQL database
- Using Docker secrets for secure credential management
- Network configuration for service communication
- Production-ready deployment with a Cloudflare tunnel
