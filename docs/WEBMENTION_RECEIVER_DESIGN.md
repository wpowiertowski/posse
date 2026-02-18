# Design Plan: Self-Hosted Webmention Receiver

Detailed design for implementing a W3C-compliant webmention receiver
endpoint in POSSE, replacing the dependency on webmention.io for
receiving webmentions from external sites.

**Status**: Design plan (not yet implemented)
**Spec Reference**: [W3C Webmention Recommendation](https://www.w3.org/TR/webmention/)
**Related Code**: Existing sender in `src/indieweb/webmention.py`, storage in
`src/interactions/storage.py`, routes in `src/ghost/ghost.py`

---

## 1. Goals

1. Accept standard webmentions via `POST /webmention` with `source` + `target`
2. Verify that the source URL actually links to the target
3. Extract content from source pages (author, text, type) via microformats2
4. Store verified webmentions in SQLite
5. Serve webmentions via API for the Ghost theme widget
6. Advertise the endpoint via HTTP Link header on blog responses
7. Handle updates (same source+target, new content) and deletes (410 Gone / missing link)
8. Maintain equivalent abuse protection to the existing webmention.io setup

**Non-goals for initial implementation**:
- Vouch extension (third-party vouching)
- Salmention extension (upstream reply propagation)
- Private Webmention (access-controlled posts)
- Real-time WebSocket push of new mentions

---

## 2. Architecture Overview

```
                       ┌──────────────────────┐
                       │  External Site        │
                       │  sends webmention     │
                       └──────────┬───────────┘
                                  │ POST /webmention
                                  │ source=...&target=...
                                  ▼
┌─────────────────────────────────────────────────────────────┐
│  Flask Route: POST /webmention                              │
│                                                             │
│  1. Validate source + target are valid URLs                 │
│  2. Reject if source == target                              │
│  3. Validate target is a URL we own (allowed origins)       │
│  4. Return 202 Accepted (async processing)                  │
│  5. Queue verification task                                 │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│  Verification Worker (background thread)                    │
│                                                             │
│  1. SSRF check on source URL                                │
│  2. Fetch source URL (GET, with size/redirect limits)       │
│  3. Check HTTP status:                                      │
│     - 410 Gone → delete existing mention (if any)           │
│     - 4xx/5xx → reject                                      │
│     - 2xx → continue                                        │
│  4. Check source HTML contains link to target               │
│     - If no link found → delete existing mention            │
│  5. Parse microformats2 (mf2py) from source                 │
│  6. Extract: author name, author URL, author photo,         │
│     content (text + html), mention type (reply/like/repost) │
│  7. Upsert into received_webmentions table                  │
│  8. Optional: send Pushover notification                    │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  API: GET /api/webmentions/<post_url_or_id>                 │
│                                                             │
│  Returns JSON array of verified webmentions for a post:     │
│  [{author, content, type, source_url, verified_at}, ...]    │
│  Consumed by Ghost theme widget (replaces webmention.io)    │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  Endpoint Advertisement                                      │
│                                                             │
│  HTTP response header on all blog pages:                    │
│  Link: <https://posse.example.com/webmention>; rel="webmention" │
│                                                             │
│  (Added via Ghost theme or reverse proxy, not POSSE itself) │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. Database Schema

New table in the existing `interactions.db` SQLite database.

```sql
CREATE TABLE IF NOT EXISTS received_webmentions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- The page that mentions us (external URL)
    source_url TEXT NOT NULL,

    -- Our page being mentioned
    target_url TEXT NOT NULL,

    -- Mention type: reply, like, repost, mention, bookmark
    mention_type TEXT NOT NULL DEFAULT 'mention',

    -- Author info (extracted from microformats)
    author_name TEXT,
    author_url TEXT,
    author_photo TEXT,

    -- Content (extracted from microformats)
    content_text TEXT,     -- plain text
    content_html TEXT,     -- sanitized HTML (for rich display)

    -- Verification state
    status TEXT NOT NULL DEFAULT 'pending',
    -- status values: pending, verified, deleted

    -- Timestamps
    received_at TEXT NOT NULL,   -- when the webmention POST arrived
    verified_at TEXT,            -- when source was last fetched and verified
    updated_at TEXT,             -- when content was last changed

    -- Uniqueness: one mention per source+target pair
    UNIQUE(source_url, target_url)
);

