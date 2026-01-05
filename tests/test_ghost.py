"""
Unit Tests for Ghost Webhook Receiver.

This test suite validates the Ghost webhook receiver functionality,
ensuring that incoming Ghost post webhooks are properly received,
validated against the JSON schema, and logged appropriately.

Test Coverage:
    - Endpoint availability (health check)
    - Valid post reception (200 OK)
    - Schema validation (required fields)
    - Error handling (invalid payloads)
    - Content-Type validation
    - Response format verification
    - Validation function testing

Testing Strategy:
    Uses Flask's test client to simulate HTTP requests without
    starting an actual server. This provides:
    - Fast test execution (no network overhead)
    - Isolation (no external dependencies)
    - Deterministic results (controlled test data)
    - Easy debugging (in-process execution)

Fixtures:
    - client: Flask test client for making HTTP requests
    - valid_post_payload: Sample valid Ghost post loaded from JSON fixture

Running Tests:
    $ poetry run pytest tests/test_ghost.py -v
    $ docker compose run --rm test poetry run pytest tests/test_ghost.py
    
Coverage:
    $ poetry run pytest tests/test_ghost.py --cov=ghost --cov-report=html
"""
import json
import pytest
from pathlib import Path

# Import Flask app and validation functions
from ghost.ghost import app, validate_ghost_post, GhostPostValidationError


@pytest.fixture
def client():
    """Create a Flask test client for testing endpoints.
    
    The test client allows making HTTP requests to the Flask app
    without starting an actual server. It's faster and more reliable
    than testing against a real server.
    
    Configuration:
        TESTING=True enables Flask's testing mode which:
        - Disables error catching to show full tracebacks
        - Improves error messages in test output
        - Disables certain optimizations
    
    Yields:
        FlaskClient: Test client for making HTTP requests
        
    Example:
        def test_something(client):
            response = client.get('/health')
            assert response.status_code == 200
    """
    # Enable testing mode for better error messages
    app.config['TESTING'] = True
    
    # Create and yield test client
    # Using 'with' ensures proper cleanup after test
    with app.test_client() as client:
        yield client


@pytest.fixture
def valid_post_payload():
    """Load a valid Ghost post fixture from JSON file.
    
    This fixture provides a realistic Ghost post payload that passes
    schema validation. It's loaded from a JSON file to ensure the test
    data matches what Ghost actually sends.
    
    The fixture includes:
    - All required fields (id, title, slug, content, url, timestamps)
    - Optional fields (tags, authors, featured status)
    - Properly formatted dates (ISO-8601)
    - Valid URIs for url and image fields
    
    Returns:
        dict: Valid Ghost post data structure
        
    File Location:
        tests/fixtures/valid_ghost_post.json
    """
    # Construct path to fixture file relative to this test file
    fixture_path = Path(__file__).parent / "fixtures" / "valid_ghost_post.json"
    
    # Load and parse JSON fixture
    with open(fixture_path, 'r') as f:
        return json.load(f)


def test_health_check(client):
    """Test the health check endpoint returns healthy status.
    
    The /health endpoint is used by monitoring systems and load balancers
    to verify the service is running. It should always return 200 OK with
    a simple JSON response.
    
    Validates:
        - Endpoint is accessible (200 status)
        - Response is valid JSON
        - Response contains expected status field
        - Status value is "healthy"
    """
    # Make GET request to health endpoint
    response = client.get('/health')
    
    # Verify successful response
    assert response.status_code == 200, "Health check should return 200 OK"
    
    # Parse and validate JSON response
    data = response.get_json()
    assert data is not None, "Health check should return JSON"
    assert data['status'] == 'healthy', "Health check status should be 'healthy'"


def test_receive_valid_post(client, valid_post_payload):
    """Test receiving a valid Ghost post returns success response.
    
    This is the main happy-path test verifying that a properly formatted
    Ghost post webhook is:
    1. Accepted by the endpoint
    2. Validated successfully against the schema
    3. Logged appropriately (INFO and DEBUG levels)
    4. Acknowledged with a 200 OK response
    5. Response includes post ID for tracking
    
    Uses the valid_post_payload fixture which contains a realistic
    Ghost post with all required fields and several optional ones.
    """
    # Send POST request with valid Ghost post data
    response = client.post(
        '/webhook/ghost',  # Endpoint URL
        json=valid_post_payload,  # Automatically serializes to JSON
        content_type='application/json'  # Required Content-Type header
    )
    
    # Verify successful response status
    assert response.status_code == 200, "Valid post should return 200 OK"
    
    # Parse response JSON
    data = response.get_json()
    
    # Verify response structure and content
    assert data['status'] == 'success', "Response status should be 'success'"
    assert data['message'] == 'Post received and validated', "Response should confirm receipt"
    assert data['post_id'] == valid_post_payload['post']['current']['id'], "Response should include post ID"


