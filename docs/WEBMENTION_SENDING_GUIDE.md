# Webmention Sending Guide

## Overview

POSSE can send [W3C Webmentions](https://www.w3.org/TR/webmention/) to one or more targets when a post matches a configured tag. This is useful for submitting posts to aggregators like [IndieWeb News](https://news.indieweb.org/), notifying other sites, or any service that accepts webmentions.

## 1. Configuration

Add this to `config.yml`:

```yaml
webmention:
  enabled: true
  targets:
    - name: "IndieWeb News"
      endpoint: "https://news.indieweb.org/en/webmention"
      target: "https://news.indieweb.org/en"
      tag: "indiewebnews"
      timeout: 30
```

Each target has:

| Field      | Description |
|------------|-------------|
| `name`     | Human-readable label (used in logs and notifications) |
| `endpoint` | URL to POST the webmention to |
| `target`   | URL sent as the `target` parameter in the webmention |
| `tag`      | Ghost tag slug that triggers sending to this target |
| `timeout`  | Request timeout in seconds (default: 30) |

### Multiple targets

You can configure as many targets as you need. Each is independent and matched against its own tag:

```yaml
webmention:
  enabled: true
  targets:
    - name: "IndieWeb News EN"
      endpoint: "https://news.indieweb.org/en/webmention"
      target: "https://news.indieweb.org/en"
      tag: "indiewebnews"
      timeout: 30

    - name: "IndieWeb News DE"
      endpoint: "https://news.indieweb.org/de/webmention"
      target: "https://news.indieweb.org/de"
      tag: "indiewebnews-de"
      timeout: 30

    - name: "My Blogroll"
      endpoint: "https://blogroll.example.com/webmention"
      target: "https://blogroll.example.com"
      tag: "blogroll"
      timeout: 15
```

A single post can trigger multiple targets if it has multiple matching tags.

## 2. Theme Requirements (for IndieWeb News)

If you're submitting to IndieWeb News, your Ghost post HTML must expose the target as a syndication link using `u-syndication` in your h-entry markup:

```html
<a class="u-syndication" href="https://news.indieweb.org/en">IndieWeb News</a>
```

If this markup is missing, IndieWeb News may reject the webmention because it cannot confirm syndication intent. Other targets may have different requirements.

## 3. Editorial Workflow

1. Publish a Ghost post normally.
2. Add the configured tag (e.g. `indiewebnews`) to trigger submission to the matching target(s).
3. POSSE sends a webmention for each matching target after webhook processing.

Posts without any matching tag are skipped entirely.

## 4. Operational Behavior

- Webmention sending happens independently from Mastodon/Bluesky posting
- Failures do not stop the primary syndication pipeline
- Results are logged and surfaced through Pushover notifications when enabled
- Tag matching is case-insensitive

## 5. Quick Validation

Use a tagged post URL in a manual smoke test:

```bash
curl -sS "https://news.indieweb.org/en/webmention" \
  -d "source=https://yourblog.com/example-post/" \
  -d "target=https://news.indieweb.org/en"
```

Use this only for diagnostics; normal operation should happen through POSSE event processing.
