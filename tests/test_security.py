"""
Security Tests for POSSE API Endpoints.

This test suite validates security controls for the /api/interactions endpoint,
including:
- Input validation (post ID format)
- Rate limiting (per-IP and global discovery)
- Referrer validation
- Path traversal protection
- Authentication for protected endpoints
- Error message sanitization

Running Tests:
    $ PYTHONPATH=src python -m pytest tests/test_security.py -v
"""
import json
import pytest
import tempfile
import shutil
import os
import time
from queue import Queue
from unittest.mock import MagicMock, patch

from ghost.ghost import (
    create_app,
    validate_ghost_post_id,
    is_safe_path,
    check_discovery_cooldown,
    record_discovery_attempt,
    check_global_discovery_limit,
    record_global_discovery,
    check_request_rate_limit,
    record_request,
    validate_referrer,
    sanitize_error_message,
    clear_rate_limit_caches,
)


class TestInputValidation:
    """Test input validation functions."""

    def test_valid_post_id(self):
        """Valid 24-char hex string should pass."""
        assert validate_ghost_post_id("507f1f77bcf86cd799439011") is True

    def test_valid_post_id_lowercase(self):
        """All lowercase hex should pass."""
        assert validate_ghost_post_id("abcdef0123456789abcdef01") is True

    def test_invalid_post_id_too_short(self):
        """Short ID should fail."""
        assert validate_ghost_post_id("507f1f77bcf86cd79943901") is False

    def test_invalid_post_id_too_long(self):
        """Long ID should fail."""
        assert validate_ghost_post_id("507f1f77bcf86cd7994390111") is False

    def test_invalid_post_id_uppercase(self):
        """Uppercase hex should fail (strict validation)."""
        assert validate_ghost_post_id("507F1F77BCF86CD799439011") is False

    def test_invalid_post_id_path_traversal(self):
        """Path traversal attempt should fail."""
        assert validate_ghost_post_id("../../../etc/passwd") is False
        assert validate_ghost_post_id("..%2f..%2f..%2fetc%2fpasswd") is False

    def test_invalid_post_id_special_chars(self):
        """Special characters should fail."""
        assert validate_ghost_post_id("507f1f77bcf86cd79943901!") is False
        assert validate_ghost_post_id("507f1f77bcf86cd79943901;") is False

    def test_invalid_post_id_null(self):
        """Null/None should fail."""
        assert validate_ghost_post_id(None) is False
        assert validate_ghost_post_id("") is False

    def test_invalid_post_id_non_string(self):
        """Non-string should fail."""
        assert validate_ghost_post_id(123456789012345678901234) is False
        assert validate_ghost_post_id(["507f1f77bcf86cd799439011"]) is False


class TestPathTraversalProtection:
    """Test path traversal protection."""

    def test_safe_path_within_base(self):
        """Path within base directory should be safe."""
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = os.path.join(tmpdir, "test.json")
            assert is_safe_path(tmpdir, file_path) is True

    def test_safe_path_nested(self):
        """Nested path within base should be safe."""
        with tempfile.TemporaryDirectory() as tmpdir:
            nested_dir = os.path.join(tmpdir, "subdir")
            os.makedirs(nested_dir)
            file_path = os.path.join(nested_dir, "test.json")
            assert is_safe_path(tmpdir, file_path) is True

    def test_unsafe_path_traversal(self):
        """Path traversal attempt should be blocked."""
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = os.path.join(tmpdir, "..", "etc", "passwd")
            assert is_safe_path(tmpdir, file_path) is False

    def test_unsafe_path_absolute_escape(self):
        """Absolute path escaping base should be blocked."""
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = "/etc/passwd"
            assert is_safe_path(tmpdir, file_path) is False


