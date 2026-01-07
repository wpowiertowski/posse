# Multi-Account Integration Guide

This document describes how to integrate the new multi-account filtering functionality into the Ghost webhook flow.

## Overview

The multi-account support with filters has been fully implemented and tested. To complete the integration, the Ghost webhook receiver needs to be updated to:

1. Load multi-account clients
2. Filter posts for each account
3. Post to matching accounts

## Implementation Steps

### Step 1: Update Ghost Webhook Receiver

Modify `src/ghost/ghost.py` to use multi-account clients:

```python
from mastodon_client.mastodon_client import MastodonClient
from social.filters import get_matching_accounts

# In create_app() function, after loading config:
config = load_config()

# Load all Mastodon clients
mastodon_clients = MastodonClient.from_config_multi(config)
app.config['MASTODON_CLIENTS'] = mastodon_clients

# Similarly for Bluesky when implemented
# bluesky_clients = BlueskyClient.from_config_multi(config)
# app.config['BLUESKY_CLIENTS'] = bluesky_clients
```

### Step 2: Filter and Post in Webhook Handler

Update the `receive_ghost_post()` function:

```python
@app.route('/webhook/ghost', methods=['POST'])
def receive_ghost_post():
    # ... existing validation code ...
    
    # Get clients from config
    mastodon_clients = current_app.config.get('MASTODON_CLIENTS', [])
    
    # Get accounts configuration for filtering
    config = load_config()
    mastodon_accounts_config = config.get('mastodon', {}).get('accounts', [])
    
    if mastodon_accounts_config:
        # Multi-account mode: filter and post to matching accounts
        matching_accounts = get_matching_accounts(payload, mastodon_accounts_config)
        
        for i, account_config in enumerate(matching_accounts):
            account_name = account_config.get('name', 'unnamed')
            
            # Find corresponding client
            if i < len(mastodon_clients) and mastodon_clients[i].enabled:
                client = mastodon_clients[i]
                
                # Format post content (customize as needed)
                post_content = format_post_for_mastodon(post_data)
                
                # Post to this account
                result = client.post(post_content)
                if result:
                    logger.info(f"Posted to Mastodon account '{account_name}': {result.get('url')}")
                else:
                    logger.error(f"Failed to post to Mastodon account '{account_name}'")
    
    # ... rest of existing code ...
```

### Step 3: Create Post Formatting Function

Add a helper function to format Ghost posts for social media:

```python
def format_post_for_mastodon(post_data: Dict[str, Any]) -> str:
    """Format a Ghost post for Mastodon.
    
    Args:
        post_data: Ghost post current data
        
    Returns:
        Formatted string suitable for Mastodon post
    """
    title = post_data.get('title', '')
    url = post_data.get('url', '')
    excerpt = post_data.get('excerpt', '')
    
    # Customize format as needed
    # Example: "Title\n\nExcerpt...\n\nRead more: URL"
    
    # Mastodon has a 500 character limit (most instances)
    post = f"{title}\n\n{excerpt}\n\nRead more: {url}"
    
    # Truncate if needed
    if len(post) > 450:  # Leave room for URL
        post = post[:447] + "..."
    
    return post
```

## Testing the Integration

### Manual Testing

1. **Setup test secrets:**
   ```bash
   mkdir -p secrets
   echo "your_test_token" > secrets/mastodon_test_access_token.txt
   ```

2. **Configure test account:**
   ```yaml
   # config.yml
   mastodon:
     accounts:
       - name: "test"
         instance_url: "https://mastodon.social"
         access_token_file: "/run/secrets/mastodon_test_access_token"
         filters:
           tags: ["test"]  # Only posts with "test" tag
   ```

3. **Send test webhook:**
   ```bash
   curl -X POST http://localhost:5000/webhook/ghost \
     -H "Content-Type: application/json" \
     -d @tests/fixtures/valid_ghost_post.json
   ```

### Unit Testing

Add tests in `tests/test_ghost.py`:

```python
def test_ghost_webhook_with_multi_account_mastodon(self):
    """Test webhook with multi-account Mastodon posting."""
    # Mock MastodonClient.from_config_multi
    # Send webhook request
    # Verify correct accounts were called based on filters
```

## Configuration Examples

### Example 1: Personal and Professional Accounts

```yaml
mastodon:
  accounts:
    - name: "personal"
      instance_url: "https://mastodon.social"
      access_token_file: "/run/secrets/mastodon_personal_access_token"
      filters:
        tags: ["personal", "photography", "travel"]
    
    - name: "professional"
      instance_url: "https://fosstodon.org"
      access_token_file: "/run/secrets/mastodon_professional_access_token"
      filters:
        tags: ["tech", "security"]
        exclude_tags: ["personal"]
```

### Example 2: Public vs Members-Only Content

```yaml
mastodon:
  accounts:
    - name: "public"
      instance_url: "https://mastodon.social"
      access_token_file: "/run/secrets/mastodon_public_access_token"
      filters:
        visibility: ["public"]
    
    - name: "supporters"
      instance_url: "https://mastodon.social"
      access_token_file: "/run/secrets/mastodon_supporters_access_token"
      filters:
        visibility: ["members", "paid"]
```

## Troubleshooting

### No Posts Being Syndicated

1. Check filter configuration - empty filters (`{}`) match all posts
2. Verify tags in Ghost posts match filter tags exactly (slug format)
3. Check logs for filter matching debug messages
4. Ensure at least one account has filters that match your posts

### Posts Going to Wrong Accounts

1. Review `exclude_tags` - they take precedence over `tags`
2. Remember: within `tags` filter, ANY tag matches (OR logic)
3. All other filters must match (AND logic)
4. Check account order - posts are processed in order

### Authentication Errors

1. Verify secret files exist and are readable
2. Check secret file paths in config match Docker Compose
3. Ensure access tokens have `write:statuses` scope
4. Test tokens directly in Mastodon UI

## Performance Considerations

- Tag extraction is optimized (computed once per filter check)
- Filters are evaluated sequentially (short-circuit on first failure)
- Consider rate limits when posting to multiple accounts
- Add delays between posts if needed

## Security Notes

- Never log access tokens
- Keep secret files outside version control
- Use Docker secrets in production
- Rotate tokens periodically
- Use minimal scopes (`write:statuses` only)

## Future Enhancements

- [ ] Add retry logic for failed posts
- [ ] Add rate limiting between posts
- [ ] Support for media attachments
- [ ] Custom post templates per account
- [ ] Post scheduling/queueing
- [ ] Analytics and reporting
