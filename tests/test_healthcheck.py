"""
Unit Tests for Healthcheck Endpoint.

This test suite validates the comprehensive healthcheck endpoint functionality,
ensuring that all enabled services are properly checked and their statuses
are correctly reported in the response.

Test Coverage:
    - POST /healthcheck endpoint availability
    - Service status checking (Mastodon, Bluesky, LLM, Pushover)
    - Response format validation
    - Error handling for service failures
    - Overall health status determination

Testing Strategy:
    Uses Flask's test client with mocked service clients to simulate
    various service health states without requiring actual service connections.

Fixtures:
    - mock_mastodon_client: Mock MastodonClient instance
    - mock_bluesky_client: Mock BlueskyClient instance
    - mock_llm_client: Mock LLMClient instance
    - mock_pushover_notifier: Mock PushoverNotifier instance
    - healthcheck_client: Flask test client configured with mock services

Running Tests:
    $ poetry run pytest tests/test_healthcheck.py -v
    $ docker compose run --rm test poetry run pytest tests/test_healthcheck.py
"""
import json
import pytest
from queue import Queue
from unittest.mock import Mock, MagicMock

from ghost.ghost import create_app


@pytest.fixture
def mock_mastodon_client():
    """Create a mock MastodonClient instance."""
    client = Mock()
    client.enabled = True
    client.account_name = "test_mastodon"
    client.verify_credentials = Mock(return_value={"username": "testuser"})
    return client


@pytest.fixture
def mock_bluesky_client():
    """Create a mock BlueskyClient instance."""
    client = Mock()
    client.enabled = True
    client.account_name = "test_bluesky"
    client.verify_credentials = Mock(return_value={"handle": "test.bsky.social"})
    return client


@pytest.fixture
def mock_llm_client():
    """Create a mock LLMClient instance."""
    client = Mock()
    client.enabled = True
    client._check_health = Mock(return_value=True)
    return client


@pytest.fixture
def mock_pushover_notifier():
    """Create a mock PushoverNotifier instance."""
    notifier = Mock()
    notifier.enabled = True
    notifier.send_test_notification = Mock(return_value=True)
    return notifier


HEALTHCHECK_TOKEN = "test-healthcheck-token"


@pytest.fixture
def healthcheck_client(mock_mastodon_client, mock_bluesky_client, mock_llm_client, mock_pushover_notifier):
    """Create a Flask test client with mock service clients for healthcheck testing."""
    test_queue = Queue()
    config = {
        "security": {
            "internal_api_token": HEALTHCHECK_TOKEN
        }
    }
    app = create_app(
        test_queue,
        notifier=mock_pushover_notifier,
        config=config,
        mastodon_clients=[mock_mastodon_client],
        bluesky_clients=[mock_bluesky_client],
        llm_client=mock_llm_client
    )
    app.config["TESTING"] = True

    with app.test_client() as client:
        yield client


def test_healthcheck_endpoint_exists(healthcheck_client):
    """Test that the POST /healthcheck endpoint exists and accepts POST requests."""
    response = healthcheck_client.post("/healthcheck", headers={"X-Internal-Token": HEALTHCHECK_TOKEN})
    assert response.status_code == 200
    assert response.content_type == "application/json"