class TestRateLimiting:
    """Test rate limiting functions."""

    def setup_method(self):
        """Clear rate limiting caches before each test."""
        clear_rate_limit_caches()

    def test_discovery_cooldown_not_in_cache(self):
        """Post ID not in cache should not be in cooldown."""
        assert check_discovery_cooldown("507f1f77bcf86cd799439011") is False

    def test_discovery_cooldown_after_record(self):
        """Post ID should be in cooldown after recording."""
        post_id = "507f1f77bcf86cd799439011"
        record_discovery_attempt(post_id)
        assert check_discovery_cooldown(post_id) is True

    def test_global_discovery_limit_not_exceeded(self):
        """Should not exceed limit with few requests."""
        for _ in range(5):
            record_global_discovery()
        assert check_global_discovery_limit() is False

    def test_global_discovery_limit_exceeded(self):
        """Should exceed limit with many requests."""
        for _ in range(15):  # Exceeds default limit of 10
            record_global_discovery()
        assert check_global_discovery_limit() is True

    def test_request_rate_limit_not_exceeded(self):
        """Should not exceed limit with few requests."""
        for _ in range(10):
            record_request("192.168.1.1")
        assert check_request_rate_limit("192.168.1.1") is False

    def test_request_rate_limit_exceeded(self):
        """Should exceed limit with many requests from same IP."""
        for _ in range(65):  # Exceeds default limit of 60
            record_request("192.168.1.1")
        assert check_request_rate_limit("192.168.1.1") is True

    def test_request_rate_limit_per_ip(self):
        """Rate limit should be per-IP."""
        for _ in range(65):
            record_request("192.168.1.1")
        # Different IP should not be limited
        assert check_request_rate_limit("192.168.1.2") is False


class TestReferrerValidation:
    """Test referrer validation."""

    def test_referrer_validation_disabled(self):
        """Empty allowed list should disable validation."""
        assert validate_referrer("https://evil.com/page", []) is True

    def test_referrer_exact_match(self):
        """Exact domain match should pass."""
        assert validate_referrer(
            "https://myblog.com/post",
            ["myblog.com"]
        ) is True

    def test_referrer_full_url_match(self):
        """Full URL prefix match should pass."""
        assert validate_referrer(
            "https://myblog.com/post",
            ["https://myblog.com"]
        ) is True

    def test_referrer_wildcard_match(self):
        """Wildcard subdomain match should pass."""
        assert validate_referrer(
            "https://blog.myblog.com/post",
            ["*.myblog.com"]
        ) is True

    def test_referrer_mismatch(self):
        """Non-matching referrer should fail."""
        assert validate_referrer(
            "https://evil.com/page",
            ["myblog.com"]
        ) is False

    def test_referrer_missing(self):
        """Missing referrer should fail when validation enabled."""
        assert validate_referrer(None, ["myblog.com"]) is False

    def test_referrer_case_insensitive(self):
        """Referrer matching should be case-insensitive."""
        assert validate_referrer(
            "https://MyBlog.com/post",
            ["myblog.com"]
        ) is True


class TestErrorSanitization:
    """Test error message sanitization."""

    def test_sanitize_token_error(self):
        """Token-related errors should be sanitized."""
        assert sanitize_error_message(
            Exception("Invalid token: abc123xyz")
        ) == "Authentication failed"

    def test_sanitize_credential_error(self):
        """Credential errors should be sanitized."""
        assert sanitize_error_message(
            Exception("Bad credentials for user@example.com")
        ) == "Authentication failed"

    def test_sanitize_timeout_error(self):
        """Timeout errors should be sanitized."""
        assert sanitize_error_message(
            Exception("Connection timeout after 30s")
        ) == "Request timed out"

    def test_sanitize_connection_error(self):
        """Connection errors should be sanitized."""
        assert sanitize_error_message(
            Exception("Connection refused to 192.168.1.1:5000")
        ) == "Connection error"

    def test_sanitize_rate_limit_error(self):
        """Rate limit errors should be sanitized."""
        assert sanitize_error_message(
            Exception("Too many requests, try again later")
        ) == "Rate limit exceeded"

    def test_sanitize_generic_error(self):
        """Unknown errors should return generic message."""
        assert sanitize_error_message(
            Exception("Something went wrong with internal details")
        ) == "Service temporarily unavailable"


