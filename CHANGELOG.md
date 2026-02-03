# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).


## [Unreleased]

### Added

- Automatic syndication mapping discovery for older posts - syncs interactions for posts syndicated before interaction sync was enabled (#71)
- Webmentions support in social interactions widget - display likes, reposts, and comments from webmention.io (#73)
- Ghost REST API integration for fetching post metadata during interaction sync (#72)
- CORS support with configuration-based allowed origins for cross-origin API requests
- Syndication links summary field in interactions API response for easier widget integration
- IndieWeb News syndication support via webmention when posts are tagged appropriately (#66)
- Timeout handling for Mastodon API requests to prevent sync failures

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

[Unreleased]: https://github.com/wpowiertowski/posse/compare/v1.0.3...HEAD
[1.0.3]: https://github.com/wpowiertowski/posse/releases/tag/v1.0.3
[1.0.2]: https://github.com/wpowiertowski/posse/releases/tag/v1.0.2
[1.0.1]: https://github.com/wpowiertowski/posse/releases/tag/v1.0.1
[1.0.0]: https://github.com/wpowiertowski/posse/releases/tag/v1.0.0