CREATE INDEX IF NOT EXISTS idx_rwm_target ON received_webmentions(target_url);
CREATE INDEX IF NOT EXISTS idx_rwm_status ON received_webmentions(status);
CREATE INDEX IF NOT EXISTS idx_rwm_received ON received_webmentions(received_at);
```

### Why this schema

- **UNIQUE(source_url, target_url)**: The W3C spec says a receiver should
  update an existing mention when it receives the same source+target pair
  again. This constraint enables upsert behavior.
- **status field**: Tracks the lifecycle: `pending` (received, not yet verified),
  `verified` (source confirmed to link to target), `deleted` (source returned
  410 or no longer links to target).
- **mention_type**: Determined by microformats parsing. A source with
  `class="h-entry"` containing `u-like-of` pointing to our target is a "like";
  `u-repost-of` is a "repost"; `u-in-reply-to` is a "reply"; anything else
  with a plain `<a>` link is a "mention".

---

## 4. New Module: `src/indieweb/receiver.py`

### 4.1 Receive Endpoint Logic

```python
def validate_webmention_request(source: str, target: str, allowed_origins: list[str]) -> list[str]:
    """Validate incoming webmention parameters.

    Checks per W3C spec Section 3.2.1:
    - source and target are valid HTTP(S) URLs
    - source != target
    - target is a URL we own (origin matches allowed_origins)

    Returns list of error strings (empty = valid).
    """
```

### 4.2 Verification Logic

```python
def verify_webmention(source_url: str, target_url: str) -> VerificationResult:
    """Fetch source URL and verify it links to target.

    Steps per W3C spec Section 3.2.2:
    1. SSRF check (reuse _is_private_or_loopback from webmention.py)
    2. HTTP GET source_url with:
       - User-Agent containing "Webmention"
       - Max 20 redirects
       - Response size limit (1 MB)
       - Timeout (30s)
    3. Handle HTTP status:
       - 410 Gone → return VerificationResult(status="deleted")
       - Other non-2xx → return VerificationResult(status="rejected")
    4. Parse response body for link to target:
       - HTML: check href attributes of <a>, <link>, etc.
       - JSON: check if target URL appears as a value
       - Plain text: string search
    5. If no link found → return VerificationResult(status="deleted")
    6. Parse microformats2 for content extraction
    7. Return VerificationResult(status="verified", content=...)

    Returns VerificationResult with status and extracted content.
    """
```

### 4.3 Microformats Parsing

```python
def extract_mention_data(mf2_data: dict, target_url: str) -> MentionData:
    """Extract author, content, and mention type from mf2 parsed data.

    Determines mention type by checking h-entry properties:
    - u-like-of containing target → "like"
    - u-repost-of containing target → "repost"
    - u-bookmark-of containing target → "bookmark"
    - u-in-reply-to containing target → "reply"
    - Otherwise → "mention"

    Extracts author from p-author h-card:
    - p-name → author_name
    - u-url → author_url
    - u-photo → author_photo

    Extracts content from e-content (HTML) and p-content (text),
    with sanitization to prevent XSS.
    """
```

### 4.4 Content Sanitization

```python
def sanitize_mention_html(html: str, max_length: int = 2000) -> str:
    """Sanitize HTML content from webmention source.

    Per W3C spec security considerations:
    - Strip all tags except: p, br, a, strong, em, blockquote, code, pre
    - Remove all attributes except href on <a> tags
    - Add rel="nofollow noopener" to all links
    - Truncate to max_length
    - HTML-escape any remaining special characters
    """
```

---

## 5. Flask Routes

### 5.1 Receiver Endpoint

```
POST /webmention
Content-Type: application/x-www-form-urlencoded

