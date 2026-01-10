[![CI](https://github.com/wpowiertowski/posse/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/wpowiertowski/posse/actions?query=branch%3Amain)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python 3.14+](https://img.shields.io/badge/python-3.14%2B-blue)](https://www.python.org/downloads/)
[![Poetry](https://img.shields.io/badge/poetry-managed-blue.svg)](https://python-poetry.org/)
[![Docker](https://img.shields.io/badge/docker-ready-blue.svg)](https://www.docker.com/)

# POSSE

**Publish Own Site, Syndicate Elsewhere** - Automatically syndicate your Ghost blog posts to Mastodon and Bluesky.

POSSE is a Docker-ready Python application that receives webhooks from your Ghost blog and cross-posts content to multiple Mastodon and Bluesky accounts. Keep your blog as the source of truth while maintaining a presence across the fediverse and social media platforms.

## Features

- **Ghost Webhook Integration**: Automatically receives and validates Ghost post webhooks
- **Multi-Account Support**: Configure unlimited Mastodon and Bluesky accounts
- **Pushover Notifications**: Get real-time push notifications for important events:
  - 📝 New post received and validated
  - ✅ Post queued for syndication
  - ⚠️ Validation errors
- **Robust Validation**: JSON Schema validation for all incoming webhooks
- **Production Ready**: Runs with Gunicorn and comprehensive logging
- **Docker Support**: Easy deployment with Docker and Docker Compose
- **Secure Credentials**: Credential management with Docker secrets

## Quick Start

**Prerequisites**: Docker must be installed on your system.

1. **Clone and configure**:
   ```bash
   git clone https://github.com/wpowiertowski/posse.git
   cd posse
   cp config.example.yml config.yml
   # Edit config.yml with your settings (see Configuration section)
   ```

2. **Start the application**:
   ```bash
   docker compose up
   ```

3. **Configure Ghost webhook**: In your Ghost admin panel, navigate to **Settings** → **Integrations** → **Custom Integrations** → **Add custom integration**:
   - **Webhook URL**: `http://your-posse-host:5000/webhook/ghost`
   - **Event**: Post published

The webhook receiver will be available at `http://localhost:5000/webhook/ghost`. For detailed configuration including Mastodon, Bluesky, and Pushover setup, see the Configuration section below.

## How It Works

POSSE automates the syndication workflow:

1. **Receive**: Ghost sends a webhook when a post is published
2. **Validate**: The post is validated against a JSON schema
3. **Notify**: Optional push notifications via Pushover
4. **Syndicate**: Posts are distributed to configured Mastodon and Bluesky accounts

Your Ghost blog remains the source of truth while your content reaches audiences across multiple platforms.

## Configuration

### Basic Configuration

Create a `config.yml` file in the project root (use `config.example.yml` as a template):

```yaml
# Optional: Enable Pushover notifications
pushover:
  enabled: true
  app_token_file: /run/secrets/pushover_app_token
  user_key_file: /run/secrets/pushover_user_key

# Configure Mastodon accounts
mastodon:
  accounts:
    - name: "personal"
      instance_url: "https://mastodon.social"
      access_token_file: "/run/secrets/mastodon_personal_access_token"
      # tags: []  # Optional: Empty or omitted means all posts
    # Add more accounts as needed
    - name: "professional"
      instance_url: "https://fosstodon.org"
      access_token_file: "/run/secrets/mastodon_professional_access_token"
      tags: ["tech", "programming"]  # Only posts with these tags

# Configure Bluesky accounts
bluesky:
  accounts:
    - name: "main"
      instance_url: "https://bsky.social"
      handle: "user.bsky.social"
      app_password_file: "/run/secrets/bluesky_main_app_password"
      tags: ["personal", "blog"]  # Filter by tags
```

### Tag-Based Filtering

Each account can optionally specify a list of tags to filter which posts are syndicated to that account:

- **No tags field or empty list**: Account receives ALL posts
- **With tags**: Account only receives posts that have at least one matching tag

The matching is case-insensitive and based on Ghost post tag slugs. For example:
- Post tagged with "Technology" (slug: "technology") will match account tag "technology"
- Post tagged with "Python" (slug: "python") will match account tag "python"

**Example use cases**:
- **Archive account**: No tags filter - receives everything
- **Personal account**: Tags ["personal", "blog", "life"] - only personal posts
- **Tech account**: Tags ["technology", "programming", "coding"] - only tech posts
- **Work account**: Tags ["business", "work"] - only professional content
```

### Setting Up Mastodon

1. **Create a Mastodon application** on your instance:
   - Go to **Settings** → **Development** → **New Application**
   - Application name: `POSSE`
   - Required scope: `write:statuses`
   - Copy the access token

2. **Store the access token securely**:
   ```bash
   mkdir -p secrets
   echo "your_mastodon_token" > secrets/mastodon_personal_access_token.txt
   ```

3. **Update `config.yml`** with your Mastodon instance URL and account name (see Basic Configuration above)

4. **Add secret to `docker-compose.yml`**:
   ```yaml
   services:
     app:
       secrets:
         - mastodon_personal_access_token
   
   secrets:
     mastodon_personal_access_token:
       file: ./secrets/mastodon_personal_access_token.txt
   ```

Repeat these steps for each Mastodon account you want to configure.

### Setting Up Bluesky

1. **Create a Bluesky app password**:
   - Go to **Settings** → **App Passwords**
   - Create a new app password
   - Give it a name like `POSSE`
   - Copy the generated password (not your account password)

2. **Store the app password securely**:
   ```bash
   mkdir -p secrets
   echo "your_app_password" > secrets/bluesky_main_app_password.txt
   ```

3. **Update `config.yml`** with your Bluesky instance URL, handle, and account name:
   ```yaml
   bluesky:
     accounts:
       - name: "main"
         instance_url: "https://bsky.social"
         handle: "your-handle.bsky.social"
         app_password_file: "/run/secrets/bluesky_main_app_password"
   ```

4. **Add secret to `docker-compose.yml`**:
   ```yaml
   services:
     app:
       secrets:
         - bluesky_main_app_password
   
   secrets:
     bluesky_main_app_password:
       file: ./secrets/bluesky_main_app_password.txt
   ```

Repeat these steps for each Bluesky account you want to configure.

### Pushover Notifications (Optional)

To enable real-time push notifications for post events:

1. **Create a Pushover account** at [pushover.net](https://pushover.net/) and create an application to get an API token
2. **Store credentials**:
   ```bash
   mkdir -p secrets
   echo "your_app_token" > secrets/pushover_app_token.txt
   echo "your_user_key" > secrets/pushover_user_key.txt
   ```
3. **Enable in `config.yml`**: Set `pushover.enabled: true` (see Basic Configuration above)
4. **Add secrets to `docker-compose.yml`** following the same pattern as Mastodon secrets

**Notification types**:
- 📝 Post received and validated
- ✅ Post queued for syndication
- ⚠️ Validation errors (high priority)

## Development

### Available Commands

Use the Makefile for common development tasks:

```bash
make help          # Show all available commands
make build         # Build Docker images
make up            # Start the application
make down          # Stop containers
make test          # Run tests
make shell         # Open a shell in the container
```

### Running Tests

```bash
# Run all tests
make test

# Run tests with verbose output
make test-verbose
```

### Project Status

**Implemented**:
- ✅ Ghost webhook receiver with validation
- ✅ Pushover notifications
- ✅ Multi-account support for Mastodon
- ✅ Multi-account support for Bluesky
- ✅ Bluesky authentication and credential verification
- ✅ Automated Docker Hub publishing
- ✅ Mastodon posting integration
- ✅ Bluesky posting integration

## Examples

### Complete Production Setup

For a complete production example showing POSSE integrated with Ghost, MySQL, and Cloudflare tunnel, see:

**[Ghost Blog Docker Compose Example](https://github.com/wpowiertowski/docker/blob/main/ghost/compose.yml)**

This example demonstrates:
- Running POSSE alongside Ghost blog and database
- Secure credential management with Docker secrets
- Network configuration for service communication
- Production-ready deployment setup

### Webhook Payload Example

Ghost sends webhooks in this format:

```json
{
  "post": {
    "current": {
      "id": "abc123",
      "title": "My Blog Post",
      "slug": "my-blog-post",
      "status": "published",
      "url": "https://myblog.com/my-blog-post/",
      "tags": ["technology", "tutorial"],
      "authors": [{"name": "John Doe"}]
    }
  }
}
```

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.
