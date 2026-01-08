#!/bin/bash
# Script to run Mastodon integration tests
# This script:
# 1. Starts the Mastodon test instance
# 2. Sets up the test user and access token
# 3. Runs the integration tests
# 4. Tears down the Mastodon instance

set -e

echo "================================================"
echo "Running Mastodon Integration Tests"
echo "================================================"

# Function to cleanup on exit
cleanup() {
    echo ""
    echo "Cleaning up..."
    docker compose --profile test down -v
    echo "Cleanup complete."
}

# Register cleanup function
trap cleanup EXIT

# Start Mastodon test instance
echo "Starting Mastodon test instance..."
docker compose --profile test up -d

# Wait for services to be healthy
echo "Waiting for Mastodon to be healthy..."
timeout=300  # 5 minutes timeout
elapsed=0
while [ $elapsed -lt $timeout ]; do
    if docker compose --profile test ps | grep -q "mastodon-test-web.*healthy"; then
        echo "Mastodon is healthy!"
        break
    fi
    echo "Waiting... ($elapsed/$timeout seconds)"
    sleep 5
    elapsed=$((elapsed + 5))
done

if [ $elapsed -ge $timeout ]; then
    echo "ERROR: Timeout waiting for Mastodon to become healthy"
    docker compose --profile test ps
    docker compose --profile test logs mastodon-web
    exit 1
fi

# Additional wait to ensure everything is fully ready
echo "Waiting additional 10 seconds for full initialization..."
sleep 10

# Setup test user and access token
echo "Setting up test user and access token..."
./scripts/setup-mastodon-test.sh

# Run the integration tests
echo ""
echo "Running integration tests..."
docker compose --profile test run --rm test pytest tests/test_mastodon_integration.py -v

echo ""
echo "================================================"
echo "Integration tests completed successfully!"
echo "================================================"