source=https://external.example.com/post&target=https://myblog.com/my-article/
```

**Response codes**:
- `202 Accepted` — webmention queued for async verification
- `400 Bad Request` — missing/invalid source or target, or source == target
- `400 Bad Request` — target is not a URL we own
- `429 Too Many Requests` — rate limited

**Response body** (202):
```json
{
  "status": "accepted",
  "message": "Webmention queued for verification"
}
```

### 5.2 Webmentions API

```
GET /api/webmentions?target=https://myblog.com/my-article/
```

**Response**:
```json
{
  "target": "https://myblog.com/my-article/",
  "webmentions": [
    {
      "source_url": "https://external.example.com/post",
      "mention_type": "reply",
      "author_name": "Jane Doe",
      "author_url": "https://janedoe.example.com",
      "author_photo": "https://janedoe.example.com/photo.jpg",
      "content_text": "Great article, thanks for sharing!",
      "content_html": "<p>Great article, thanks for sharing!</p>",
      "verified_at": "2026-02-18T15:30:00Z"
    }
  ],
  "count": 1
}
```

This endpoint replaces the webmention.io API call in the Ghost theme widget.

---

## 6. Endpoint Advertisement

The webmention endpoint must be advertised so senders can discover it.
There are two options (both should be implemented):

### 6.1 HTTP Link Header (recommended — works for all content types)

Add to all responses from the blog (via reverse proxy or Ghost middleware):

```
Link: <https://posse.example.com/webmention>; rel="webmention"
```

**Implementation**: This should be done at the reverse proxy level (nginx/Caddy)
rather than in POSSE, because POSSE doesn't serve blog pages — Ghost does.

Example nginx config:
```nginx
add_header Link '<https://posse.example.com/webmention>; rel="webmention"' always;
```

### 6.2 HTML `<link>` Tag (fallback)

In the Ghost theme's `default.hbs`:
```html
<link rel="webmention" href="https://posse.example.com/webmention" />
```

### 6.3 Configuration

New config section:
```yaml
webmention_receiver:
  enabled: true
  endpoint_url: "https://posse.example.com/webmention"
  allowed_target_origins:
    - "https://myblog.com"
  rate_limit: 30               # max webmentions per IP per window
  rate_limit_window_seconds: 3600
  max_source_fetch_size: 1048576  # 1 MB
  verification_timeout: 30      # seconds
  moderation: false              # if true, hold for approval
```

---

## 7. Verification Worker

### 7.1 Architecture

The verification worker runs as a background thread (same pattern as the
existing event processor in `posse.py`). It consumes from a thread-safe
queue of pending webmentions.

```python
verification_queue: Queue[tuple[str, str]] = Queue()
# Items are (source_url, target_url) tuples

def verification_worker():
    """Background thread that verifies pending webmentions."""
    while True:
        source_url, target_url = verification_queue.get(block=True)
        try:
            result = verify_webmention(source_url, target_url)
            # Upsert into received_webmentions based on result.status
            ...
        except Exception as e:
            logger.error(f"Verification failed: {e}")
        finally:
            verification_queue.task_done()
```

### 7.2 Verification Flow

```
Receive POST /webmention
    │
    ├─ Validate source + target (sync)
    ├─ Check rate limit (sync)
    ├─ Return 202 Accepted (sync)
    │
    └─ Queue (source, target) for async verification
         │
         ▼
    Verification Worker picks up task
         │
         ├─ SSRF check on source_url
         │   └─ Block private/loopback → log + skip
         │
         ├─ HTTP GET source_url
         │   ├─ 410 Gone → mark existing mention as "deleted"
         │   ├─ Non-2xx → reject, no storage
         │   └─ 2xx → continue
         │
         ├─ Check source contains link to target
         │   └─ No link found → mark existing mention as "deleted"
         │
         ├─ Parse microformats2 (mf2py)
         │   ├─ Extract mention type (reply/like/repost/mention)
         │   ├─ Extract author (name, url, photo)
         │   └─ Extract content (text + sanitized html)
         │
         └─ Upsert into received_webmentions
             ├─ New: INSERT with status="verified"
             └─ Existing: UPDATE content + verified_at
