# Posse

[![CI](https://github.com/wpowiertowski/posse/workflows/CI/badge.svg)](https://github.com/wpowiertowski/posse/actions)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python 3.14+](https://img.shields.io/badge/python-3.14%2B-blue)](https://www.python.org/downloads/)
[![Poetry](https://img.shields.io/badge/poetry-enabled-blue)](https://python-poetry.org/)
[![Docker](https://img.shields.io/badge/docker-supported-blue)](https://www.docker.com/)

A Python project for managing and orchestrating distributed tasks.

## Project Layout

```
posse/
├── src/
│   └── posse/
│       ├── __init__.py
│       ├── main.py
│       └── ...
├── tests/
│   ├── __init__.py
│   ├── test_main.py
│   └── ...
├── docs/
│   └── ...
├── pyproject.toml
├── poetry.lock
├── Dockerfile
├── README.md
└── LICENSE
```

## Prerequisites

- Python 3.14 or higher
- Poetry (for dependency management)
- Docker (optional, for containerized deployment)
- Git

## Setup

### Using Poetry

1. Clone the repository:
   ```bash
   git clone https://github.com/wpowiertowski/posse.git
   cd posse
   ```

2. Install dependencies:
   ```bash
   poetry install
   ```

3. Activate the virtual environment:
   ```bash
   poetry shell
   ```

### Using Docker

1. Build the Docker image:
   ```bash
   docker build -t posse:latest .
   ```

2. Run the container:
   ```bash
   docker run -it posse:latest
   ```

## Usage

### Basic Usage

```python
from posse import main

# Your usage example here
```

### Command Line

```bash
poetry run posse --help
```

## Development

### Install Development Dependencies

```bash
poetry install --with dev
```

### Code Style

This project uses:
- `black` for code formatting
- `flake8` for linting
- `mypy` for type checking

Format your code:
```bash
poetry run black src/ tests/
```

Run linting:
```bash
poetry run flake8 src/ tests/
```

Run type checking:
```bash
poetry run mypy src/
```

## Testing

Run the test suite:

```bash
poetry run pytest
```

Run tests with coverage:

```bash
poetry run pytest --cov=src --cov-report=html
```

Run tests with verbose output:

```bash
poetry run pytest -v
```

## Cleanup

Remove virtual environment and cache files:

```bash
poetry env remove
find . -type d -name __pycache__ -exec rm -r {} +
find . -type f -name "*.pyc" -delete
find . -type d -name ".pytest_cache" -exec rm -r {} +
find . -type d -name ".mypy_cache" -exec rm -r {} +
```

## Notes

- Ensure you have Python 3.14+ installed before setting up the project.
- Poetry automatically creates and manages virtual environments.
- All dependencies are specified in `pyproject.toml`.
- For Docker usage, refer to the `Dockerfile` for image specifications.
- Contributions are welcome! Please follow the development guidelines above.

---

For more information, see the [documentation](docs/) or open an [issue](https://github.com/wpowiertowski/posse/issues).
