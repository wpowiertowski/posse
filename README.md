# POSSE
POSSE (Publish Own Site, Syndicate Elsewhere) is a small Python project that synchronizes Ghost blog posts with social profiles (e.g., Mastodon, Bluesky). The repository uses a src-layout and is built & run with Docker and Poetry.

## Project layout

```
.
├── docker-compose.yml      # Docker Compose configuration
├── Dockerfile              # Docker image definition (installs the package into container env)
├── pyproject.toml          # Poetry configuration and dependencies
├── src/
│   └── posse/              # package implementation (importable as `posse`)
├── tests/                  # pytest test suite
└── README.md               # This file
```

## Prerequisites

- Docker
- Docker Compose

## Setup

1. Initialize Poetry lock file (first time only):
   ```bash
   docker compose run --rm app poetry lock
   ```

## Usage

### Run the Application

```bash
docker compose up app
```

Or run it directly:
```bash
docker compose run --rm app
```

### Run Tests

Run all tests:
```bash
docker compose run --rm test
```

Or using the profile:
```bash
docker compose --profile test up test
```

### Run Tests with Verbose Output

```bash
docker compose run --rm app poetry run pytest -v
```

### Run Tests with Coverage

```bash
docker compose run --rm app poetry run pytest --cov=. --cov-report=term-missing
```

### Interactive Shell

Get a shell inside the container:
```bash
docker compose run --rm app bash
```

Then you can run commands like:
```bash
poetry run python -m posse
poetry run pytest
poetry run posse  # Uses the console script defined in pyproject.toml
```

## Development

### Install New Dependencies

```bash
docker compose run --rm app poetry add <package-name>
```

### Install Development Dependencies

```bash
docker compose run --rm app poetry add --group dev <package-name>
```

### Update Dependencies

```bash
docker compose run --rm app poetry update
```

## Testing

The project includes pytest with coverage reporting. Tests are automatically discovered in files matching `test_*.py`.

Test features:
- Basic unit tests
- Parametrized tests
- Code coverage reporting
- HTML coverage reports (generated in `htmlcov/` directory)

## Cleanup

Remove containers and images:
```bash
docker compose down
docker compose down --rmi all  # Also remove images
```

## Notes

- The application code is mounted as a volume, so changes are reflected immediately
- The Dockerfile is configured to install dependencies into the container environment (no in-project Poetry virtualenv), so you do not need to set `PYTHONPATH` in the container to import `posse`.
- Coverage reports are generated in the `htmlcov/` directory