def test_healthcheck_all_services_healthy(healthcheck_client):
    """Test healthcheck response when all services are healthy."""
    response = healthcheck_client.post("/healthcheck", headers={"X-Internal-Token": HEALTHCHECK_TOKEN})
    assert response.status_code == 200

    data = json.loads(response.data)

    # Check overall status
    assert data["status"] == "healthy"
    assert "timestamp" in data
    assert "services" in data

    # Check Mastodon service
    assert data["services"]["mastodon"]["enabled"] is True
    assert "test_mastodon" in data["services"]["mastodon"]["accounts"]
    assert data["services"]["mastodon"]["accounts"]["test_mastodon"]["status"] == "healthy"
    assert data["services"]["mastodon"]["accounts"]["test_mastodon"]["username"] == "@testuser"

    # Check Bluesky service
    assert data["services"]["bluesky"]["enabled"] is True
    assert "test_bluesky" in data["services"]["bluesky"]["accounts"]
    assert data["services"]["bluesky"]["accounts"]["test_bluesky"]["status"] == "healthy"
    assert data["services"]["bluesky"]["accounts"]["test_bluesky"]["handle"] == "test.bsky.social"

    # Check LLM service
    assert data["services"]["llm"]["enabled"] is True
    assert data["services"]["llm"]["status"] == "healthy"

    # Check Pushover service
    assert data["services"]["pushover"]["enabled"] is True
    assert data["services"]["pushover"]["status"] == "healthy"


def _make_healthcheck_config():
    """Helper to create config with auth token for healthcheck tests."""
    return {"security": {"internal_api_token": HEALTHCHECK_TOKEN}}


def test_healthcheck_mastodon_failure(mock_mastodon_client, mock_bluesky_client, mock_llm_client, mock_pushover_notifier):
    """Test healthcheck response when Mastodon service fails."""
    # Configure Mastodon to fail
    mock_mastodon_client.verify_credentials = Mock(return_value=None)

    test_queue = Queue()
    app = create_app(
        test_queue,
        notifier=mock_pushover_notifier,
        config=_make_healthcheck_config(),
        mastodon_clients=[mock_mastodon_client],
        bluesky_clients=[mock_bluesky_client],
        llm_client=mock_llm_client
    )
    app.config["TESTING"] = True

    with app.test_client() as client:
        response = client.post("/healthcheck", headers={"X-Internal-Token": HEALTHCHECK_TOKEN})
        assert response.status_code == 200

        data = json.loads(response.data)

        # Overall status should be unhealthy
        assert data["status"] == "unhealthy"

        # Mastodon should be unhealthy
        assert data["services"]["mastodon"]["accounts"]["test_mastodon"]["status"] == "unhealthy"
        assert "error" in data["services"]["mastodon"]["accounts"]["test_mastodon"]


def test_healthcheck_llm_disabled(mock_mastodon_client, mock_bluesky_client, mock_pushover_notifier):
    """Test healthcheck response when LLM service is disabled."""
    # Create disabled LLM client
    mock_llm_client = Mock()
    mock_llm_client.enabled = False

    test_queue = Queue()
    app = create_app(
        test_queue,
        notifier=mock_pushover_notifier,
        config=_make_healthcheck_config(),
        mastodon_clients=[mock_mastodon_client],
        bluesky_clients=[mock_bluesky_client],
        llm_client=mock_llm_client
    )
    app.config["TESTING"] = True

    with app.test_client() as client:
        response = client.post("/healthcheck", headers={"X-Internal-Token": HEALTHCHECK_TOKEN})
        assert response.status_code == 200

        data = json.loads(response.data)

        # Overall status should still be healthy (disabled services don't affect health)
        assert data["status"] == "healthy"

        # LLM should be disabled
        assert data["services"]["llm"]["enabled"] is False


def test_healthcheck_no_services_configured():
    """Test healthcheck response when no services are configured."""
    test_queue = Queue()

    # Create disabled notifier
    mock_notifier = Mock()
    mock_notifier.enabled = False

    app = create_app(
        test_queue,
        notifier=mock_notifier,
        config=_make_healthcheck_config(),
        mastodon_clients=[],
        bluesky_clients=[],
        llm_client=None
    )
    app.config["TESTING"] = True

    with app.test_client() as client:
        response = client.post("/healthcheck", headers={"X-Internal-Token": HEALTHCHECK_TOKEN})
        assert response.status_code == 200

        data = json.loads(response.data)

        # Overall status should be healthy (no services to fail)
        assert data["status"] == "healthy"

        # All services should be disabled
        assert data["services"]["mastodon"]["enabled"] is False
        assert data["services"]["bluesky"]["enabled"] is False
        assert data["services"]["llm"]["enabled"] is False
        assert data["services"]["pushover"]["enabled"] is False


