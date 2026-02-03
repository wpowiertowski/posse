# Social Interactions Widget

This widget displays social media interactions (comments, likes, reposts) from Mastodon and Bluesky for syndicated Ghost blog posts, along with Webmentions.

## Screenshot

![Social Interactions Widget](./social-widget-screenshot.png)

The widget displays:
- **Social engagement section**: Shows aggregated likes, reposts, and replies from POSSE-syndicated posts
- **Responses section**: Displays Webmentions including:
  - Facepile of likes and reposts
  - Full comment threads
  - Empty state with "Reply on Mastodon/Bluesky" and "Send a Webmention" options

## Installation

### For Ghost Code Injection

1. Copy the contents of `social-interactions-widget.html`
2. In Ghost Admin, go to your post Settings > Code Injection > Post Footer
3. Paste the code
4. Replace the placeholders:
   - `POSSE_API_URL` with your POSSE service URL
   - `POST_ID` with your Ghost post ID
   - `POST_URL` with your post's absolute URL
   - `WEBMENTION_DOMAIN` with your domain

### For Ghost Theme Integration

1. Save the widget code as a partial in your theme (e.g., `partials/social-interactions.hbs`)
2. Use Handlebars variables for dynamic values:
   - `{{id}}` or `{{@post.id}}` for post ID
   - `{{url absolute="true"}}` for post URL
   - `{{@custom.posse_api_url}}` for POSSE API URL (requires custom theme setting)
   - `{{@custom.webmention_domain}}` for webmention domain

3. Include in your `post.hbs`:
   ```handlebars
   {{> "social-interactions"}}
   ```

## Features

- **POSSE Integration**: Fetches engagement stats from your POSSE service
- **Webmentions**: Displays likes, reposts, and comments via webmention.io API
- **Syndication Links**: Shows "Reply on Mastodon/Bluesky" buttons using syndication data
- **Dark Mode**: Automatic dark mode support via CSS media queries
- **Responsive**: Mobile-friendly design
- **Auto-refresh**: Updates every 5 minutes
