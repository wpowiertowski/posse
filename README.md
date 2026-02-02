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
- **Social Interaction Sync**: Display social media engagement (likes, reposts, comments) on your Ghost posts
- **IndieWeb News Syndication**: Submit posts to IndieWeb News via webmention
- **LLM Alt Text Generation**: Optional AI-powered alt text generation for images using vision models
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
   ```

2. **Add your credentials** (at minimum, one Mastodon or Bluesky account):
   ```bash
   mkdir -p secrets
   echo "your_mastodon_token" > secrets/mastodon_access_token.txt
   ```

3. **Edit `config.yml`** with your account settings (see [Configuration](#configuration))

4. **Start the application**:
   ```bash
   docker compose up
   ```

5. **Configure Ghost webhook**: In Ghost admin → **Settings** → **Integrations** → **Add custom integration**:
   - **Webhook URL**: `http://your-posse-host:5000/webhook/ghost`
   - **Event**: Post published

### Using the Docker Hub Image

Alternatively, pull the pre-built image:

```bash
docker pull wpowiertowski/posse:latest
```

## Configuration

### Basic Configuration

Create a `config.yml` file in the project root (use `config.example.yml` as a template):

```yaml
# Optional: Enable LLM for automatic alt text generation
llm:
  enabled: false  # Set to true to enable automatic alt text generation
  url: "llama-vision"  # Hostname or URL of the LLM service
  port: 5000  # Port number for the LLM service
  # timeout: 60  # Optional: Request timeout in seconds (default: 60)

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

Each account can optionally specify tags to filter which posts are syndicated:

- **No tags or empty list**: Account receives ALL posts
- **With tags**: Account only receives posts with at least one matching tag (case-insensitive, matches Ghost tag slugs)

**Example use cases**:

- Archive account (no filter) → receives everything
- Personal account with `["personal", "life"]` → only personal posts  
- Tech account with `["technology", "programming"]` → only tech posts

### LLM-Powered Alt Text Generation (Optional)

POSSE can automatically generate descriptive alt text for images that don't already have alt text in your Ghost posts. This feature uses a vision-capable language model (like Llama 3.2 Vision) to analyze images and create accessible descriptions.

**Benefits**:

- Improves accessibility for visually impaired users
- Automatically adds alt text to images without manual intervention
- Only processes images that are missing alt text

**Setup**:

1. **Deploy a vision-capable LLM service**. You can use the [llama-vision Docker container](https://github.com/wpowiertowski/docker/tree/main/llama-vision) which provides a compatible API.

2. **Enable LLM in config.yml**:

   ```yaml
   llm:
     enabled: true
     url: "llama-vision"  # Hostname of your LLM service
     port: 5000
   ```

3. **Add to docker-compose.yml** (if using Docker):

   ```yaml
   services:
     posse:
       # ... existing config ...
       depends_on:
         - llama-vision
     
     llama-vision:
       image: your-llama-vision-image:latest
       ports:
         - "5000:5000"
       environment:
         MODEL_PATH: /models
         MODEL_NAME: llama-3.2-11b-vision-instruct-q4_k_m.gguf
       volumes:
         - ./models:/models
   ```

**How it works**:

- When a post is received, POSSE checks each image for existing alt text
- If alt text is missing, the image is sent to the LLM service
- The LLM generates a concise, descriptive caption
- The generated alt text is used when posting to social media

**Note**: LLM processing adds latency to post syndication (typically 5-30 seconds per image depending on your hardware). Images with existing alt text are not processed.

### Managing Secrets

POSSE uses Docker secrets for secure credential management. Store each credential in a separate file:

```bash
mkdir -p secrets
echo "your_token" > secrets/mastodon_access_token.txt
echo "your_app_password" > secrets/bluesky_app_password.txt
echo "your_pushover_token" > secrets/pushover_app_token.txt
```

Then reference them in `docker-compose.yml`:

```yaml
services:
  app:
    secrets:
      - mastodon_access_token
      - bluesky_app_password

