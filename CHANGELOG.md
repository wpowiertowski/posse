# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).


## [Unreleased]

### Changed

- **Generalized webmention sending** - replaced the IndieWeb News-specific `IndieWebNewsClient` with a generic `WebmentionClient` that supports multiple configurable targets, each triggered by a tag
- Config section renamed from `indieweb.news` (single target) to `webmention.targets` (list of targets with name, endpoint, target, tag, timeout)
- Webmention reply refusal handling now applies to any 4xx client-error response, not only those from webmention.io
- Pushover notifications for webmention results now include the target name
- Renamed `has_indieweb_tag` → `has_tag`, `get_indieweb_config` → `get_webmention_config`
- Renamed `IndieWeb News Guide` to `Webmention Sending Guide` with multi-target examples


## [1.1.2] - 2026-02-08

### Added

- Self-hosted webmention reply workflow: reply form (`GET /webmention`), submission API (`POST /api/webmention/reply`), and published h-entry reply pages (`GET /reply/<reply_id>`)
- SQLite-backed `webmention_replies` table with get/store/delete operations in interaction storage
- Configurable project timezone (`timezone`) with validation and UTC fallback
- Comprehensive reply feature tests (`tests/test_webmention_reply.py`) and timezone config coverage in `tests/test_config.py`

### Changed

- Ghost Content API client, interaction sync service, scheduler, and syndication mapping timestamps now use configured timezone instead of fixed UTC
- Reply target validation now requires allowed origin, existing Ghost post lookup by slug, and canonical URL match before submission is accepted
- Reply source URL generation now prefers target origin to keep canonical host behavior behind reverse proxies
- Reply form and reply h-entry pages now reuse Ghost theme assets (stylesheet and Montserrat fonts) for visual consistency
- `README.md` reorganized into a concise entry point with dedicated feature guides
- Local runtime `data/` directory is now ignored in `.gitignore`

### Security

- Hardened webmention reply handling: stored replies are removed when delivery is rejected with 4xx responses
- Tightened reply form and reply page HTTP headers (CSP, `X-Content-Type-Options`, `X-Frame-Options`, referrer policy, and cache controls)

### Documentation

- Added focused guides: `docs/SYNDICATION_GUIDE.md`, `docs/WEBMENTION_REPLY_GUIDE.md`, and `docs/WEBMENTION_SENDING_GUIDE.md`
- Updated README feature list, endpoints, quick-start flow, and guide cross-links
- Expanded `config.example.yml` and `config.yml` comments for timezone and webmention reply configuration


## [1.1.1] - 2026-02-06

### Changed

- Interaction and syndication mapping runtime storage is now SQLite-only (`interactions.db`)
- Interaction scheduler now reads tracked posts from SQLite mappings instead of filesystem JSON scans
- Interaction storage path now resolves directly from `interactions.cache_directory` (database at cache directory root)
- Removed legacy JSON migration and mapping consistency scripts/tests tied to transitional storage flow

### Documentation

- Updated interaction sync documentation and examples to reflect SQLite-only storage and current configuration


## [1.1.0] - 2026-02-03

### Major Feature: Social Interaction Syncing

This release introduces **syndication interaction syncing** - a system that fetches engagement metrics (likes, reposts, replies) from your syndicated posts on Mastodon and Bluesky and syncs them back to your Ghost blog. Combined with a new embeddable widget, readers can now see social engagement directly on your blog posts.

Key capabilities:
- Automatic polling of Mastodon and Bluesky APIs for interaction data
- Reply preview extraction with author metadata
- Scheduled background sync with configurable intervals
- REST API endpoint for fetching interaction data per post
- Ghost theme widget for displaying social engagement and webmentions

### Added

