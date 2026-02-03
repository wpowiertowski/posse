# Social Interaction Sync - User Guide

## Overview

The Social Interaction Sync feature allows you to display social media engagement (likes, reposts, and comments) from Mastodon and Bluesky directly on your Ghost blog posts. When you syndicate a post via POSSE, the interactions from social media are automatically synced back and can be displayed using a JavaScript widget.

## Features

- **Automatic Syncing**: Interactions are automatically retrieved from Mastodon and Bluesky
- **Aggregated Stats**: Shows total likes, reposts, and replies across all platforms
- **Comment Previews**: Displays recent comments from both platforms
- **Platform-Specific Details**: View engagement breakdown by platform
- **Webmentions Support**: Display likes, reposts, and comments via webmention.io
- **Automatic Discovery**: Discovers syndication mappings for older posts when Ghost Content API is configured
- **Auto-Refresh**: Widget updates every 5 minutes without page reload
- **Responsive Design**: Mobile-friendly with dark mode support

## Configuration

Add the following to your `config.yml`:

```yaml
interactions:
  enabled: true                    # Enable/disable interaction syncing
  sync_interval_minutes: 30        # How often to sync (in minutes)
  max_post_age_days: 30           # Maximum age of posts to sync
  cache_directory: "./data/interactions"  # Where to store interaction data

  # Privacy settings (optional)
  show_reply_content: true         # Show full comment text
  show_reply_authors: true         # Show commenter names and avatars
```

### Configuration Options

| Option | Default | Description |
|--------|---------|-------------|
| `enabled` | `true` | Enable or disable interaction syncing |
| `sync_interval_minutes` | `30` | How frequently to check for new interactions |
| `max_post_age_days` | `30` | Stop syncing posts older than this |
| `cache_directory` | `./data/interactions` | Directory to store interaction data |

### Ghost Content API (Recommended)

To enable automatic syndication mapping discovery for older posts, configure the Ghost Content API:

```yaml
ghost:
  content_api:
    url: "https://yourblog.com"  # Your Ghost blog URL
    key_file: "/run/secrets/ghost_content_api_key"  # Content API key file
    version: "v5.0"  # Ghost API version
    timeout: 30  # Request timeout in seconds
```

**To create a Ghost Content API key:**
1. In Ghost Admin, go to **Settings** → **Integrations**
2. Click **Add custom integration**
3. Name it "POSSE"
4. Copy the **Content API Key**
5. Store it in a secrets file: `echo "your-key" > secrets/ghost_content_api_key.txt`

### CORS Configuration

Enable CORS to allow the widget to fetch interaction data from your blog:

```yaml
cors:
  enabled: true
  origins:
    - "https://yourblog.com"
    - "https://www.yourblog.com"  # Include www if used
```

## Installation

### Step 1: Enable in Configuration

