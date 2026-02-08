# IndieWeb News Guide

## Overview

POSSE can submit selected Ghost posts to [IndieWeb News](https://news.indieweb.org/) using webmentions. Submission is tag-driven and optional.

## 1. Configuration

Add this to `config.yml`:

```yaml
indieweb:
  enabled: true
  news:
    endpoint: "https://news.indieweb.org/en/webmention"
    target: "https://news.indieweb.org/en"
    tag: "indiewebnews"
    timeout: 30
```

Notes:

- `tag` is matched case-insensitively against Ghost tag slug/name
- `endpoint` and `target` can be changed for language variants (`/de`, `/fr`, etc.)

## 2. Ghost Theme Requirement

Your Ghost post HTML must expose IndieWeb News as a syndication target using `u-syndication` in your h-entry markup.

Example snippet:

```html
<a class="u-syndication" href="https://news.indieweb.org/en">IndieWeb News</a>
```

If this markup is missing, IndieWeb News may reject the webmention because it cannot confirm syndication intent.

## 3. Editorial Workflow

1. Publish a Ghost post normally.
2. Add the configured tag (default: `indiewebnews`).
3. POSSE sends a webmention for that post after webhook processing.

Posts without the configured tag are ignored by IndieWeb submission logic.

## 4. Operational Behavior

- Submission happens independently from Mastodon/Bluesky posting
- Failures do not stop the primary syndication pipeline
- Results are logged and can be surfaced through notifications when enabled

## 5. Quick Validation

Use a tagged post URL in a manual smoke test:

```bash
curl -sS "https://news.indieweb.org/en/webmention" \
  -d "source=https://yourblog.com/example-post/" \
  -d "target=https://news.indieweb.org/en"
```

Use this only for diagnostics; normal operation should happen through POSSE event processing.
