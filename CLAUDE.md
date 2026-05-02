# POSSE

POSSE (Publish on your Own Site, Syndicate Elsewhere) is a Flask application that syndicates Ghost blog posts to Mastodon and Bluesky, receives and processes webmentions, and serves an interactions API consumed by the Ghost theme.

## Running Tests

**Always run tests via Docker** — do not run pytest directly on the host.

```bash
docker compose --profile test run --rm test
```

To run a specific test file or test:

```bash
docker compose --profile test run --rm test poetry run pytest tests/test_webmention_receiver.py -v
docker compose --profile test run --rm test poetry run pytest -k "test_verify" -v
```

The test configuration is defined in `pyproject.toml` under `[tool.pytest.ini_options]`.

## Development

Start the application:

```bash
docker compose up
```

The app mounts the local directory into the container, so code changes are reflected without rebuilding.

## Architecture

- `src/ghost/ghost.py` — Flask app, all HTTP routes (webhooks, webmention receiver, interactions API, reply form)
- `src/indieweb/receiver.py` — Async webmention verification (fetches source, parses microformats2, classifies type)
- `src/indieweb/webmention.py` — Outbound webmention sending
- `src/interactions/interaction_sync.py` — Periodic Mastodon/Bluesky interaction sync, new-reply detection
- `src/interactions/storage.py` — SQLite persistence (interactions, webmentions, replies)
- `src/notifications/pushover.py` — Pushover notification client
- `widget/social-interactions.hbs` — Ghost theme partial (copied to the Ghost theme on deploy)

## Code Modification Protocol

**Always read files before modifying them.** Never propose changes to code you haven't read — understand context, patterns, and dependencies first.

Only make changes that are directly requested or clearly necessary. Don't add features beyond what was asked, refactor surrounding code unnecessarily, or design for hypothetical future requirements. Delete unused code completely rather than leaving backwards-compatibility hacks.

## Git Workflow

### Commits

Only create commits when explicitly requested:

1. Run `git status` and `git diff` to see changes
2. Review recent commits with `git log` for message style
3. Draft a concise commit message (1-2 sentences, focus on "why")
4. Add relevant files specifically — not `git add .`
5. Include `Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>` in the commit message
6. Run `git status` after to verify

Never skip hooks (`--no-verify`), never force push to main/master, create new commits rather than amending (unless explicitly asked), and don't commit sensitive files (`.env`, credentials).

**Never push directly to main.** All changes must go through a pull request, even small ones.

### Pull Requests

Always use a pull request to land changes — work on a feature branch, then:

1. Review all commits that will be included (not just the latest)
2. Push the branch and open a PR with `gh pr create`
3. Draft a PR summary with bullet points and a test plan
4. Return the PR URL

### Releases / Tags

1. Update `CHANGELOG.md` with a summary of changes since the previous release
2. Update the project version in `pyproject.toml`
3. Create a commit and tag it appropriately
4. Push the commit and tag to origin

## Security Guidelines

Assist with: authorized security testing, defensive security tools, CTF challenges, security research, and analyzing vulnerabilities in order to fix them.

Do not assist with: destructive techniques, DoS attacks, mass targeting, supply chain compromise, detection evasion for malicious purposes, or unauthorized access/exploitation.