```

### 7.3 Retry Policy

- If source fetch fails due to network error (timeout, DNS failure):
  keep the mention as "pending" and retry on next receipt of the same
  source+target pair (spec says receiver MAY retry).
- Do NOT implement automatic periodic retries (adds complexity, the
  sender is responsible for re-sending).

---

## 8. Security Considerations

### 8.1 SSRF Protection

Reuse the existing `_is_private_or_loopback()` from `webmention.py` to check
the source URL before fetching. This prevents attackers from using the
webmention endpoint to scan internal networks.

### 8.2 Rate Limiting

- Per-IP rate limiting on `POST /webmention` (same mechanism as reply endpoint)
- Global rate limit on verification fetches (prevent queue flooding)
- Configurable limits via `webmention_receiver` config section

### 8.3 Content Sanitization

- All extracted HTML content sanitized before storage (allowlist of safe tags)
- All displayed content HTML-escaped at render time
- `rel="nofollow noopener"` on all external links
- Author photos proxied or validated (prevent tracking pixels)

### 8.4 Abuse Prevention

- Source URL must be HTTP(S)
- Source URL must resolve to a public IP
- Response size capped at 1 MB
- Max 20 redirects during source fetch
- Content length limits on stored text (2000 chars)
- Optional moderation queue (hold mentions for approval before display)

### 8.5 Denial of Service

- Verification is async (receiver returns immediately)
- Queue has bounded size (reject if full)
- Verification worker has timeout on source fetch
- Single-threaded verification prevents parallelism exhaustion

---

## 9. Migration Path from webmention.io

### Phase 1: Parallel Operation
- Deploy the receiver endpoint alongside webmention.io
- Advertise both endpoints (webmention.io via their existing `<link>` tag,
  POSSE via HTTP Link header)
- Both receive webmentions; POSSE stores its own
- Theme widget continues to use webmention.io API

### Phase 2: Widget Migration
- Update the Ghost theme widget (`social-interactions.hbs`) to fetch from
  the new POSSE API (`/api/webmentions?target=...`) instead of webmention.io
- Keep webmention.io as fallback for any mentions that arrive there

### Phase 3: Full Cutover
- Remove webmention.io `<link>` tag from Ghost theme
- POSSE is the sole receiver
- Consider one-time import of historical webmention.io data via their API

### Data Import

webmention.io provides an API to export all mentions:
```
GET https://webmention.io/api/mentions.jf2?domain=myblog.com&per-page=1000
```

A one-time import script can convert these into `received_webmentions` rows:
```python
def import_webmention_io_data(domain: str, store: InteractionDataStore):
    """Import historical webmentions from webmention.io API."""
    # Paginate through all mentions
    # Map jf2 format to received_webmentions schema
    # Insert with status="verified" and original timestamps
```

---

## 10. Dependencies

### New Dependencies

| Package | Purpose | Size |
|---|---|---|
| `mf2py` | Microformats2 HTML parser | ~50KB |
| `bleach` or `nh3` | HTML sanitization | ~200KB |

Both are well-maintained, widely-used Python packages.

`mf2py` is the standard Python library for parsing microformats2, used by
most IndieWeb Python projects. It parses HTML and returns structured data
following the mf2 JSON specification.

`nh3` (or `bleach` as alternative) provides HTML sanitization with tag/attribute
allowlists, which is essential for safely storing and displaying user-provided
HTML content from webmention sources.

### Existing Dependencies (reused)

- `requests` — HTTP fetching (source verification)
- `sqlite3` — Storage (existing InteractionDataStore)
- `flask` — HTTP endpoints
- Existing SSRF protection (`_is_private_or_loopback`)
- Existing rate limiting infrastructure

---

## 11. File Structure

```
src/indieweb/
├── __init__.py              # add receiver exports
├── webmention.py            # existing sender (unchanged)
├── reply.py                 # existing reply form (unchanged)
├── link_tracking.py         # existing link tracking (unchanged)
├── receiver.py              # NEW: receiver endpoint logic
│   ├── validate_webmention_request()
│   ├── verify_webmention()
│   ├── extract_mention_data()
│   └── sanitize_mention_html()
└── utils.py                 # existing utilities (unchanged)

src/interactions/
├── storage.py               # ADD: received_webmentions CRUD methods
│   ├── upsert_received_webmention()
│   ├── get_received_webmentions()
│   ├── mark_webmention_deleted()
│   └── get_webmention_by_source_target()
└── ...

src/ghost/
└── ghost.py                 # ADD: POST /webmention route
                             # ADD: GET /api/webmentions route

