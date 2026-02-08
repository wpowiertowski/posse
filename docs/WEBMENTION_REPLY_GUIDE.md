# Webmention Reply Guide

## Overview

POSSE can host a webmention reply form for readers who do not run their own IndieWeb-enabled site. Submitted replies are:

1. validated
2. stored in SQLite
3. published as a reply page (`/reply/<id>`) with microformats
4. sent as a webmention to the target post

## 1. Configuration

Add these sections to `config.yml`.

```yaml
timezone: "UTC"

ghost:
  content_api:
    url: "https://yourblog.com"
    key_file: "/run/secrets/ghost_content_api_key"
    version: "v5.0"
    timeout: 30

interactions:
  cache_directory: "./data"

webmention_reply:
  enabled: true
  blog_name: "Your Blog"
  allowed_target_origins:
    - "https://yourblog.com"
  rate_limit: 5
  rate_limit_window_seconds: 3600
  turnstile_site_key: ""
  # turnstile_secret_key_file: "/run/secrets/turnstile_secret_key"
```

Important requirements:

- `ghost.content_api` should be configured; reply target validation depends on it
- `allowed_target_origins` must include every canonical origin you want to accept
- `interactions.cache_directory` controls where `interactions.db` is stored

## 2. Endpoints

- `GET /webmention?url=<target-post-url>`: render the reply form for a specific target URL
- `POST /api/webmention/reply`: accept JSON submission, store reply, start async webmention send
- `GET /reply/<reply_id>`: serve a stored reply as an h-entry source page

Submission payload fields:

- `author_name` (required)
- `author_url` (optional)
- `content` (required)
- `target` (required)
- `website` (honeypot field, should be empty)
- `cf-turnstile-response` (required only when Turnstile is enabled)

## 3. Validation and Abuse Controls

POSSE applies layered checks:

- Target URL scheme/domain validation against `allowed_target_origins`
- Canonical target verification through Ghost Content API lookup by slug
- Per-IP rate limiting (`rate_limit` / `rate_limit_window_seconds`)
- Honeypot detection for bots
- Optional Cloudflare Turnstile verification

If target verification is unavailable (for example Ghost Content API is down), submissions are refused.

## 4. Reply Storage and Delivery

Replies are persisted in `interactions.db` table `webmention_replies`.

After storing a reply, POSSE asynchronously sends a webmention:

- Source: `<target-origin>/reply/<reply_id>`
- Target: submitted target post URL

If webmention delivery fails with a 4xx refusal from `webmention.io`, POSSE removes the stored reply to avoid publishing invalid source pages.

## 5. Theme and Rendering

Recent reply updates make rendered pages align with your Ghost theme:

- Form page can inject Ghost CSS and Montserrat font from allowed origins
- Reply page reuses shared form style blocks when available
- Reply pages include `h-entry`, `h-card`, and `u-in-reply-to` microformats

Security headers are set on both form and reply pages, including CSP, `X-Frame-Options`, and `X-Content-Type-Options`.

## 6. Add a Link from Ghost Posts

Add a link in your Ghost post template pointing to POSSE:

```handlebars
<a href="https://posse.yourdomain.com/webmention?url={{url absolute='true'}}">
  Send a Webmention
</a>
```

Readers open that link, submit a reply, and POSSE handles source page publishing and webmention delivery.

## 7. Quick Verification

Form render:

```bash
curl -sS "https://posse.yourdomain.com/webmention?url=https://yourblog.com/your-post/" -o /tmp/reply_form.html
```

Reply page (after submission):

```bash
curl -sS "https://posse.yourdomain.com/reply/<reply_id>" -o /tmp/reply_page.html
```
