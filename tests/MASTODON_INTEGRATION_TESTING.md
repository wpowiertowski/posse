# Mastodon Integration Testing

This directory contains integration tests that validate the Mastodon client functionality against a real Mastodon instance.

## Overview

The integration tests use a containerized Mastodon instance running in Docker. This provides:
- **Real API testing**: Tests interact with an actual Mastodon server
- **Verification**: Tests can verify posts were created by querying the instance
- **Isolation**: Test instance is separate from production
- **Reproducibility**: Same environment for local and CI testing

## Architecture

The test setup includes:
- **PostgreSQL**: Database for Mastodon
- **Redis**: Cache and background job queue
- **Mastodon Web**: Main Mastodon web server (API endpoint)
- **Mastodon Sidekiq**: Background job processor
- **Test Service**: Container running the test suite

## Running Integration Tests

### Quick Start

Run all integration tests with the automated script:

```bash
./scripts/run-mastodon-tests.sh
```

This script will:
1. Start the Mastodon test instance
2. Wait for services to be healthy
3. Create a test user and access token
4. Run the integration tests
5. Tear down the instance

### Manual Testing

For more control, run steps manually:

```bash
# 1. Start Mastodon test instance
docker compose --profile test up -d

# 2. Wait for Mastodon to be healthy (check with docker ps)
docker compose --profile test ps

# 3. Setup test user and access token
./scripts/setup-mastodon-test.sh

# 4. Run integration tests
docker compose --profile test run --rm test pytest tests/test_mastodon_integration.py -v

# 5. View Mastodon logs if needed
docker compose --profile test logs mastodon-web

# 6. Cleanup when done
docker compose --profile test down -v
```

### Running Specific Tests

```bash
# Run a specific test class
docker compose --profile test run --rm test pytest tests/test_mastodon_integration.py::TestMastodonIntegration -v

# Run a specific test
docker compose --profile test run --rm test pytest tests/test_mastodon_integration.py::TestMastodonIntegration::test_post_simple_status -v
```

## Test Configuration

### Environment Variables

The test container uses these environment variables:

- `MASTODON_TEST_INSTANCE_URL`: URL of the test Mastodon instance (default: `http://mastodon-web:3000`)
- `MASTODON_TEST_ACCESS_TOKEN_FILE`: Path to the access token file (default: `/tmp/mastodon_test_token.txt`)

### Test User

The setup script creates a test user with:
- **Username**: `testuser`
- **Email**: `test@localhost`
- **Role**: Owner (admin)
- **Status**: Confirmed

An OAuth application is created with:
- **Name**: POSSE Test Client
- **Scopes**: `read write follow`
- **Access Token**: Stored in `secrets/mastodon_test_access_token.txt`

## Test Coverage

The integration tests verify:

### Basic Functionality
- ✅ Credential verification
- ✅ Posting simple statuses
- ✅ Verifying posts were created

### Post Options
- ✅ Visibility levels (public, unlisted, private, direct)
- ✅ Sensitive content warnings
- ✅ Spoiler text / content warnings

### Media Handling
- ✅ Posting with media URLs (when network access available)
- ✅ Media descriptions / alt text
- ✅ Graceful handling of download failures

### Client Behavior
- ✅ Disabled client (no token) doesn't post
- ✅ Multiple sequential posts
- ✅ Client creation from configuration

## Troubleshooting

### Mastodon Takes Too Long to Start

The Mastodon instance can take 1-2 minutes to fully initialize. The scripts include appropriate waits, but if you're running manually, be patient.

```bash
# Check service health
docker compose --profile test ps

# View startup logs
docker compose --profile test logs -f mastodon-web
```

### Test User Already Exists

If you run setup multiple times, the test user may already exist. This is normal and the script will continue.

### Access Token Issues

If tests fail with authentication errors:

```bash
# Verify token file exists
cat secrets/mastodon_test_access_token.txt

# Recreate token
docker compose --profile test exec mastodon-web rails runner "
app = Doorkeeper::Application.find_by(name: 'POSSE Test Client')
user = User.find_by(email: 'test@localhost')
token = Doorkeeper::AccessToken.create!(
  application_id: app.id,
  resource_owner_id: user.id,
  scopes: 'read write follow'
)
puts token.token
"
```

### Database Issues

If you see database errors, reset the test environment:

```bash
# Completely tear down and restart
docker compose --profile test down -v
docker compose --profile test up -d
```

### Network Access for Media Tests

Some tests download images from external URLs. These may fail in restricted network environments. The tests are designed to handle this gracefully.

## CI/CD Integration

GitHub Actions workflow includes Mastodon integration tests:

- **Job**: `mastodon-integration-test`
- **Runs**: On all PRs and main branch pushes
- **Timeout**: 15 minutes total
- **Cleanup**: Always tears down test instance

## Performance Considerations

### Startup Time

- **Initial startup**: ~2-3 minutes (downloads images, runs migrations)
- **Subsequent startups**: ~1-2 minutes (images cached)

### Resource Usage

The test Mastodon instance requires:
- **CPU**: ~2 cores during startup, ~0.5 cores running
- **Memory**: ~2GB total (all services)
- **Disk**: ~1GB for images and volumes

### Optimization Tips

1. **Keep volumes**: Don't use `-v` flag when stopping if running tests repeatedly
2. **Pre-pull images**: Run `docker compose --profile test pull` to cache images
3. **Parallel tests**: Tests can run in parallel with pytest-xdist if needed

## Security Notes

- Test instance uses **weak secrets** (safe for testing only)
- Test instance is **not production-ready**
- Access tokens are **stored in git-ignored files**
- Test instance **does not federate**
- All data is **ephemeral** (destroyed with `-v` flag)

## Future Enhancements

Potential improvements to the test setup:

- [ ] Add tests for reply threads
- [ ] Add tests for mentions and notifications
- [ ] Add tests for boost/favorite functionality
- [ ] Add tests for timeline retrieval
- [ ] Add tests for account relationships (follow/unfollow)
- [ ] Add performance benchmarks
- [ ] Add multi-account posting tests
- [ ] Cache Mastodon Docker images in CI

## Related Files

- `docker-compose.yml`: Service definitions
- `.env.mastodon.test`: Mastodon configuration
- `scripts/setup-mastodon-test.sh`: User and token setup
- `scripts/run-mastodon-tests.sh`: Automated test runner
- `tests/test_mastodon_integration.py`: Integration test suite
- `.github/workflows/ci.yml`: CI configuration