class TestEndpointSecurity:
    """Integration tests for endpoint security."""

    @pytest.fixture
    def test_dirs(self):
        """Create temporary directories for test data."""
        test_dir = tempfile.mkdtemp()
        storage_path = os.path.join(test_dir, "interactions")
        mappings_path = os.path.join(test_dir, "syndication_mappings")
        os.makedirs(storage_path, exist_ok=True)
        os.makedirs(mappings_path, exist_ok=True)

        yield {
            "test_dir": test_dir,
            "storage_path": storage_path,
            "mappings_path": mappings_path
        }

        shutil.rmtree(test_dir)

    @pytest.fixture
    def secured_app(self, test_dirs):
        """Create Flask app with security features enabled."""
        clear_rate_limit_caches()

        test_queue = Queue()

        # Create config with security settings
        config = {
            "security": {
                "allowed_referrers": ["https://myblog.com"],
                "rate_limit_enabled": True,
                "rate_limit_requests": 10,
                "rate_limit_window_seconds": 60,
                "discovery_rate_limit_enabled": True,
                "discovery_rate_limit": 5,
                "internal_api_token": "test-secret-token"
            }
        }

        app = create_app(
            test_queue,
            config=config
        )

        app.config["TESTING"] = True
        app.config["INTERACTIONS_STORAGE_PATH"] = test_dirs["storage_path"]
        app.config["SYNDICATION_MAPPINGS_PATH"] = test_dirs["mappings_path"]

        return app, test_dirs

    def test_invalid_post_id_rejected(self, secured_app):
        """Invalid post ID should return 400."""
        app, _ = secured_app

        with app.test_client() as client:
            response = client.get(
                "/api/interactions/invalid-id",
                headers={"Referer": "https://myblog.com/post"}
            )
            assert response.status_code == 400
            data = json.loads(response.data)
            assert data["message"] == "Invalid post ID format"

    def test_missing_referrer_rejected(self, secured_app):
        """Missing referrer should return 403 when validation enabled."""
        app, _ = secured_app

        with app.test_client() as client:
            response = client.get("/api/interactions/507f1f77bcf86cd799439011")
            assert response.status_code == 403
            data = json.loads(response.data)
            assert data["message"] == "Forbidden"

    def test_invalid_referrer_rejected(self, secured_app):
        """Invalid referrer should return 403."""
        app, _ = secured_app

        with app.test_client() as client:
            response = client.get(
                "/api/interactions/507f1f77bcf86cd799439011",
                headers={"Referer": "https://evil.com/page"}
            )
            assert response.status_code == 403

    def test_valid_referrer_accepted(self, secured_app):
        """Valid referrer should be accepted (returns 404 for non-existent post)."""
        app, _ = secured_app

        with app.test_client() as client:
            response = client.get(
                "/api/interactions/507f1f77bcf86cd799439011",
                headers={"Referer": "https://myblog.com/post"}
            )
            # Should get 404 (not found) instead of 403 (forbidden)
            assert response.status_code == 404

    def test_rate_limit_exceeded(self, secured_app):
        """Exceeding rate limit should return 429."""
        app, _ = secured_app

        with app.test_client() as client:
            # Make requests up to and exceeding the limit
            for i in range(15):
                response = client.get(
                    f"/api/interactions/507f1f77bcf86cd79943901{i:01x}",
                    headers={"Referer": "https://myblog.com/post"}
                )
                if response.status_code == 429:
                    break

            # Should eventually get rate limited
            assert response.status_code == 429
            data = json.loads(response.data)
            assert "Rate limit exceeded" in data["message"]

    def test_sync_endpoint_requires_auth(self, secured_app):
        """Sync endpoint should require authentication."""
        app, _ = secured_app

        with app.test_client() as client:
            response = client.post(
                "/api/interactions/507f1f77bcf86cd799439011/sync"
            )
            assert response.status_code == 401
            data = json.loads(response.data)
            assert data["message"] == "Unauthorized"

    def test_sync_endpoint_wrong_token(self, secured_app):
        """Sync endpoint should reject wrong token."""
        app, _ = secured_app

        with app.test_client() as client:
            response = client.post(
                "/api/interactions/507f1f77bcf86cd799439011/sync",
                headers={"X-Internal-Token": "wrong-token"}
            )
            assert response.status_code == 401

    def test_sync_endpoint_valid_token(self, secured_app):
        """Sync endpoint should accept valid token."""
        app, _ = secured_app

        with app.test_client() as client:
            response = client.post(
                "/api/interactions/507f1f77bcf86cd799439011/sync",
                headers={"X-Internal-Token": "test-secret-token"}
            )
            # Should get 503 (no scheduler) not 401 (unauthorized)
            assert response.status_code == 503

    def test_sync_endpoint_fails_closed_without_token(self, test_dirs):
        """Sync endpoint should return 503 when no token is configured."""
        clear_rate_limit_caches()
        test_queue = Queue()

        config = {
            "security": {}  # No internal_api_token
        }

        app = create_app(test_queue, config=config)
        app.config["TESTING"] = True

        with app.test_client() as client:
            response = client.post(
                "/api/interactions/507f1f77bcf86cd799439011/sync"
            )
            assert response.status_code == 503
            data = json.loads(response.data)
            assert data["message"] == "Endpoint not configured"

    def test_healthcheck_requires_auth(self, secured_app):
        """Healthcheck endpoint should require authentication."""
        app, _ = secured_app

        with app.test_client() as client:
            response = client.post("/healthcheck")
            assert response.status_code == 401
            data = json.loads(response.data)
            assert data["message"] == "Unauthorized"

    def test_healthcheck_wrong_token(self, secured_app):
        """Healthcheck endpoint should reject wrong token."""
        app, _ = secured_app

        with app.test_client() as client:
            response = client.post(
                "/healthcheck",
                headers={"X-Internal-Token": "wrong-token"}
            )
            assert response.status_code == 401

    def test_healthcheck_valid_token(self, secured_app):
        """Healthcheck endpoint should accept valid token."""
        app, _ = secured_app

        with app.test_client() as client:
            response = client.post(
                "/healthcheck",
                headers={"X-Internal-Token": "test-secret-token"}
            )
            # Should get 200 (healthy) not 401 (unauthorized)
            assert response.status_code == 200

    def test_healthcheck_fails_closed_without_token(self, test_dirs):
        """Healthcheck endpoint should return 503 when no token is configured."""
        clear_rate_limit_caches()
        test_queue = Queue()

        config = {
            "security": {}  # No internal_api_token
        }

        app = create_app(test_queue, config=config)
        app.config["TESTING"] = True

        with app.test_client() as client:
            response = client.post("/healthcheck")
            assert response.status_code == 503
            data = json.loads(response.data)
            assert data["message"] == "Endpoint not configured"


