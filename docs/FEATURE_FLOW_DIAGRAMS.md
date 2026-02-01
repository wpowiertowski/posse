# POSSE Feature Flow Diagrams

This document contains comprehensive flow diagrams for all features implemented in POSSE (Publish Own Site, Syndicate Elsewhere).

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Ghost Webhook Integration](#2-ghost-webhook-integration)
3. [Event Processing Pipeline](#3-event-processing-pipeline)
4. [Content Formatting](#4-content-formatting)
5. [Multi-Account Syndication](#5-multi-account-syndication)
6. [Image Processing](#6-image-processing)
7. [LLM Alt Text Generation](#7-llm-alt-text-generation)
8. [Tag-Based Filtering](#8-tag-based-filtering)
9. [Post Splitting](#9-post-splitting)
10. [Interaction Sync](#10-interaction-sync)
11. [IndieWeb News Syndication](#11-indieweb-news-syndication)
12. [Pushover Notifications](#12-pushover-notifications)
13. [Health Check System](#13-health-check-system)
14. [Configuration Loading](#14-configuration-loading)

---

## 1. System Overview

High-level architecture showing how all components interact.

```mermaid
flowchart TB
    subgraph Ghost["Ghost CMS"]
        GP[Ghost Post Published]
    end

    subgraph POSSE["POSSE Application"]
        subgraph Flask["Flask Web Server"]
            WH[Webhook Handler]
            HC[Health Check]
            API[Interactions API]
        end

        subgraph Processing["Processing Layer"]
            EQ[(Events Queue)]
            EP[Event Processor]
            CF[Content Formatter]
        end

        subgraph Clients["Social Clients"]
            MC[Mastodon Client]
            BC[Bluesky Client]
        end

        subgraph Services["Support Services"]
            LLM[LLM Client]
            PO[Pushover Notifier]
            IS[Interaction Scheduler]
            WM[Webmention Sender]
        end

        subgraph Storage["Storage"]
            SM[(Syndication Mappings)]
            IC[(Interaction Cache)]
            IMG[(Image Cache)]
        end
    end

    subgraph External["External Services"]
        MA[Mastodon Instances]
        BS[Bluesky/ATProto]
        LLMS[LLM Service]
        POS[Pushover API]
        IWN[IndieWeb News]
    end

    GP -->|POST webhook| WH
    WH -->|Queue post| EQ
    EQ -->|Dequeue| EP
    EP --> CF
    CF -->|Format for platform| MC
    CF -->|Format for platform| BC
    MC -->|Post| MA
    BC -->|Post| BS
    EP -->|Generate alt text| LLM
    LLM -->|API call| LLMS
    EP -->|Notify| PO
    PO -->|Push| POS
    EP -->|Send webmention| WM
    WM -->|Submit| IWN
    EP -->|Store mapping| SM
    IS -->|Fetch interactions| MC
    IS -->|Fetch interactions| BC
    IS -->|Store| IC
    API -->|Read| IC
    EP -->|Cache images| IMG
```

---

## 2. Ghost Webhook Integration

Flow for receiving and validating Ghost CMS webhooks.

```mermaid
flowchart TD
    A[Ghost publishes/updates post] -->|HTTP POST| B[/webhook/ghost endpoint]

    B --> C{Content-Type valid?}
    C -->|No| D[Return 400 Bad Request]
    C -->|Yes| E[Parse JSON body]

    E --> F{JSON valid?}
    F -->|No| G[Return 400 Bad Request]
    F -->|Yes| H[Validate against JSON Schema]

    H --> I{Schema valid?}
    I -->|No| J[Log validation error]
    J --> K[Send Pushover notification]
    K --> L[Return 400 Bad Request]

    I -->|Yes| M[Extract post data]
    M --> N{Post has 'current' key?}
    N -->|Yes| O[Use post.current]
    N -->|No| P[Use post directly]

    O --> Q[Extract: title, url, excerpt, tags, images]
    P --> Q

    Q --> R[Log post received]
    R --> S[Send 'Post Received' notification]
    S --> T[Push to events_queue]
    T --> U[Send 'Post Queued' notification]
    U --> V[Return 200 OK]

    style D fill:#f66
    style G fill:#f66
    style L fill:#f66
    style V fill:#6f6
```

### Webhook Payload Structure

```mermaid
flowchart LR
    subgraph Webhook["Ghost Webhook Payload"]
        direction TB
        POST["post: { }"]

        subgraph Current["post.current"]
            T[title]
            U[url]
            E[excerpt]
            H[html]
            FI[feature_image]
            TA[tags: array]
            AU[authors: array]
        end

        subgraph Previous["post.previous"]
            PT[title]
            PU[url]
        end
    end

    POST --> Current
    POST --> Previous
```

---

## 3. Event Processing Pipeline

Main processing loop that handles queued posts.

```mermaid
flowchart TD
    A[Daemon Thread: process_events] -->|Blocking get| B[(Events Queue)]
    B --> C[Extract post from queue]

    C --> D[Prepare content for each platform]
    D --> E[Extract images from post]
    E --> F[Download and cache images]

    F --> G[Get/Generate alt text for images]
    G --> H[Format content with character limits]

    H --> I[Apply tag-based filtering]
    I --> J[Get filtered client list]

    J --> K{Any clients to post to?}
    K -->|No| L[Log: No matching accounts]
    K -->|Yes| M[ThreadPoolExecutor - max 10 workers]

    M --> N[Post to each account in parallel]
    N --> O[Collect results]

    O --> P[Store syndication mappings]
    P --> Q[Clean up cached images]

    Q --> R{Post has 'indiewebnews' tag?}
    R -->|Yes| S[Send webmention to IndieWeb News]
    R -->|No| T[Skip webmention]

    S --> U[Mark queue task done]
    T --> U
    L --> U

    U -->|Loop| A

    style A fill:#bbf
    style U fill:#6f6
```

### Parallel Posting Detail

```mermaid
flowchart TD
    subgraph ThreadPool["ThreadPoolExecutor (max_workers=10)"]
        direction TB

        A[Submit all posting tasks] --> B[Future 1: Mastodon Account A]
        A --> C[Future 2: Mastodon Account B]
        A --> D[Future 3: Bluesky Account A]
        A --> E[Future N: ...]

        B --> F[Wait for completion with timeout]
        C --> F
        D --> F
        E --> F
    end

    F --> G[Collect results]
    G --> H{Any failures?}
    H -->|Yes| I[Log errors, send failure notifications]
    H -->|No| J[Log success, send success notifications]

    I --> K[Return mixed results]
    J --> K
```

---

## 4. Content Formatting

How post content is formatted for each platform.

```mermaid
flowchart TD
    A[Raw Ghost Post] --> B[Extract base content]

    B --> C[Get title]
    B --> D[Get URL]
    B --> E[Get excerpt or generate from HTML]
    B --> F[Get tags as hashtags]

    C --> G[Build content template]
    D --> G
    E --> G
    F --> G

    G --> H{Platform type?}

    H -->|Mastodon| I[Apply 500 char limit]
    H -->|Bluesky| J[Apply 300 char limit]

    I --> K[Truncate excerpt if needed]
    J --> K

    K --> L[Add #posse hashtag]
    L --> M[Add post URL]
    M --> N[Add service-specific tags]

    N --> O[Final formatted content]

    subgraph Template["Content Template"]
        direction LR
        T1["📝 {title}"] --> T2["{excerpt}..."]
        T2 --> T3["#{tag1} #{tag2}"]
        T3 --> T4["#posse"]
        T4 --> T5["{url}"]
    end

    O --> Template
```

### Character Limit Handling

```mermaid
flowchart TD
    A[Calculate total length] --> B{Within limit?}

    B -->|Yes| C[Use full content]
    B -->|No| D[Calculate available space]

    D --> E[Reserved: URL + hashtags + buffer]
    E --> F[Available for excerpt = limit - reserved]

    F --> G[Truncate excerpt to available space]
    G --> H[Add ellipsis ...]
    H --> I[Combine components]

    C --> J[Final content]
    I --> J
```

---

## 5. Multi-Account Syndication

Support for multiple accounts per platform.

```mermaid
flowchart TD
    subgraph Config["Configuration (config.yml)"]
        direction TB
        MA[mastodon.accounts]
        BA[bluesky.accounts]
    end

    MA --> A1[Account 1: tech.social]
    MA --> A2[Account 2: social.coop]
    MA --> A3[Account N: ...]

    BA --> B1[Account 1: main.bsky]
    BA --> B2[Account 2: alt.bsky]

    subgraph Accounts["Per-Account Configuration"]
        direction TB
        ACC["Each Account Has:"]
        URL[instance_url / handle]
        TOK[access_token / app_password]
        TAGS[tags: filter list]
        SPL[split_multi_image_posts]
        LIM[char_limit override]
    end

    A1 --> Accounts
    A2 --> Accounts
    B1 --> Accounts
    B2 --> Accounts

    subgraph Posting["Posting Process"]
        direction TB
        P1[Filter accounts by tags]
        P2[Format content per account]
        P3[Post in parallel]
        P4[Track results per account]
    end

    Accounts --> Posting
```

### Account Selection Flow

```mermaid
flowchart TD
    A[Incoming Post with Tags] --> B[Get all configured accounts]

    B --> C[For each account]
    C --> D{Account has tag filter?}

    D -->|No filter| E[Include account - receives all posts]
    D -->|Has filter| F{Post tags match filter?}

    F -->|Match found| G[Include account]
    F -->|No match| H[Exclude account]

    E --> I[Filtered account list]
    G --> I
    H --> J[Skip this account]

    I --> K[Post to included accounts only]
```

---

## 6. Image Processing

Comprehensive image handling pipeline.

```mermaid
flowchart TD
    A[Ghost Post] --> B[Extract feature_image URL]
    A --> C[Parse HTML for img tags]

    B --> D{Feature image exists?}
    D -->|Yes| E[Add to image list - priority 1]
    D -->|No| F[Continue without feature image]

    C --> G[Extract all img src URLs]
    G --> H[For each image URL]

    H --> I{Same domain as blog?}
    I -->|Yes| J[Add to image list]
    I -->|No| K[Skip external image]

    E --> L[Combined image list]
    F --> L
    J --> L

    L --> M[For each image to process]
    M --> N[Generate SHA-256 hash of URL]
    N --> O[Create cache filename]

    O --> P{Already cached?}
    P -->|Yes| Q[Use cached file]
    P -->|No| R[Download image]

    R --> S[Save to /tmp/posse_image_cache/]
    S --> T[Return file path]
    Q --> T

    T --> U[Get or generate alt text]
    U --> V[Image ready for posting]

    style K fill:#f96
```

### Image Cache Structure

```mermaid
flowchart LR
    subgraph Cache["/tmp/posse_image_cache/"]
        direction TB
        F1["sha256_abc123.jpg"]
        F2["sha256_def456.png"]
        F3["sha256_ghi789.webp"]
    end

    subgraph Process["Cache Lifecycle"]
        direction TB
        P1[Download on first access]
        P2[Reuse during session]
        P3[Clean up after posting]
    end

    Process --> Cache
```

---

## 7. LLM Alt Text Generation

Vision LLM integration for accessibility.

```mermaid
flowchart TD
    A[Image to process] --> B{Alt text in Ghost?}

    B -->|Yes| C[Use existing alt text]
    B -->|No/Empty| D{LLM configured?}

    D -->|No| E[Use empty alt text]
    D -->|Yes| F[Prepare LLM request]

    F --> G[Download image if needed]
    G --> H[Encode image to base64]
    H --> I[Build prompt for vision model]

    I --> J[Send to LLM API]
    J --> K{Response received?}

    K -->|Timeout| L[Log warning, use empty alt]
    K -->|Error| M[Log error, use empty alt]
    K -->|Success| N[Parse response]

    N --> O[Extract generated description]
    O --> P[Truncate to max length if needed]
    P --> Q[Return alt text]

    C --> Q
    E --> Q
    L --> Q
    M --> Q

    style Q fill:#6f6
```

### LLM Request Flow

```mermaid
sequenceDiagram
    participant P as POSSE
    participant L as LLM Client
    participant API as LLM API (Ollama/etc)

    P->>L: generate_alt_text(image_path)
    L->>L: Read and base64 encode image
    L->>L: Build multimodal prompt

    L->>API: POST /api/generate
    Note over L,API: Request includes base64 image + prompt

    alt Success
        API-->>L: Generated description
        L-->>P: Alt text string
    else Timeout
        API--xL: No response in time
        L-->>P: Empty string + warning
    else Error
        API-->>L: Error response
        L-->>P: Empty string + error logged
    end
```

---

## 8. Tag-Based Filtering

How posts are routed to specific accounts.

```mermaid
flowchart TD
    A[Post with tags: tech, python, tutorial] --> B[Get all accounts]

    subgraph Accounts["Configured Accounts"]
        ACC1["Account A<br/>tags: [tech, ai]"]
        ACC2["Account B<br/>tags: [gaming]"]
        ACC3["Account C<br/>tags: []  (no filter)"]
    end

    B --> C{Check Account A}
    C --> D{Post has 'tech' or 'ai'?}
    D -->|Yes: has 'tech'| E[Include Account A]

    B --> F{Check Account B}
    F --> G{Post has 'gaming'?}
    G -->|No| H[Exclude Account B]

    B --> I{Check Account C}
    I --> J{Has tag filter?}
    J -->|No filter| K[Include Account C]

    E --> L[Final: Account A, Account C]
    K --> L

    style H fill:#f96
    style E fill:#6f6
    style K fill:#6f6
```

### Tag Matching Logic

```mermaid
flowchart TD
    A[Account tag filter] --> B{Filter is empty?}

    B -->|Yes| C[Accept ALL posts]
    B -->|No| D[Get post tag slugs]

    D --> E[Lowercase all tags]
    E --> F[For each filter tag]

    F --> G{Tag in post tags?}
    G -->|Yes| H[Match found - accept post]
    G -->|No| I{More filter tags?}

    I -->|Yes| F
    I -->|No| J[No match - reject post]

    C --> K[Post goes to this account]
    H --> K
    J --> L[Post skipped for this account]

    style K fill:#6f6
    style L fill:#f96
```

---

## 9. Post Splitting

Multi-image post splitting for better display.

```mermaid
flowchart TD
    A[Post with multiple images] --> B{Account has split_multi_image_posts?}

    B -->|No| C[Post with all images attached]
    B -->|Yes| D{Post has #nosplit tag?}

    D -->|Yes| E[Skip splitting - post as single]
    D -->|No| F{Image count > 1?}

    F -->|No| G[Single post with single image]
    F -->|Yes| H[Calculate split count]

    H --> I[Create N posts - one per image]

    I --> J[Post 1: Image 1 + full text]
    I --> K[Post 2: Image 2 + reply indicator]
    I --> L[Post N: Image N + reply indicator]

    J --> M[Post in sequence]
    K --> M
    L --> M

    C --> N[Store syndication mapping]
    E --> N
    G --> N
    M --> N

    style D fill:#ff9
```

### Split Post Structure

```mermaid
flowchart LR
    subgraph Original["Original Post"]
        OP[Title + Excerpt + URL]
        OI1[Image 1]
        OI2[Image 2]
        OI3[Image 3]
    end

    subgraph Split["Split Posts"]
        direction TB
        SP1["Post 1<br/>Full content + Image 1"]
        SP2["Post 2<br/>'(2/3)' + Image 2"]
        SP3["Post 3<br/>'(3/3)' + Image 3"]
    end

    Original --> Split

    SP1 -->|Thread| SP2
    SP2 -->|Thread| SP3
```

---

## 10. Interaction Sync

Background service for syncing social interactions.

```mermaid
flowchart TD
    subgraph Scheduler["InteractionScheduler (Background Thread)"]
        A[Start scheduler] --> B[Wait for interval]
        B --> C[Trigger sync cycle]
        C --> D[Read syndication mappings]

        D --> E[For each mapped post]
        E --> F{Post age < max_days?}

        F -->|No| G[Skip - too old]
        F -->|Yes| H{Recently synced?}

        H -->|Yes| I[Skip - wait for interval]
        H -->|No| J[Fetch interactions]

        J --> K[Query Mastodon API]
        J --> L[Query Bluesky API]

        K --> M[Get favorites, reblogs, replies]
        L --> N[Get likes, reposts, replies]

        M --> O[Aggregate stats]
        N --> O

        O --> P[Parse recent comments]
        P --> Q[Store to JSON cache]

        Q --> R[Update last sync time]
        R --> B

        G --> E
        I --> E
    end
```

### Interaction Data Structure

```mermaid
flowchart TD
    subgraph Storage["interactions/{ghost_post_id}.json"]
        direction TB

        A[ghost_post_id]
        B[last_synced timestamp]

        subgraph Stats["aggregated_stats"]
            S1[total_likes: N]
            S2[total_reposts: N]
            S3[total_comments: N]
        end

        subgraph Platforms["platform_data"]
            subgraph Masto["mastodon"]
                M1[favorites: N]
                M2[reblogs: N]
                M3[replies: N]
                M4[post_url: ...]
            end

            subgraph Bsky["bluesky"]
                B1[likes: N]
                B2[reposts: N]
                B3[replies: N]
                B4[post_uri: ...]
            end
        end

        subgraph Comments["recent_comments"]
            C1["comment 1: {author, text, platform, timestamp}"]
            C2["comment 2: {...}"]
            C3["..."]
        end
    end

    A --> Stats
    A --> Platforms
    A --> Comments
    B --> A
```

### API Endpoint Flow

```mermaid
sequenceDiagram
    participant W as Ghost Widget
    participant API as /api/interactions
    participant C as Interaction Cache

    W->>API: GET /api/interactions/{ghost_post_id}
    API->>C: Read {ghost_post_id}.json

    alt Cache exists
        C-->>API: Interaction data
        API-->>W: JSON response with stats
    else Cache miss
        C-->>API: File not found
        API-->>W: 404 or empty response
    end

    Note over W: Display likes, reposts, comments on blog
```

---

## 11. IndieWeb News Syndication

Webmention-based syndication to IndieWeb News.

```mermaid
flowchart TD
    A[Post processing complete] --> B{Post has 'indiewebnews' tag?}

    B -->|No| C[Skip IndieWeb News]
    B -->|Yes| D[Prepare webmention]

    D --> E[Source URL = Post URL]
    E --> F[Target URL = news.indieweb.org/en]

    F --> G[Discover webmention endpoint]
    G --> H{Endpoint found?}

    H -->|No| I[Log error - no endpoint]
    H -->|Yes| J[Send webmention POST]

    J --> K{Response status?}

    K -->|2xx| L[Success - log and notify]
    K -->|4xx| M[Client error - log details]
    K -->|5xx| N[Server error - log and retry?]

    L --> O[Send success notification]
    M --> P[Send failure notification]
    N --> P

    C --> Q[Continue processing]
    O --> Q
    P --> Q
```

### Webmention Protocol

```mermaid
sequenceDiagram
    participant P as POSSE
    participant IWN as IndieWeb News

    Note over P: Post has #indiewebnews tag

    P->>IWN: HEAD / GET to discover endpoint
    IWN-->>P: Link header or HTML with webmention endpoint

    P->>P: Parse endpoint URL

    P->>IWN: POST to webmention endpoint
    Note over P,IWN: Form data: source={post_url}&target={news_url}

    alt Accepted
        IWN-->>P: 202 Accepted
        Note over P: Submission queued for review
    else Already submitted
        IWN-->>P: 200 OK (duplicate)
    else Error
        IWN-->>P: 4xx/5xx Error
    end
```

---

## 12. Pushover Notifications

Real-time push notification system.

```mermaid
flowchart TD
    subgraph Events["Notification Triggers"]
        E1[Post received from Ghost]
        E2[Post queued for syndication]
        E3[Post successfully published]
        E4[Validation error]
        E5[Posting error]
        E6[IndieWeb News submission]
        E7[LLM service issue]
    end

    Events --> A{Pushover configured?}

    A -->|No| B[Skip notification]
    A -->|Yes| C[Build notification payload]

    C --> D[Set title based on event type]
    D --> E[Set message with details]
    E --> F[Add URL if applicable]

    F --> G[Send to Pushover API]
    G --> H{Response?}

    H -->|Success| I[Log notification sent]
    H -->|Failure| J[Log error - continue processing]

    B --> K[Continue main flow]
    I --> K
    J --> K
```

### Notification Types

```mermaid
flowchart LR
    subgraph Types["Notification Categories"]
        direction TB

        subgraph Info["Informational"]
            I1["📥 Post Received"]
            I2["📤 Post Queued"]
            I3["✅ Post Published"]
        end

        subgraph Warning["Warnings"]
            W1["⚠️ LLM Unavailable"]
            W2["⚠️ Partial Failure"]
        end

        subgraph Error["Errors"]
            E1["❌ Validation Failed"]
            E2["❌ Posting Failed"]
            E3["❌ Service Error"]
        end

        subgraph IndieWeb["IndieWeb"]
            IW1["🌐 Submitted to IndieWeb News"]
            IW2["❌ Webmention Failed"]
        end
    end
```

---

## 13. Health Check System

Service health monitoring endpoints.

```mermaid
flowchart TD
    subgraph Endpoints["Health Endpoints"]
        H1["GET /health<br/>Simple liveness probe"]
        H2["POST /healthcheck<br/>Comprehensive check"]
    end

    H1 --> A[Return 200 OK immediately]

    H2 --> B[Initialize checks]

    B --> C[Check Mastodon accounts]
    B --> D[Check Bluesky accounts]
    B --> E[Check LLM service]
    B --> F[Check Pushover service]

    C --> G[Verify credentials for each account]
    D --> H[Verify credentials for each account]
    E --> I[Test LLM API connectivity]
    F --> J[Test Pushover API]

    G --> K[Collect results]
    H --> K
    I --> K
    J --> K

    K --> L{All checks passed?}
    L -->|Yes| M[Return 200 with full status]
    L -->|No| N[Return 200 with degraded status]

    subgraph Response["Response Structure"]
        R1["status: 'healthy' | 'degraded'"]
        R2["services: { mastodon, bluesky, llm, pushover }"]
        R3["accounts: [ { name, status, error? } ]"]
    end

    M --> Response
    N --> Response
```

### Health Check Detail

```mermaid
sequenceDiagram
    participant C as Client
    participant H as Health Endpoint
    participant M as Mastodon Clients
    participant B as Bluesky Clients
    participant L as LLM Client
    participant P as Pushover

    C->>H: POST /healthcheck

    par Check all services
        H->>M: Verify credentials
        M-->>H: OK / Error per account
    and
        H->>B: Verify credentials
        B-->>H: OK / Error per account
    and
        H->>L: Test connectivity
        L-->>H: OK / Error
    and
        H->>P: Test API
        P-->>H: OK / Error
    end

    H->>H: Aggregate results
    H-->>C: JSON status report
```

---

## 14. Configuration Loading

How configuration is loaded and validated.

```mermaid
flowchart TD
    A[Application Start] --> B[Load config.yml]

    B --> C{File exists?}
    C -->|No| D[Use defaults / environment vars]
    C -->|Yes| E[Parse YAML]

    E --> F[Check for Docker secrets]
    F --> G{Secrets available?}

    G -->|Yes| H[Override with secret values]
    G -->|No| I[Use config file values]

    H --> J[Build configuration object]
    I --> J
    D --> J

    J --> K[Initialize LLM client if configured]
    J --> L[Initialize Pushover if configured]
    J --> M[Initialize Mastodon accounts]
    J --> N[Initialize Bluesky accounts]
    J --> O[Initialize Interaction Scheduler]
    J --> P[Configure IndieWeb settings]

    K --> Q[Create Flask app]
    L --> Q
    M --> Q
    N --> Q
    O --> Q
    P --> Q

    Q --> R[Start Gunicorn server]
```

### Configuration Structure

```mermaid
flowchart TD
    subgraph Config["config.yml Structure"]
        direction TB

        subgraph LLM["llm (optional)"]
            L1[base_url]
            L2[model]
            L3[timeout]
        end

        subgraph Pushover["pushover (optional)"]
            P1[user_key / user_key_file]
            P2[api_token / api_token_file]
        end

        subgraph Mastodon["mastodon"]
            subgraph MA["accounts[]"]
                M1[name]
                M2[instance_url]
                M3[access_token / access_token_file]
                M4[tags]
                M5[split_multi_image_posts]
                M6[char_limit]
            end
        end

        subgraph Bluesky["bluesky"]
            subgraph BA["accounts[]"]
                B1[name]
                B2[handle]
                B3[app_password / app_password_file]
                B4[tags]
                B5[split_multi_image_posts]
            end
        end

        subgraph Interactions["interactions (optional)"]
            I1[enabled]
            I2[storage_path]
            I3[sync_interval_minutes]
            I4[max_post_age_days]
        end

        subgraph IndieWeb["indieweb (optional)"]
            IW1[news_enabled]
            IW2[news_tag]
        end
    end
```

### Docker Secrets Integration

```mermaid
flowchart LR
    subgraph Secrets["/run/secrets/"]
        S1[mastodon_token_account1]
        S2[bluesky_password_account1]
        S3[pushover_user_key]
        S4[pushover_api_token]
    end

    subgraph Config["config.yml references"]
        C1["access_token_file: /run/secrets/..."]
        C2["app_password_file: /run/secrets/..."]
        C3["user_key_file: /run/secrets/..."]
        C4["api_token_file: /run/secrets/..."]
    end

    C1 -->|Read at startup| S1
    C2 -->|Read at startup| S2
    C3 -->|Read at startup| S3
    C4 -->|Read at startup| S4

    Secrets --> A[Loaded into memory]
    A --> B[Never logged or exposed]
```

---

## Summary

This document covers all major features of the POSSE application:

| Feature | Primary Files | Key Components |
|---------|--------------|----------------|
| Ghost Webhook | `ghost.py`, `ghost_post_schema.json` | Flask endpoint, JSON Schema validation |
| Event Processing | `posse.py` | Queue, ThreadPoolExecutor, daemon thread |
| Content Formatting | `posse.py` | Character limits, hashtags, URL handling |
| Multi-Account | `mastodon_client.py`, `bluesky_client.py` | Per-account config, parallel posting |
| Image Processing | `posse.py`, `base_client.py` | SHA-256 caching, download, cleanup |
| LLM Alt Text | `llm_client.py` | Vision model, base64 encoding, timeout |
| Tag Filtering | `posse.py` | Case-insensitive matching, account routing |
| Post Splitting | `posse.py` | #nosplit bypass, thread creation |
| Interaction Sync | `interaction_sync.py`, `scheduler.py` | Background sync, JSON caching, API |
| IndieWeb News | `webmention.py` | W3C Webmention, endpoint discovery |
| Pushover | `pushover.py` | Event notifications, error alerts |
| Health Checks | `ghost.py` | Liveness, comprehensive service checks |
| Configuration | `config/__init__.py` | YAML, Docker secrets, validation |

All diagrams use [Mermaid](https://mermaid.js.org/) syntax and can be rendered in GitHub, GitLab, and other markdown viewers with Mermaid support.
