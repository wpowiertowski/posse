# Social Interaction Sync Architecture

## Overview

This document outlines the architecture for syncing interactions (comments, boosts/reposts, and favorites/likes) from syndicated posts on Mastodon and Bluesky back to Ghost blog posts.

## Problem Statement

Currently, POSSE syndicates Ghost blog posts to Mastodon and Bluesky, but there's no way for readers to see the social media engagement on the original Ghost post. This creates a fragmented conversation where:
- Comments on Mastodon/Bluesky are invisible to Ghost readers
- Ghost readers can't see how many people liked/boosted the post
- The original blog post appears inactive even when generating social engagement

## Goals

1. **Retrieve interactions** from Mastodon and Bluesky posts
2. **Store interaction data** efficiently for display
3. **Display interactions** in a widget on Ghost posts
4. **Update periodically** to show recent engagement
5. **Maintain privacy** and respect user preferences

## Architecture Components

### 1. Interaction Retrieval Service

A new service that polls social media platforms for interactions on syndicated posts.

```python
# src/interactions/interaction_sync.py
class InteractionSyncService:
    """
    Retrieves interactions from Mastodon and Bluesky posts
    and stores them for display in Ghost.
    """

    def sync_post_interactions(self, ghost_post_id: str) -> Dict[str, Any]:
        """
        Sync interactions for a specific Ghost post.

        Returns:
        {
            "mastodon": {
                "account_name": {
                    "post_url": "...",
                    "favorites": 10,
                    "reblogs": 5,
                    "replies": 3,
                    "reply_previews": [...]
                }
            },
            "bluesky": {
                "account_name": {
                    "post_url": "...",
                    "likes": 15,
                    "reposts": 7,
                    "replies": 4,
                    "reply_previews": [...]
                }
            }
        }
        """
```

#### Mastodon Integration

Using the existing `Mastodon.py` library:

```python
# Get status by ID
status = mastodon_api.status(status_id)

# Get favorites count and users
favorites = mastodon_api.status_favourited_by(status_id)

# Get reblogs count and users
reblogs = mastodon_api.status_reblogged_by(status_id)

# Get context (replies)
context = mastodon_api.status_context(status_id)
```

#### Bluesky Integration

Using the existing `atproto` library:

```python
# Get post thread
thread = client.app.bsky.feed.get_post_thread({
    'uri': post_uri
})

# Get likes
likes = client.app.bsky.feed.get_likes({
    'uri': post_uri,
    'limit': 100
})

# Get reposts
reposts = client.app.bsky.feed.get_reposted_by({
    'uri': post_uri,
    'limit': 100
})
```

### 2. Data Storage

Store interaction data in SQLite:

- Database file: `<cache_directory>/interactions.db`
- `interaction_data` table contains one normalized JSON payload per Ghost post
- API responses are served from SQLite-backed reads

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
            "content": "Great post!",
            "created_at": "2026-01-27T09:00:00Z",
            "url": "https://mastodon.social/@commenter/789"
          }
        ]
      }
    },
    "bluesky": {
      "main": {
        "post_uri": "at://did:plc:xyz/app.bsky.feed.post/abc",
        "post_url": "https://bsky.app/profile/user.bsky.social/post/abc",
        "likes": 38,
        "reposts": 12,
        "replies": 5,
        "reply_previews": [...]
      }
    }
  }
}
```

#### Storage Model (Implemented)
- SQLite database for both interaction payloads and syndication mappings
- Database file: `<cache_directory>/interactions.db`
- Tables: `interaction_data`, `syndication_mappings`
- Payloads are JSON blobs validated against `src/schema/interactions_db_schema.json`

### 3. Mapping System

We need to map Ghost posts to their syndicated social media posts. This requires storing the relationship when posts are syndicated.

**Enhancement to existing syndication flow**:

```python
# In src/posse/posse.py, after successful posting:
def _syndicate_to_social_media(post_data):
    # ... existing code ...

    # After posting to Mastodon
    if result:
        _store_syndication_mapping(
            ghost_post_id=post_id,
            platform="mastodon",
            account=account_name,
            post_id=result['id'],
            post_url=result['url']
        )

    # After posting to Bluesky
    if result:
        _store_syndication_mapping(
            ghost_post_id=post_id,
            platform="bluesky",
            account=account_name,
            post_uri=result['uri'],
            post_url=construct_bluesky_url(result['uri'])
        )
```

Store mappings in SQLite table `syndication_mappings` (payload shape shown below):

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

### 4. Sync Scheduler

A background task that periodically syncs interactions:

```python
# src/interactions/scheduler.py
class InteractionScheduler:
    """
    Periodically syncs interactions for syndicated posts.
    """

    def __init__(self, sync_interval_minutes=30):
        self.sync_interval = sync_interval_minutes

    def run(self):
        """
        Main loop that syncs all tracked posts.
        """
        while True:
            self._sync_all_posts()
            time.sleep(self.sync_interval * 60)

    def _sync_all_posts(self):
        """
        Sync interactions for all posts with syndication mappings.
        """
        # Read all mapping files
        # For each post, sync interactions
        # Store updated interaction data
