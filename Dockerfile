# Use Alpine base image which has BusyBox tar 1.37.0, not vulnerable to CVE-2025-45582
# (CVE-2025-45582 only affects GNU tar <= 1.35)
# CVE-2025-60876 fix: Install GNU wget to replace vulnerable BusyBox wget (1.37.0-r30)
FROM python:3.14-alpine

# Install GNU wget to mitigate CVE-2025-60876 (BusyBox wget vulnerability)
# GNU wget is not affected by this vulnerability
RUN apk add --no-cache wget

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    POETRY_VERSION=2.2.1 \
    POETRY_HOME="/opt/poetry" \
    POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_IN_PROJECT=false \
    POETRY_VIRTUALENVS_CREATE=true

# Add Poetry to PATH
ENV PATH="$POETRY_HOME/bin:$PATH"

# Install system dependencies (if any)
# No system dependencies required for this application

# Install Poetry
RUN pip install "poetry==$POETRY_VERSION"

# Set working directory
WORKDIR /app

# Copy dependency files
COPY pyproject.toml poetry.lock* ./

# Install dependencies
RUN poetry install --no-root

# Copy application code
COPY . .

# Install the project
RUN poetry install

# Expose port
EXPOSE 5000

# Default command - use posse entry point (which runs Gunicorn internally)
CMD ["poetry", "run", "posse"]
