# Webmention Standard Review: Current Implementation vs W3C Spec

Review of the POSSE codebase's webmention functionality against the
[W3C Webmention Recommendation](https://www.w3.org/TR/webmention/).

---

## Current Implementation Summary

The codebase implements webmentions in two distinct roles:

### 1. Sender Role (Outbound Webmentions)

**Tag-triggered sending** (`src/indieweb/webmention.py` — `WebmentionClient`):
Posts published via Ghost webhook are matched against configured targets by tag.
For each match, a webmention POST is sent to a pre-configured endpoint.
Used for submitting to aggregators like IndieWeb News.

**Generic sending with discovery** (`src/indieweb/webmention.py` — `send_webmention()`):
Used when a reply is submitted through the reply form. Discovers the target's
webmention endpoint, then POSTs `source` + `target` per the spec.

### 2. Receiver Role (Inbound — Reply Form Only)

**Reply form** (`GET /webmention`, `POST /api/webmention/reply`, `GET /reply/<id>`):
A custom reply submission form where visitors fill in name, optional URL, and
reply text. The reply is stored in SQLite, rendered as an h-entry page, and a
webmention is sent from that page to the target post. This is *not* a standard
webmention receiver endpoint — it's a UI-driven reply flow that sends
webmentions outbound.

### 3. Display Role (Widget)

**webmention.io integration** (`widget/social-interactions.hbs`):
The Ghost theme widget fetches webmentions from the webmention.io third-party
service API and renders likes, reposts, and comments on post pages.

---

## Compliance Matrix: Current State vs W3C Standard

### Sender Requirements

| Requirement | Spec Level | Status | Notes |
|---|---|---|---|
| POST with `source` and `target` as x-www-form-urlencoded | MUST | **Implemented** | Both `WebmentionClient._send_webmention()` and `send_webmention()` |
| Discover endpoint via HTTP Link header (`rel="webmention"`) | MUST | **Implemented** | `discover_webmention_endpoint()` line 268-274 |
| Discover endpoint via HTML `<link rel="webmention">` | MUST | **Implemented** | Lines 278-292 |
| Discover endpoint via HTML `<a rel="webmention">` | MUST | **Implemented** | Lines 294-300 |
| Resolve relative endpoint URLs against target URL | MUST | **Implemented** | Uses `urljoin()` |
| Follow redirects when fetching target for discovery | MUST | **Implemented** | `allow_redirects=True` |
| Accept any 2xx as success | MUST | **Implemented** | `response.ok` checks |
| Capture Location header from 201 responses | SHOULD | **Partial** | Location is captured and logged but not used for status monitoring |
| Re-discover endpoint on each send (for updates) | MUST | **Implemented** | `send_webmention()` discovers fresh each time. `WebmentionClient` uses pre-configured endpoints (no re-discovery) |
| Preserve endpoint query parameters | MUST | **Implemented** | Endpoint URL used as-is in `requests.post()` |
| Avoid sending to localhost/loopback | SHOULD NOT | **Not implemented** | No loopback address check |
| Include "Webmention" in User-Agent | MAY | **Not implemented** | Uses default requests User-Agent |
| Respect HTTP cache headers during discovery | SHOULD | **Not implemented** | Always fetches fresh |
| Send via HEAD before GET for discovery | MAY | **Not implemented** | Always uses GET |
| Re-send webmentions when content is updated | SHOULD | **Not implemented** | Only sends on initial publish, not on post updates |
| Re-send webmentions when content is deleted | SHOULD | **Not implemented** | No delete handling |
| Send webmentions for previously-linked URLs on update | SHOULD | **Not implemented** | No link diff tracking |

### Receiver Requirements

| Requirement | Spec Level | Status | Notes |
|---|---|---|---|
| Advertise webmention endpoint (Link header or HTML tag) | MUST | **Delegated to webmention.io** | Blog posts don't advertise POSSE's own endpoint; webmention.io handles receiving |
| Accept POST with `source` and `target` parameters | MUST | **Not implemented (self-hosted)** | No standard receiver endpoint. `/api/webmention/reply` accepts form submissions, not standard webmentions |
| Validate `source` and `target` are valid URLs | MUST | **Partial** | Reply validation checks URL schemes but this isn't a standard receiver |
| Reject when source equals target | MUST | **Not implemented** | Not applicable — no receiver endpoint |
| Return 2xx for accepted webmentions | MUST | **Not applicable** | No receiver |
| Queue and process asynchronously | SHOULD | **Not applicable** | No receiver |
| Verify source by fetching it | MUST | **Not applicable** | No receiver (webmention.io does this) |
| Check source contains link to target | MUST | **Not applicable** | No receiver |
| Handle updates (same source+target, refreshed content) | SHOULD | **Not applicable** | No receiver |
| Handle deletes (source returns 410 or missing link) | SHOULD | **Not applicable** | No receiver |
| Prevent XSS in displayed content | MUST | **Implemented** | Reply rendering uses `html.escape()`. Widget sanitizes webmention.io content |
| Moderate before publishing | MAY | **Not implemented** | Replies go live immediately after validation |

### Security Measures

| Measure | Spec Level | Status | Notes |
|---|---|---|---|
| XSS prevention on displayed content | MUST | **Implemented** | `html.escape()` in reply rendering; script removal in widget |
| CSRF protection | SHOULD | **Partial** | Turnstile CAPTCHA on reply form; no CSRF token on standard endpoints |
| Rate limiting | SHOULD | **Implemented** | Per-IP rate limiting on reply submissions |
| Redirect loop protection | SHOULD | **Not implemented** | No explicit redirect limit in discovery |
| Fetch size/time limits for verification | SHOULD | **Partial** | Timeout on requests (30s) but no response size limit |
| Content encoding/filtering | MUST | **Implemented** | HTML escaping on all rendered content |

---

## Gap Analysis: Functionality Not Yet Implemented

### High Value — Standard Webmention Receiver Endpoint

**What**: A standard `POST /webmention` endpoint that accepts `source` and `target`
parameters per the W3C spec, verifies the source, and stores/displays the mention.

**Current state**: The blog relies on webmention.io as a third-party service to
receive webmentions. The POSSE `/api/webmention/reply` endpoint is a custom form
handler, not a standard receiver.

**What it would enable**:
- Self-hosted webmention receiving (no third-party dependency on webmention.io)
- Full control over webmention verification, storage, and display
- Compliance with the receiver section of the spec
- Ability to advertise your own endpoint via `<link rel="webmention">`

**Implementation scope**:
1. New `POST /webmention` endpoint accepting standard `source` + `target`
2. Async verification queue (fetch source, check it links to target)
3. Microformats parsing of source (extract author, content via mf2py)
4. New database table for received webmentions (source, target, author, content, type, verified_at)
5. Update/delete handling (re-verify on duplicate source+target; handle 410 Gone)
6. Advertise endpoint via HTTP Link header on blog responses
7. Replace or supplement webmention.io widget data with self-hosted data

### High Value — Webmention Sending on Post Updates

**What**: When a Ghost post is updated (not just initially published), re-send
webmentions to all linked URLs, including URLs that were previously linked but
have been removed.

**Current state**: Webmentions are only sent on initial publication
(`src/posse/posse.py:716-743`). Editing a post does not trigger re-sending.

**What it would enable**:
- Receivers can update their display when your content changes
- Removed links can be cleaned up by receivers
- Compliance with the sender update requirements (SHOULD)

**Implementation scope**:
1. Track previously-sent webmentions per post (source URL + target URL pairs)
2. On post update webhook, extract all outbound links from post HTML
3. Diff against previously-sent targets
4. Re-send to all current targets (updates) + previously-linked targets (removals)
5. Re-discover endpoint for each target (MUST per spec)

### High Value — Webmention Sending on Post Delete

**What**: When a post is deleted, re-send webmentions to all previously-linked
URLs so receivers know to remove/update their display.

**Current state**: No handling. Ghost `post.deleted` webhooks are not processed
for webmention purposes.

**What it would enable**:
- Clean removal of mentions when content is deleted
- Receivers see deletion markers or remove stale mentions
- Compliance with delete handling (SHOULD)

**Implementation scope**:
1. Handle `post.deleted` webhook events
2. Look up previously-sent webmention targets for the deleted post
3. Serve 410 Gone for the deleted post's URL (or rely on Ghost returning 404)
4. Re-send webmentions to all previously-notified targets

### Medium Value — Loopback/Private Network Protection (Sender)

**What**: Before sending a webmention or performing endpoint discovery, check
that the target URL does not resolve to localhost, loopback (127.0.0.0/8),
or private network addresses.

**Current state**: No check. `discover_webmention_endpoint()` and
`send_webmention()` will follow any URL.

**What it would enable**:
- Prevents SSRF (Server-Side Request Forgery) via crafted webmention targets
- Compliance with spec's SHOULD NOT for loopback
- Defense against abuse if targets are ever user-supplied

**Implementation scope**:
1. Resolve hostname to IP before request
2. Check against private/loopback ranges (127.0.0.0/8, 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16, ::1)
3. Apply to both discovery GET and webmention POST

### Medium Value — Reply Moderation Queue

**What**: Hold submitted replies in a pending state before they go live,
allowing the blog owner to approve/reject them.

**Current state**: Replies that pass validation are immediately stored and a
webmention is sent. No moderation step.

**What it would enable**:
- Spam prevention beyond rate limiting and Turnstile
- Quality control before content appears on the blog
- Compliance with spec's MAY for moderation
- Could include notification to blog owner (Pushover already integrated)

**Implementation scope**:
1. Add `status` column to `webmention_replies` (pending/approved/rejected)
2. Store replies as pending by default
3. Defer webmention sending until approved
4. Admin API endpoints for listing/approving/rejecting replies
5. Pushover notification on new pending reply

### Medium Value — Source Verification for Reply Webmentions

**What**: After sending a webmention for a reply, the target's receiver will
fetch the reply's h-entry page to verify it links to the target. Currently the
POSSE side does this correctly (serves the h-entry). But if a receiver sends a
webmention *back* to POSSE (e.g., a Salmention), there's no endpoint to receive it.

**Current state**: No incoming webmention verification. Relies entirely on
webmention.io for receiving.

### Medium Value — Redirect Limit on Discovery

**What**: Limit the number of HTTP redirects followed during endpoint discovery
to prevent infinite redirect loops.

**Current state**: `requests.get()` follows redirects with no explicit limit
(requests library default is 30, which is reasonable but not spec-compliant
with the suggested 20).

**Implementation scope**:
1. Set `max_redirects` on the requests Session to 20
2. Handle `TooManyRedirects` exception

### Medium Value — Response Size Limit on Discovery

**What**: Limit the amount of data downloaded when fetching a target URL for
endpoint discovery or verification.

**Current state**: No size limit. A malicious or large target could cause the
server to download unlimited data.

**Implementation scope**:
1. Stream the response and read in chunks
2. Abort after a configured limit (e.g., 1MB)
3. Apply to both `discover_webmention_endpoint()` and any future verification

### Low Value — Webmention User-Agent String

**What**: Include "Webmention" in the User-Agent header when making discovery
and sending requests.

**Current state**: Uses default `python-requests` User-Agent.

**What it would enable**:
- Better identification in target server logs
- Compliance with MAY recommendation
- Helps targets distinguish webmention traffic

**Implementation scope**:
1. Set `User-Agent: Webmention (POSSE; +https://yourblog.com)` on requests

### Low Value — HTTP Cache Respect During Discovery

**What**: Honor HTTP cache headers (Cache-Control, Expires, ETag) when fetching
target URLs for endpoint discovery.

**Current state**: Always fetches fresh.

**What it would enable**:
- Reduced load on target servers during repeated sends
- Compliance with SHOULD

**Implementation scope**:
1. Use `requests-cache` or manual caching layer
2. Respect Cache-Control max-age and ETag/If-None-Match

### Low Value — HEAD-Before-GET Discovery Optimization

**What**: Send an HTTP HEAD request first to check for a Link header before
downloading the full HTML.

**Current state**: Always does full GET.

**What it would enable**:
- Faster discovery when endpoint is in Link header (avoids downloading HTML)
- Reduced bandwidth

**Implementation scope**:
1. HEAD request first, check Link header
2. Fall back to GET only if no Link header found

### Low Value — Content Negotiation on Verification

**What**: Include an Accept header indicating preferred content types when
verifying source URLs, and handle verification differently per media type
(HTML: check href attributes; JSON: exact URL match in values; plain text:
string search).

**Current state**: Discovery uses `Accept: text/html`. No multi-format
verification since there's no receiver.

**Relevance**: Only matters if self-hosted receiver is implemented.

---

## Extensions Referenced in the Spec

| Extension | Description | Relevance |
|---|---|---|
| **Vouch** | Anti-spam: requires a "vouch" URL from a trusted third party | Medium — would help with spam on a self-hosted receiver |
| **Salmention** | Propagates replies upstream (notify original post when someone replies to a reply) | Low — niche use case |
| **Private Webmention** | Support for access-controlled posts | Low — Ghost posts are typically public |

---

## Recommendations (Prioritized)

### Immediate / Low-Effort Improvements

1. **Loopback address check** on sender — prevents SSRF, small code change
2. **Redirect limit** on discovery — set `max_redirects=20` on requests Session
3. **Response size limit** on discovery — stream with 1MB cap
4. **Webmention User-Agent** — one-line header change

### Medium-Term Features

4. **Send on post update** — requires link tracking + Ghost update webhook handling
5. **Send on post delete** — requires sent-webmention tracking + delete webhook
6. **Reply moderation queue** — status column + admin endpoints + Pushover alerts

### Longer-Term / Architectural

7. **Self-hosted webmention receiver** — full receiver endpoint with async verification, microformats parsing, storage, and display. This is the largest gap vs the standard but also the largest undertaking. The current webmention.io delegation is a reasonable approach for the current architecture.

---

## Architecture Context

The current split — webmention.io for receiving, POSSE for sending and reply
forms — is a pragmatic choice. webmention.io handles the complex receiver
responsibilities (endpoint advertisement, source verification, content extraction,
spam filtering). POSSE handles the sender role and a custom reply form that
works *with* webmention.io's infrastructure.

Moving to a fully self-hosted receiver would eliminate the webmention.io
dependency but would require implementing endpoint advertisement, async
verification queuing, microformats parsing (via mf2py), content extraction,
spam filtering, and a migration path for existing webmention.io data.