class TestWebhookAuthentication:
    """Test webhook endpoint authentication."""

    @pytest.fixture
    def test_dirs(self):
        """Create temporary directories for test data."""
        test_dir = tempfile.mkdtemp()
        yield {"test_dir": test_dir}
        shutil.rmtree(test_dir)

    def test_webhook_no_secret_configured_allows_requests(self, test_dirs):
        """Webhook should accept requests when no secret is configured."""
        clear_rate_limit_caches()
        test_queue = Queue()

        config = {
            "security": {}  # No webhook_secret
        }

        app = create_app(test_queue, config=config)
        app.config["TESTING"] = True

        with app.test_client() as client:
            response = client.post(
                "/webhook/ghost",
                data=json.dumps({"some": "data"}),
                content_type="application/json"
            )
            # Should get 400 (validation error) not 401 (unauthorized)
            assert response.status_code == 400

    def test_webhook_secret_rejects_missing_header(self, test_dirs):
        """Webhook should reject requests without secret header when configured."""
        clear_rate_limit_caches()
        test_queue = Queue()

        config = {
            "security": {
                "webhook_secret": "test-webhook-secret"
            }
        }

        app = create_app(test_queue, config=config)
        app.config["TESTING"] = True

        with app.test_client() as client:
            response = client.post(
                "/webhook/ghost",
                data=json.dumps({"some": "data"}),
                content_type="application/json"
            )
            assert response.status_code == 401
            data = json.loads(response.data)
            assert data["message"] == "Unauthorized"

    def test_webhook_secret_rejects_wrong_secret(self, test_dirs):
        """Webhook should reject requests with wrong secret."""
        clear_rate_limit_caches()
        test_queue = Queue()

        config = {
            "security": {
                "webhook_secret": "test-webhook-secret"
            }
        }

        app = create_app(test_queue, config=config)
        app.config["TESTING"] = True

        with app.test_client() as client:
            response = client.post(
                "/webhook/ghost",
                data=json.dumps({"some": "data"}),
                content_type="application/json",
                headers={"X-Webhook-Secret": "wrong-secret"}
            )
            assert response.status_code == 401

    def test_webhook_secret_accepts_correct_secret(self, test_dirs):
        """Webhook should accept requests with correct secret."""
        clear_rate_limit_caches()
        test_queue = Queue()

        config = {
            "security": {
                "webhook_secret": "test-webhook-secret"
            }
        }

        app = create_app(test_queue, config=config)
        app.config["TESTING"] = True

        with app.test_client() as client:
            response = client.post(
                "/webhook/ghost",
                data=json.dumps({"some": "data"}),
                content_type="application/json",
                headers={"X-Webhook-Secret": "test-webhook-secret"}
            )
            # Should get 400 (validation error) not 401 (unauthorized)
            assert response.status_code == 400