```

**Sync Strategy**:
- Sync new posts every 30 minutes for the first 48 hours
- Then reduce to every 6 hours for posts 2-7 days old
- Then once daily for posts 7-30 days old
- Stop syncing posts older than 30 days (configurable)

### 5. API Endpoints

Add new endpoints to the Flask app:

```python
# In src/ghost/ghost.py

@app.route("/api/interactions/<ghost_post_id>", methods=["GET"])
def get_interactions(ghost_post_id):
    """
    Retrieve interactions for a specific Ghost post.

    Returns JSON with all interactions from Mastodon and Bluesky.
    """

@app.route("/api/interactions/<ghost_post_id>/sync", methods=["POST"])
def trigger_sync(ghost_post_id):
    """
    Manually trigger a sync for a specific post.

    Useful for immediate updates or testing.
    """
```

### 6. Ghost Widget

A JavaScript widget that embeds in Ghost posts to display interactions.

#### Widget HTML/JS (Ghost Code Injection)

```html
<div id="social-interactions" data-post-id="{{post.id}}"></div>

<script>
(function() {
  const postId = document.getElementById('social-interactions').dataset.postId;
  const apiUrl = 'https://posse.example.com/api/interactions/' + postId;

  // Fetch interactions
  fetch(apiUrl)
    .then(response => response.json())
    .then(data => renderInteractions(data))
    .catch(error => console.error('Failed to load interactions:', error));

  function renderInteractions(data) {
    const container = document.getElementById('social-interactions');

    // Calculate totals
    const totals = calculateTotals(data);

    // Render summary
    let html = '<div class="social-interactions-widget">';
    html += '<h3>Social Media Engagement</h3>';
    html += '<div class="engagement-summary">';
    html += `<span class="stat"><strong>${totals.likes}</strong> likes</span>`;
    html += `<span class="stat"><strong>${totals.reposts}</strong> reposts</span>`;
    html += `<span class="stat"><strong>${totals.replies}</strong> replies</span>`;
    html += '</div>';

    // Render platform-specific engagement
    if (data.platforms.mastodon) {
      html += renderMastodonSection(data.platforms.mastodon);
    }
    if (data.platforms.bluesky) {
      html += renderBlueskySection(data.platforms.bluesky);
    }

    // Render recent replies
    html += renderReplies(data);
    html += '</div>';

    container.innerHTML = html;
  }

  function calculateTotals(data) {
    // Calculate aggregate stats across platforms
    // ...
  }

  function renderMastodonSection(mastodon) {
    // Render Mastodon-specific engagement
    // ...
  }

  function renderBlueskySection(bluesky) {
    // Render Bluesky-specific engagement
    // ...
  }

  function renderReplies(data) {
    // Render recent replies from both platforms
    // ...
  }
})();
</script>

<style>
.social-interactions-widget {
  border: 1px solid #e1e8ed;
  border-radius: 8px;
  padding: 20px;
  margin: 30px 0;
  background: #f7f9fa;
}

.social-interactions-widget h3 {
  margin-top: 0;
  color: #14171a;
}

.engagement-summary {
  display: flex;
  gap: 20px;
  margin: 15px 0;
}

.engagement-summary .stat {
  padding: 10px 15px;
  background: white;
  border-radius: 4px;
  font-size: 14px;
}

/* Platform sections */
.platform-section {
  margin: 20px 0;
  padding: 15px;
  background: white;
  border-radius: 4px;
}

.platform-section h4 {
  margin-top: 0;
  display: flex;
  align-items: center;
  gap: 8px;
}

/* Reply previews */
.reply-preview {
  border-left: 3px solid #1da1f2;
  padding: 10px 15px;
  margin: 10px 0;
  background: white;
}

.reply-author {
  font-weight: bold;
  color: #1da1f2;
  text-decoration: none;
}

.reply-content {
  margin: 5px 0;
  color: #14171a;
}