Ensure `interactions.enabled: true` in your `config.yml` (it's enabled by default).

### Step 2: Restart POSSE

After updating the configuration, restart the POSSE service:

```bash
docker compose restart
```

or

```bash
make restart
```

### Step 3: Add Widget to Ghost

There are three methods to add the widget to your Ghost posts:

#### Method 1: Per-Post Code Injection (Quick Testing)

1. In Ghost Admin, go to your published post
2. Click Settings (gear icon)
3. Scroll to "Code Injection"
4. In the **Post Footer** section, paste the widget code
5. Replace these placeholders:
   - `POSSE_API_URL` → Your POSSE service URL (e.g., `https://posse.yourdomain.com`)
   - `POST_ID` → Your Ghost post ID (you can find this in the post URL)
6. Click "Save"

#### Method 2: Theme Integration (Recommended for All Posts)

1. Download your Ghost theme (Settings → Design → Change theme → Download current theme)
2. Extract the theme files
3. Open `post.hbs` (or your post template file)
4. Add this code where you want the widget to appear (usually before `</article>`):

```handlebars
{{!-- Social Interactions Widget --}}
<div id="social-interactions-widget" data-post-id="{{@post.id}}"></div>

{{!-- Include the widget script --}}
{{> "social-interactions-widget"}}
```

5. Copy the widget HTML file to `partials/social-interactions-widget.hbs` in your theme
6. Update the `POSSE_API_URL` in the widget code
7. Re-upload your theme to Ghost

#### Method 3: Site-Wide Code Injection (All Posts)

1. In Ghost Admin, go to Settings → Code Injection
2. In the **Site Footer** section, paste the widget code
3. Replace placeholders as in Method 1
4. Use `{{@post.id}}` for the post ID (if Ghost supports this in code injection)

### Widget Code

The complete widget code is in `widget/social-interactions-widget.html`.

Key configuration in the widget:

```javascript
const CONFIG = {
  apiUrl: 'https://your-posse-url.com/api/interactions',  // Your POSSE API URL
  postId: '{{@post.id}}',  // Or hardcode for specific posts
  refreshInterval: 300000,  // Refresh every 5 minutes
  maxRepliesShown: 5       // Max number of comments to display
};
```

## How It Works

### 1. Syndication Mapping

When POSSE syndicates a post to Mastodon or Bluesky, it stores a mapping:

```json
{
  "ghost_post_id": "abc123",
  "ghost_post_url": "https://blog.example.com/my-post/",
  "syndicated_at": "2026-01-27T08:00:00Z",
  "platforms": {
    "mastodon": {
      "personal": {
        "status_id": "123456",
        "post_url": "https://mastodon.social/@user/123456"
      }
    },
    "bluesky": {
      "main": {
        "post_uri": "at://did:plc:xyz/app.bsky.feed.post/abc",
        "post_url": "https://bsky.app/profile/user.bsky.social/post/abc"
      }
    }
  }
}
```

### 2. Interaction Syncing

The interaction scheduler:
- Runs in the background every 30 minutes (configurable)
- Retrieves interactions from Mastodon and Bluesky APIs
- Stores aggregated data in JSON files
- Uses a smart sync strategy based on post age:
  - Posts < 2 days: sync every cycle (most active)
  - Posts 2-7 days: sync every other cycle
  - Posts 7-30 days: sync every 4th cycle
  - Posts > 30 days: stop syncing

### 3. Widget Display

The JavaScript widget:
- Fetches interaction data from POSSE API
- Displays aggregated statistics
- Shows recent comments with avatars
- Auto-refreshes every 5 minutes
- Falls back gracefully if data unavailable

## API Endpoints

### GET /api/interactions/<post_id>

Retrieve interaction data for a specific post.

**Example Request:**
```bash
curl https://posse.example.com/api/interactions/abc123
```

**Example Response:**
```json
{
  "ghost_post_id": "abc123",
  "updated_at": "2026-01-27T10:00:00Z",
  "platforms": {
    "mastodon": {
      "personal": {
        "status_id": "123456",
        "post_url": "https://mastodon.social/@user/123456",
        "favorites": 42,
        "reblogs": 15,
        "replies": 8,
        "reply_previews": [
          {
            "author": "@commenter",
            "author_url": "https://mastodon.social/@commenter",
            "author_avatar": "https://...",
            "content": "Great post!",
            "created_at": "2026-01-27T09:00:00Z",
            "url": "https://mastodon.social/@commenter/789"
          }
        ]
      }
    },
    "bluesky": {
      "main": {
        "post_uri": "at://...",
        "post_url": "https://bsky.app/...",
        "likes": 38,
        "reposts": 12,
        "replies": 5,
        "reply_previews": [...]
      }
    }
  }
}
```

### POST /api/interactions/<post_id>/sync

Manually trigger a sync for a specific post.

**Example Request:**
```bash
curl -X POST https://posse.example.com/api/interactions/abc123/sync
```

**Example Response:**
```json
{
  "status": "success",
  "message": "Interactions synced successfully",
  "ghost_post_id": "abc123"
}
```

## Customization

### Styling

The widget includes default styles, but you can customize them by adding CSS to your Ghost theme or code injection:

```css
/* Change the widget background */
.social-interactions-container {
  background: linear-gradient(to bottom, #f0f0f0, #ffffff);
}

/* Change stat colors */
.engagement-summary .stat-number {
  color: #ff6b6b;
}

/* Adjust reply styling */
.reply-preview {
  border-left-width: 5px;
}
```

### Widget Configuration

Edit the `CONFIG` object in the widget JavaScript:

```javascript
const CONFIG = {
  apiUrl: 'https://your-posse-url.com/api/interactions',
  postId: document.getElementById('social-interactions-widget').dataset.postId,
  refreshInterval: 300000,  // Change refresh frequency (ms)
  maxRepliesShown: 10       // Show more/fewer comments
};
```

## Troubleshooting

### Widget Not Appearing

1. **Check if post has been syndicated:**
   ```bash
   ls data/syndication_mappings/
   ```
   You should see a file named `<post-id>.json`

2. **Check if interactions have been synced:**
   ```bash
   ls data/interactions/
   ```
   You should see a file named `<post-id>.json`

3. **Check API endpoint:**
   ```bash
   curl https://your-posse-url.com/api/interactions/<post-id>
   ```
   Should return interaction data (not 404)

4. **Check browser console:**
   Open browser developer tools (F12) and check for JavaScript errors

### No Interactions Showing

1. **Verify the post has social media interactions:**
   - Check the Mastodon/Bluesky posts directly
   - Make sure they have at least one like, repost, or reply

2. **Check sync is enabled:**
   ```yaml
   interactions:
     enabled: true
   ```

3. **Check logs:**
   ```bash
   docker logs posse-app | grep -i interaction
   ```

4. **Trigger manual sync:**
   ```bash
   curl -X POST https://your-posse-url.com/api/interactions/<post-id>/sync
   ```

### Widget Shows Old Data

1. **Check last updated timestamp** in the widget
2. **Verify scheduler is running:**
   ```bash
   docker logs posse-app | grep -i "InteractionScheduler"
   ```
3. **Manually trigger sync** to force an update
4. **Check browser cache** - try hard refresh (Ctrl+Shift+R)

## Privacy Considerations

The interaction sync feature respects the following privacy principles:

1. **Public Data Only**: Only retrieves publicly visible interactions
2. **No Authentication Required**: Uses public APIs for reading data
3. **Respects Deletions**: Re-syncs periodically, so deleted content disappears
4. **Attribution**: Always links back to original social media posts
5. **Configurable Display**: Can hide comment content or authors via config

## Performance

- **No Page Load Impact**: Widget loads asynchronously
- **Efficient Caching**: Interaction data cached as JSON files
- **Smart Syncing**: Older posts synced less frequently
- **Rate Limit Friendly**: Respects API rate limits
- **Minimal Storage**: JSON files typically < 50 KB per post

## Advanced Usage

### Custom Sync Schedule

Create a cron job to sync specific posts:

```bash
#!/bin/bash
# sync-post-interactions.sh

POST_ID="abc123"
POSSE_URL="https://posse.example.com"

curl -X POST "${POSSE_URL}/api/interactions/${POST_ID}/sync"
```

### Webhook Integration

If you want real-time updates (future enhancement), you could:
1. Set up Mastodon/Bluesky webhooks
2. Call the sync endpoint when interactions occur
3. Widget will pick up changes on next refresh

### Export Interaction Data

Interaction data is stored as JSON and can be exported:

```bash
# Copy all interaction data
tar -czf interactions-backup.tar.gz data/interactions/

# Convert to CSV (example)
jq -r '.platforms.mastodon[].favorites' data/interactions/*.json
```

## Security

- **Read-Only Operations**: Sync only reads data, never posts
- **Uses Existing Credentials**: Leverages configured API credentials
- **No User Tracking**: Does not track individual visitors
- **XSS Protection**: Comment content is HTML-escaped
- **CORS Configured**: API endpoints properly secured

## Support

If you encounter issues:

1. Check the [Architecture Document](INTERACTION_SYNC_ARCHITECTURE.md)
2. Review POSSE logs: `docker logs posse-app`
3. Test API endpoints manually with `curl`
4. Open an issue on GitHub with:
   - POSSE version
   - Configuration (redact credentials)
   - Error messages from logs
   - Steps to reproduce

## Future Enhancements

Completed:
- [x] Ghost REST API integration for post metadata
- [x] Automatic syndication mapping discovery
- [x] Webmentions support in widget
- [x] Dark mode support

Planned features:
- [ ] Database storage for better querying
- [ ] Analytics dashboard
- [ ] Real-time updates via WebSockets
- [ ] Moderation tools
- [ ] Export/import functionality
- [ ] Ghost Admin integration

## Credits

This feature is part of the POSSE project:
- **GitHub**: https://github.com/wpowiertowski/posse
- **License**: MIT
- **Author**: Wojtek Powiertowski
