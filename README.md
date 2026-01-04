# POSSE

POSSE stands for **Post Own Site, Syndicate Elsewhere**. This project implements the POSSE philosophy by automatically retrieving the latest posts from a Ghost blog and reposting them to both Mastodon and Bluesky accounts.

## Prerequisites

The only prerequisite required to run this project is **Docker**.

## Project Structure

The repository is organized as follows:

- **src/** - Source code for the POSSE application
- **tests/** - Test suite for the project
- **Dockerfile** - Docker configuration for containerizing the application
- **docker-compose.yml** - Docker Compose configuration for orchestrating services
- **pyproject.toml** - Python project configuration and dependencies
- **poetry.lock** - Locked dependency versions for reproducible builds
- **Makefile** - Utility commands for common development tasks

## How It Works

This project automates the POSSE workflow by:

1. Retrieving the latest published posts from a configured Ghost blog via [webhook](https://docs.ghost.org/webhooks)
2. Reposting them to your Mastodon account
3. Reposting them to your Bluesky account

This ensures your content is syndicated across multiple platforms while maintaining your Ghost blog as the primary source of truth.

## TODO
- [x] build and test flow
- [ ] flask server to receive POST requests from Ghost with contents of the published post
- [ ] authenticate and post to Mastodon account
- [ ] authenticate and post to Bluesky account

## Getting Started

Ensure Docker is installed on your system, then use Docker Compose to run the application:

```bash
docker-compose up
```

Refer to the Makefile for additional development and utility commands.