.reply-time {
  font-size: 12px;
  color: #657786;
}
</style>
```

#### Ghost Integration Methods

**Method 1: Per-Post Code Injection**
- In Ghost admin, edit post
- Go to Settings → Code Injection → Post Footer
- Paste the widget HTML/JS/CSS
- Replace `{{post.id}}` with actual post ID

**Method 2: Theme Integration** (Better for site-wide)
- Modify Ghost theme template
- Add widget to `post.hbs` template
- Widget automatically appears on all posts

**Method 3: Ghost API + Custom Field**
- Store syndication URLs in Ghost's custom fields
- Use Ghost Content API to retrieve and display

**Recommendation**: Start with Method 1 for testing, then move to Method 2 for production.

## Implementation Plan

### Phase 1: Core Infrastructure (Week 1)
1. Create syndication mapping storage
2. Modify syndication flow to store mappings
3. Create interaction sync service
4. Add API endpoints for retrieving interactions

### Phase 2: Data Collection (Week 2)
1. Implement Mastodon interaction retrieval
2. Implement Bluesky interaction retrieval
3. Persist interaction and mapping payloads in SQLite
4. Add sync scheduler with configurable intervals

### Phase 3: Widget Development (Week 3)
1. Create basic widget HTML/CSS/JS
2. Implement interaction display
3. Add platform-specific styling
4. Create documentation for Ghost integration

### Phase 4: Testing & Polish (Week 4)
1. Test with real posts and interactions
2. Optimize sync frequency
3. Add error handling and fallbacks
4. Create user documentation

## Configuration

Add to `config.yml`:

```yaml
interactions:
  enabled: true
  sync_interval_minutes: 30
  sync_recent_posts_only: true
  max_post_age_days: 30
  max_replies_per_post: 10
  cache_directory: "./data"  # interactions.db lives here

  # Privacy settings
  show_reply_content: true
  show_reply_authors: true
  anonymize_after_days: 0  # 0 = never anonymize
```

## Privacy Considerations

1. **Public Data Only**: Only retrieve publicly available interactions
2. **Respect Deletions**: Periodically re-sync to respect deleted content
3. **User Control**: Allow users to opt-out (though this is tricky)
4. **Data Retention**: Configurable retention period
5. **Attribution**: Always link back to original posts

## Performance Considerations

1. **Caching**: Cache interaction data, don't fetch on every page load
2. **Rate Limiting**: Respect API rate limits (Mastodon: 300/5min, Bluesky: varies)
3. **Lazy Loading**: Widget loads asynchronously, doesn't block page render
4. **Stale Data Acceptable**: Interactions don't need real-time updates
5. **Batch Syncing**: Sync multiple posts in one cycle

## Security Considerations

1. **API Credentials**: Use existing credential management
2. **CORS**: Configure appropriate CORS headers for API endpoints
3. **Input Validation**: Validate all user-generated content from replies
4. **XSS Protection**: Sanitize reply content before display
5. **Rate Limiting**: Implement rate limiting on API endpoints

## Implemented Enhancements

The following planned enhancements have been implemented:

1. **Ghost REST API Integration**: Posts are now retrieved via Ghost Content API for automatic syndication discovery
2. **CORS Support**: Configurable CORS for cross-origin API access from widgets
3. **Automatic Syndication Discovery**: Discovers mappings for posts syndicated before interaction sync was enabled
4. **Webmentions Support**: Widget displays likes, reposts, and comments from webmention.io
5. **Dark Mode**: Widget supports automatic dark mode via CSS media queries
6. **SQLite-only Runtime Storage**: interactions and mappings are stored/retrieved exclusively from `interactions.db`

## Future Enhancements

1. **Reply Threading**: Show full conversation threads
2. **Analytics Dashboard**: Visualize engagement over time
3. **Ghost Admin Integration**: Manage from Ghost admin panel
4. **Notification System**: Alert on high engagement
5. **Moderation Tools**: Hide/block specific interactions
6. **Export/Import**: Backup interaction data
7. **WebSub/Webhooks**: Real-time updates instead of polling

## Technical Dependencies

No new dependencies required! Uses existing:
- `Mastodon.py` - For Mastodon API calls
- `atproto` - For Bluesky API calls
- `Flask` - For API endpoints
- `requests` - For HTTP operations

## Testing Strategy

1. **Unit Tests**: Test each component in isolation
2. **Integration Tests**: Test full sync flow
3. **Mock APIs**: Use mocked responses for testing
4. **Real Data Tests**: Test with actual Mastodon/Bluesky accounts
5. **Widget Tests**: Test widget rendering in various browsers

## Documentation Requirements

1. **Setup Guide**: How to enable interaction sync
2. **Ghost Integration Guide**: How to add widget to posts
3. **Configuration Reference**: All config options explained
4. **API Documentation**: Endpoint specifications
5. **Troubleshooting Guide**: Common issues and solutions

## Success Metrics

1. Interaction sync runs without errors
2. Widget displays correctly in Ghost
3. Data updates within configured interval
4. No performance impact on Ghost site
5. Respects all API rate limits

## Conclusion

This architecture provides a complete solution for syncing social media interactions back to Ghost posts. It leverages existing infrastructure, requires no new dependencies, and provides a clean separation of concerns.

The SQLite payload-store approach keeps runtime storage simple while supporting future enhancements like analytics and real-time updates.

The Ghost widget is self-contained and can be easily integrated using Ghost's built-in code injection features, making it accessible to users without requiring theme modifications.
