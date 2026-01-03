# POSSE
POSSE (Publish Own Site, Syndicate Elsewhere) is a simple python based docker image that synchronizes ghost blog with mastodon and bluesky profiles. Blog posts can be categorized by tags and posted to different profiles across either services.

## Project Structure

```
.
├── docker-compose.yml      # Docker Compose configuration
├── Dockerfile              # Docker image definition
├── pyproject.toml          # Poetry configuration and dependencies
├── hello_world.py          # Main application code
├── test_hello_world.py     # Test suite
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
poetry run python hello_world.py
poetry run pytest
poetry run hello  # Uses the script defined in pyproject.toml
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
- Poetry virtual environment is created inside the container
- Coverage reports are generated in the `htmlcov/` directory