secrets:
  mastodon_access_token:
    file: ./secrets/mastodon_access_token.txt
  bluesky_app_password:
    file: ./secrets/bluesky_app_password.txt
```

### Setting Up Mastodon

1. **Create a Mastodon application** on your instance:
   - Go to **Settings** → **Development** → **New Application**
   - Application name: `POSSE`
   - Required scope: `write:statuses`
   - Copy the access token

2. **Store the access token** in `secrets/` and add to `docker-compose.yml` (see [Managing Secrets](#managing-secrets))

3. **Update `config.yml`** with your instance URL and account name

### Setting Up Bluesky

1. **Create a Bluesky app password**:
   - Go to **Settings** → **App Passwords**
   - Create a new app password named `POSSE`
   - Copy the generated password (not your account password)

2. **Store the app password** in `secrets/` and add to `docker-compose.yml` (see [Managing Secrets](#managing-secrets))

3. **Update `config.yml`** with your handle and instance URL

### Pushover Notifications (Optional)

1. **Create a Pushover account** at [pushover.net](https://pushover.net/) and create an application
2. **Store credentials** in `secrets/` (see [Managing Secrets](#managing-secrets))
3. **Enable in `config.yml`**: Set `pushover.enabled: true`

**Notification types**: 📝 Post received | ✅ Queued for syndication | ⚠️ Validation errors

### Social Interaction Sync (Optional)

Display social media engagement from Mastodon and Bluesky directly on your Ghost posts.

1. **Enable in `config.yml`**:
   ```yaml
   interactions:
     enabled: true
     sync_interval_minutes: 30
     max_post_age_days: 30
   ```

2. **Add widget to Ghost posts**: See [Interaction Sync Guide](docs/INTERACTION_SYNC_README.md) for detailed setup

3. **Features**:
   - Aggregated stats (likes, reposts, replies)
   - Recent comment previews
   - Auto-refresh every 5 minutes
   - Responsive design

For complete setup instructions, see the [Social Interaction Sync Guide](docs/INTERACTION_SYNC_README.md).

### IndieWeb News Syndication (Optional)

Submit your posts to [IndieWeb News](https://news.indieweb.org/) via webmention when tagged with a specific tag.

1. **Enable in `config.yml`**:
   ```yaml
   indieweb:
     enabled: true
     news:
       endpoint: "https://news.indieweb.org/en/webmention"
       target: "https://news.indieweb.org/en"
       tag: "indiewebnews"
   ```

2. **Add u-syndication markup to your Ghost theme**: Your theme must include a link to IndieWeb News with the `u-syndication` class in your h-entry markup for the webmention to be accepted.

3. **Tag your posts**: Add the `indiewebnews` tag to posts you want submitted to IndieWeb News.

**Note**: The webmention endpoint is language-specific. Use `/en/webmention` for English, `/de/webmention` for German, etc.

## How It Works

1. **Receive**: Ghost sends a webhook when a post is published
2. **Validate**: The post is validated against a JSON schema
3. **Notify**: Optional push notifications via Pushover
4. **Syndicate**: Posts are distributed to configured Mastodon and Bluesky accounts
5. **Sync Back**: Social media interactions are synced back to Ghost (optional)

Your Ghost blog remains the source of truth while your content reaches audiences across multiple platforms.

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
      "uuid": "5f2b3c4d-1234-5678-9abc-def012345678",
      "title": "My Blog Post",
      "slug": "my-blog-post",
      "status": "published",
      "url": "https://myblog.com/my-blog-post/",
      "created_at": "2026-01-15T10:00:00.000Z",
      "updated_at": "2026-01-15T10:00:00.000Z",
      "tags": [
        {"id": "tag1", "name": "Technology", "slug": "technology"}
      ],
      "authors": [
        {"id": "author1", "name": "John Doe", "slug": "john-doe"}
      ]
    }
  }
}
```

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.