- **Social interaction sync engine** - fetches likes, reposts, and replies from Mastodon and Bluesky (#64)
- **Social interactions widget** for Ghost themes - displays POSSE engagement, webmentions, and optional Disqus comments
- **Webmentions integration** in widget - fetches and displays likes, reposts, and comments from webmention.io (#73)
- **Automatic syndication mapping discovery** for older posts - enables interaction sync for posts syndicated before this feature existed (#71)
- **Legacy post backfill endpoint** - manually trigger syndication discovery for historical posts
- **Ghost REST API integration** for fetching post metadata during interaction sync (#72)
- **CORS support** with configuration-based allowed origins for cross-origin widget API requests
- **Syndication links summary** in interactions API response for widget reply buttons
- **IndieWeb News syndication** via webmention when posts are tagged appropriately (#66)
- **Timeout handling** for Mastodon API requests to prevent sync failures

### Changed

- Simplified and streamlined codebase for better maintainability (#74)
- Improved interaction storage configuration handling
- Skip syndicating internal Ghost tags (`#dont-duplicate-feature`)

### Fixed

- Interaction data loss issue during sync operations (#72)
- Mastodon API interaction sync by removing unsupported `limit` parameter
- IndieWeb News webmention endpoint URL (#68)
- Service tags not being dropped correctly from syndicated posts
- `#nosplit` tag not being dropped from syndicated posts


## [1.0.3] - 2026-01-25

### Added

- Option to split Ghost posts with multiple images into individual syndicated posts (#60)
- `#nosplit` hashtag to bypass post splitting on a per-post basis (#62)
- Claude Code GitHub Workflow for automated assistance (#61)

### Changed

- Updated AGENTS.md to reflect Claude Code development guidelines


## [1.0.2] - 2026-01-19

### Added

- POST /healthcheck endpoint to verify enabled services (#58)

### Changed

- Ensure featured image appears first in syndication media list (#59)
- README documentation cleanup

### Fixed

- Docker publish workflow for tag pushes by disabling sha tag when no branch (v1.0.1a)


## [1.0.1] - 2026-01-15

### Added

- Optional LLM-powered alt text generation for images to improve accessibility (#56)
- Rich text formatting support for Bluesky posts using `TextBuilder` (#51)

### Changed

- Filter external images from Ghost post syndication to avoid re-hosting external content (#54)
- Update Docker publish workflow to tag images using Git tags matching vX.Y.Z
- Revert and refine Docker publish workflow for stable tagging behavior (#49)

### Fixed

- Fix Docker tag generation for version tag pushes (#47)
- Fix docker metadata action failures caused by trailing whitespace in tags (#48)
- Fix docker metadata-action template syntax error (#57)


## [1.0.0] - 2026-01-12

### Added

- Ghost webhook receiver with JSON schema validation
- Multi-account support for Mastodon with tag-based filtering
- Multi-account support for Bluesky with tag-based filtering
- Pushover notifications for post events (received, validated, queued, errors)
- Tag-based post filtering per account (case-insensitive matching)
- Automatic Docker Hub publishing via GitHub Actions
- Complete Mastodon posting integration with status publishing
- Complete Bluesky posting integration with post creation
- Bluesky authentication and credential verification
- Production-ready Flask application with Gunicorn
- Docker and Docker Compose support for easy deployment
- Secure credential management with Docker secrets
- Comprehensive test suite with pytest
- CI/CD pipeline with automated testing and Docker publishing

### Documentation

- Complete README with setup instructions
- Configuration examples for Mastodon and Bluesky
- Pushover notification setup guide
- Tag-based filtering documentation
- Production deployment example with Ghost blog

### Security

- CVE-2025-45582: Using Alpine base image with BusyBox tar 1.37.0 (not vulnerable)
- CVE-2025-60876: Mitigated by installing GNU wget to replace vulnerable BusyBox wget
- CVE-2026-22184: Upgraded zlib to >= 1.3.1.3 to fix critical buffer overflow
- Secure credential management using Docker secrets
- JSON schema validation for all webhook payloads

[Unreleased]: https://github.com/wpowiertowski/posse/compare/v1.1.2...HEAD
[1.1.2]: https://github.com/wpowiertowski/posse/compare/v1.1.1...v1.1.2
[1.1.1]: https://github.com/wpowiertowski/posse/compare/v1.1.0...v1.1.1
[1.1.0]: https://github.com/wpowiertowski/posse/compare/v1.0.3...v1.1.0
[1.0.3]: https://github.com/wpowiertowski/posse/releases/tag/v1.0.3
[1.0.2]: https://github.com/wpowiertowski/posse/releases/tag/v1.0.2
[1.0.1]: https://github.com/wpowiertowski/posse/releases/tag/v1.0.1
[1.0.0]: https://github.com/wpowiertowski/posse/releases/tag/v1.0.0