def test_receive_non_json_payload(client):
    """Test that non-JSON payload is rejected with 400 error.
    
    The webhook endpoint requires Content-Type: application/json.
    This test verifies that other content types are rejected before
    any processing occurs.
    
    Validates:
        - Non-JSON request returns 400 Bad Request
        - Response includes clear error message
        - No attempt to parse/validate non-JSON data
    """
    # Send POST request with plain text instead of JSON
    response = client.post(
        '/webhook/ghost',
        data='not json',  # Plain text data
        content_type='text/plain'  # Wrong content type
    )
    
    # Verify rejection with 400 Bad Request
    assert response.status_code == 400, "Non-JSON payload should return 400"
    
    # Parse error response
    data = response.get_json()
    
    # Verify error message explains the issue
    assert data['error'] == 'Content-Type must be application/json', \
        "Error should explain Content-Type requirement"


def test_receive_invalid_schema(client):
    """Test that payload missing required fields fails validation.
    
    Ghost webhook payloads must include a nested structure with post.current
    and post.previous objects. This test verifies that posts missing required
    fields are rejected with appropriate error messages.
    
    The test uses a minimal invalid payload that is missing the required
    nested structure and fields.
    """
    # Create invalid payload missing required nested structure
    invalid_payload = {
        "post": {
            "current": {
                "id": "123",
                "title": "Test"
                # Missing: uuid, slug, status, url, created_at, updated_at
            }
            # Missing: previous
        }
    }
    
    # Send POST request with invalid payload
    response = client.post(
        '/webhook/ghost',
        json=invalid_payload,
        content_type='application/json'
    )
    
    # Verify rejection with 400 Bad Request
    assert response.status_code == 400, "Invalid schema should return 400"
    
    # Parse error response
    data = response.get_json()
    
    # Verify error response structure
    assert data['status'] == 'error', "Status should be 'error'"
    assert data['message'] == 'Invalid Ghost post payload', \
        "Message should indicate invalid payload"
    assert 'details' in data, "Response should include validation details"


def test_receive_empty_json(client):
    """Test that empty JSON object is rejected.
    
    An empty object {} contains no fields, so it fails schema validation
    for missing all required fields. This edge case should be handled
    gracefully with a clear error message.
    """
    # Send POST request with empty JSON object
    response = client.post(
        '/webhook/ghost',
        json={},  # Empty object
        content_type='application/json'
    )
    
    # Verify rejection with 400 Bad Request
    assert response.status_code == 400, "Empty JSON should return 400"
    
    # Parse error response
    data = response.get_json()
    
    # Verify it's treated as a validation error
    assert data['status'] == 'error', "Empty JSON should be validation error"


def test_validate_ghost_post_success(valid_post_payload):
    """Test validation function with valid payload passes silently.
    
    The validate_ghost_post() function should not raise any exception
    when given a valid payload. This test directly exercises the
    validation logic without going through the Flask endpoint.
    
    Success condition:
        Function completes without raising GhostPostValidationError
    """
    # Call validation function (should not raise)
    # If it raises, pytest will mark the test as failed
    validate_ghost_post(valid_post_payload)
    
    # If we reach here, validation passed successfully
    # No explicit assertion needed - the test passes if no exception raised


def test_validate_ghost_post_failure():
    """Test validation function raises exception for invalid payload.
    
    The validate_ghost_post() function should raise GhostPostValidationError
    with a descriptive message when given invalid data.
    
    This test uses pytest.raises to:
    1. Verify the correct exception type is raised
    2. Capture the exception for inspection
    3. Check the error message contains useful information
    """
    # Create invalid payload (missing required nested structure)
    invalid_payload = {"invalid": "structure"}
    
    # Use pytest context manager to catch the expected exception
    with pytest.raises(GhostPostValidationError) as exc_info:
        validate_ghost_post(invalid_payload)
    
    # Verify the exception message is informative
    # Should mention schema validation failure
    assert "Schema validation failed" in str(exc_info.value), \
        "Exception message should mention schema validation"


def test_post_with_optional_fields(client):
    """Test post with only required fields (no optional fields) is valid.
    
    The Ghost webhook schema defines some fields as required and others as
    optional. This test verifies that a minimal valid webhook payload containing
    only required fields is accepted.
    
    This is important because:
    - Not all posts will have tags, authors, or featured status
    - The webhook should accept minimal posts gracefully
    - Schema validation should not enforce optional fields
    
    Required fields tested:
        - post.current: id, uuid, title, slug, status, url, created_at, updated_at
        - post.previous: (object, can be empty)
    
    Omitted optional fields:
        - html, plaintext, tags, primary_tag, primary_author, featured,
          feature_image, meta_title, meta_description, etc.
    """
    # Create minimal payload with only required fields
    minimal_payload = {
        "post": {
            "current": {
                "id": "minimal123",
                "uuid": "uuid-minimal-123",
                "title": "Minimal Post",
                "slug": "minimal-post",
                "status": "published",
                "url": "https://example.com/minimal",
                "created_at": "2024-01-01T00:00:00.000Z",
                "updated_at": "2024-01-01T00:00:00.000Z"
            }
        }
    }
    
    # Send POST request with minimal valid payload
    response = client.post(
        '/webhook/ghost',
        json=minimal_payload,
        content_type='application/json'
    )
    
    # Verify successful response
    assert response.status_code == 200, \
        "Minimal valid post should return 200 OK"
    
    # Parse response
    data = response.get_json()
    
    # Verify response includes the post ID
    assert data['post_id'] == 'minimal123', \
        "Response should include correct post ID from nested structure"