def test_healthcheck_pushover_failure(mock_mastodon_client, mock_bluesky_client, mock_llm_client, mock_pushover_notifier):
    """Test healthcheck response when Pushover service fails."""
    # Configure Pushover to fail
    mock_pushover_notifier.send_test_notification = Mock(return_value=False)

    test_queue = Queue()
    app = create_app(
        test_queue,
        notifier=mock_pushover_notifier,
        config=_make_healthcheck_config(),
        mastodon_clients=[mock_mastodon_client],
        bluesky_clients=[mock_bluesky_client],
        llm_client=mock_llm_client
    )
    app.config["TESTING"] = True

    with app.test_client() as client:
        response = client.post("/healthcheck", headers={"X-Internal-Token": HEALTHCHECK_TOKEN})
        assert response.status_code == 200

        data = json.loads(response.data)

        # Overall status should be unhealthy
        assert data["status"] == "unhealthy"

        # Pushover should be unhealthy
        assert data["services"]["pushover"]["status"] == "unhealthy"
        assert "error" in data["services"]["pushover"]


def test_healthcheck_multiple_accounts(mock_llm_client, mock_pushover_notifier):
    """Test healthcheck with multiple Mastodon and Bluesky accounts."""
    # Create multiple mock clients
    mastodon1 = Mock()
    mastodon1.enabled = True
    mastodon1.account_name = "mastodon_personal"
    mastodon1.verify_credentials = Mock(return_value={"username": "personal"})

    mastodon2 = Mock()
    mastodon2.enabled = True
    mastodon2.account_name = "mastodon_work"
    mastodon2.verify_credentials = Mock(return_value={"username": "work"})

    bluesky1 = Mock()
    bluesky1.enabled = True
    bluesky1.account_name = "bluesky_main"
    bluesky1.verify_credentials = Mock(return_value={"handle": "main.bsky.social"})

    test_queue = Queue()
    app = create_app(
        test_queue,
        notifier=mock_pushover_notifier,
        config=_make_healthcheck_config(),
        mastodon_clients=[mastodon1, mastodon2],
        bluesky_clients=[bluesky1],
        llm_client=mock_llm_client
    )
    app.config["TESTING"] = True

    with app.test_client() as client:
        response = client.post("/healthcheck", headers={"X-Internal-Token": HEALTHCHECK_TOKEN})
        assert response.status_code == 200

        data = json.loads(response.data)

        # Check all accounts are present
        assert len(data["services"]["mastodon"]["accounts"]) == 2
        assert "mastodon_personal" in data["services"]["mastodon"]["accounts"]
        assert "mastodon_work" in data["services"]["mastodon"]["accounts"]

        assert len(data["services"]["bluesky"]["accounts"]) == 1
        assert "bluesky_main" in data["services"]["bluesky"]["accounts"]


def test_healthcheck_disabled_accounts_not_checked():
    """Test that disabled accounts are not checked during healthcheck."""
    # Create mock client that is disabled
    mock_mastodon = Mock()
    mock_mastodon.enabled = False
    mock_mastodon.account_name = "disabled_account"

    test_queue = Queue()

    mock_notifier = Mock()
    mock_notifier.enabled = False

    app = create_app(
        test_queue,
        notifier=mock_notifier,
        config=_make_healthcheck_config(),
        mastodon_clients=[mock_mastodon],
        bluesky_clients=[],
        llm_client=None
    )
    app.config["TESTING"] = True

    with app.test_client() as client:
        response = client.post("/healthcheck", headers={"X-Internal-Token": HEALTHCHECK_TOKEN})
        assert response.status_code == 200

        data = json.loads(response.data)

        # Disabled account should not be in the results
        assert "disabled_account" not in data["services"]["mastodon"]["accounts"]

        # verify_credentials should not have been called
        mock_mastodon.verify_credentials.assert_not_called()