class TestCacheControlHeaders:
    """Test Cache-Control headers on API responses."""

    @pytest.fixture
    def app_with_data(self):
        """Create Flask app with test interaction data."""
        clear_rate_limit_caches()

        test_dir = tempfile.mkdtemp()
        storage_path = os.path.join(test_dir, "interactions")
        mappings_path = os.path.join(test_dir, "syndication_mappings")
        os.makedirs(storage_path, exist_ok=True)
        os.makedirs(mappings_path, exist_ok=True)

        # Write test interaction data
        test_data = {
            "ghost_post_id": "507f1f77bcf86cd799439011",
            "updated_at": "2026-01-01T00:00:00Z",
            "syndication_links": {"mastodon": {}, "bluesky": {}},
            "platforms": {"mastodon": {}, "bluesky": {}}
        }
        with open(os.path.join(storage_path, "507f1f77bcf86cd799439011.json"), 'w') as f:
            json.dump(test_data, f)

        test_queue = Queue()
        config = {"security": {}}

        app = create_app(test_queue, config=config)
        app.config["TESTING"] = True
        app.config["INTERACTIONS_STORAGE_PATH"] = storage_path
        app.config["SYNDICATION_MAPPINGS_PATH"] = mappings_path

        yield app

        shutil.rmtree(test_dir)

    def test_api_response_has_cache_control(self, app_with_data):
        """API responses should include Cache-Control: no-store."""
        with app_with_data.test_client() as client:
            response = client.get("/api/interactions/507f1f77bcf86cd799439011")
            assert response.status_code == 200
            assert "no-store" in response.headers.get("Cache-Control", "")
            assert response.headers.get("Pragma") == "no-cache"

    def test_non_api_response_no_cache_control(self, app_with_data):
        """Non-API responses should not have the API Cache-Control header."""
        with app_with_data.test_client() as client:
            response = client.get("/health")
            assert response.status_code == 200
            # Should not have the restrictive API cache control
            cache_control = response.headers.get("Cache-Control", "")
            assert "no-store" not in cache_control


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