tests/
└── test_webmention_receiver.py  # NEW: comprehensive test suite
    ├── TestValidation
    ├── TestVerification
    ├── TestMicroformatsParsing
    ├── TestContentSanitization
    ├── TestReceiverEndpoint
    ├── TestWebmentionsAPI
    └── TestUpdateDeleteHandling
```

---

## 12. Implementation Plan (Ordered Steps)

### Step 1: Database Schema + Storage Methods
- Add `received_webmentions` table to `InteractionDataStore._initialize_db()`
- Implement CRUD: `upsert_received_webmention()`, `get_received_webmentions()`,
  `mark_webmention_deleted()`, `get_webmention_by_source_target()`
- Write storage tests

### Step 2: Validation Module
- Implement `validate_webmention_request()` in `receiver.py`
- URL validation, source != target, target origin check
- Write validation tests

### Step 3: Receiver Flask Route
- Add `POST /webmention` endpoint to `ghost.py`
- Accept `application/x-www-form-urlencoded` with `source` + `target`
- Validate synchronously, return 202 Accepted
- Queue for async verification
- Rate limiting per IP
- Write endpoint tests

### Step 4: Verification Worker
- Implement `verify_webmention()` with source fetching
- Reuse SSRF protection, redirect limits, size caps from sender
- Link-to-target checking (HTML href search, JSON value search)
- 410 Gone / missing link → delete handling
- Start verification thread alongside event processor in `posse.py`
- Write verification tests

### Step 5: Microformats Parsing
- Add `mf2py` dependency
- Implement `extract_mention_data()` for author, content, mention type
- Implement `sanitize_mention_html()` with `nh3` or `bleach`
- Write parsing and sanitization tests

### Step 6: Webmentions API
- Add `GET /api/webmentions?target=<url>` endpoint
- Return JSON array of verified webmentions for a target URL
- Include author info, content, mention type, timestamps
- Cache-friendly headers
- Write API tests

### Step 7: Widget Migration
- Update `social-interactions.hbs` to fetch from POSSE API
- Support both webmention.io and self-hosted as data sources (config toggle)
- Test with real Ghost theme

### Step 8: Endpoint Advertisement Documentation
- Document nginx/Caddy config for HTTP Link header
- Document Ghost theme `<link>` tag addition
- Update WEBMENTION_REPLY_GUIDE.md

### Step 9: Migration Tooling
- Import script for webmention.io historical data
- Verification that imported data displays correctly

---

## 13. Testing Strategy

### Unit Tests
- Validation: URL formats, source == target, origin checking
- Verification: mock source fetches with various HTML/status codes
- Microformats: parse h-entry with like/repost/reply/mention types
- Sanitization: XSS prevention, tag allowlisting, truncation
- Storage: CRUD operations, upsert behavior, status transitions

### Integration Tests
- Flask endpoint: POST /webmention with valid/invalid data
- Rate limiting: verify 429 after limit exceeded
- Async verification: submit webmention, verify it gets processed
- API: GET /api/webmentions returns correct data
- Update flow: send same source+target with changed content
- Delete flow: source returns 410, mention marked deleted

### End-to-End Tests (manual)
- Set up two test blogs
- Blog A writes post linking to Blog B
- Blog A sends webmention to Blog B's endpoint
- Blog B verifies and displays the mention
- Blog A updates post (changes link text) → Blog B updates mention
- Blog A deletes post → Blog B removes mention

---

## 14. Estimated Effort

| Step | Effort | Dependencies |
|---|---|---|
| 1. Database + Storage | Small | None |
| 2. Validation | Small | None |
| 3. Receiver Route | Small | Step 1, 2 |
| 4. Verification Worker | Medium | Step 1, 3 |
| 5. Microformats Parsing | Medium | mf2py, nh3/bleach |
| 6. Webmentions API | Small | Step 1 |
| 7. Widget Migration | Medium | Step 6 |
| 8. Documentation | Small | Step 3 |
| 9. Migration Tooling | Small | Step 6 |

Steps 1-4 form the core receiver (minimum viable). Steps 5-6 add
rich content display. Steps 7-9 complete the migration from webmention.io.
