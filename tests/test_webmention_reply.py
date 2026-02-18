"""
Tests for webmention reply functionality.

Covers:
- Reply validation (input sanitization, honeypot, URL validation)
- Reply storage (SQLite put/get)
- Reply h-entry rendering
- Flask endpoints (form, submission, h-entry page)
- Rate limiting for replies
- Turnstile verification
- Webmention endpoint discovery

Running Tests:
    $ PYTHONPATH=src python -m pytest tests/test_webmention_reply.py -v
"""
import json
import pytest
import tempfile
import shutil
from queue import Queue
from unittest.mock import patch, MagicMock

from ghost.ghost import create_app, clear_rate_limit_caches
from indieweb.reply import (
    generate_reply_id,
    hash_ip,
    sanitize_text,
    validate_url,
    validate_reply,
    is_honeypot_filled,
    build_reply_record,
    render_reply_hentry,
)
from indieweb.webmention import discover_webmention_endpoint, send_webmention, WebmentionResult
from interactions.storage import InteractionDataStore


# =========================================================================
# Fixtures
# =========================================================================

@pytest.fixture
def reply_config():
    """Config with webmention reply enabled."""
    return {
        "webmention_reply": {
            "enabled": True,
            "blog_name": "Test Blog",
            "allowed_target_origins": ["https://blog.example.com"],
            "rate_limit": 5,
            "rate_limit_window_seconds": 3600,
            "turnstile_site_key": "",
            "turnstile_secret_key": "",
        },
        "interactions": {"cache_directory": ""},
        "cors": {"enabled": False},
        "pushover": {"enabled": False},
    }


@pytest.fixture
def ghost_api_client():
    """Ghost API client fixture that recognizes only known canonical posts."""
    client = MagicMock()
    client.enabled = True

    def _get_post_by_slug(slug: str):
        if slug == "my-post":
            return {"url": "https://blog.example.com/my-post/"}
        return None

    client.get_post_by_slug.side_effect = _get_post_by_slug
    return client


@pytest.fixture
def app_with_replies(reply_config, tmp_path, ghost_api_client):
    """Flask test app with reply endpoints enabled."""
    reply_config["interactions"]["cache_directory"] = str(tmp_path)
    reply_config["webmention_reply"]["storage_path"] = str(tmp_path)
    q = Queue()
    app = create_app(q, config=reply_config, ghost_api_client=ghost_api_client)
    app.config["INTERACTIONS_STORAGE_PATH"] = str(tmp_path)
    app.config["TESTING"] = True
    return app


@pytest.fixture
def client(app_with_replies):
    """Flask test client."""
    return app_with_replies.test_client()


@pytest.fixture
def store(tmp_path):
    """Temporary InteractionDataStore."""
    return InteractionDataStore(str(tmp_path))


@pytest.fixture(autouse=True)
def clear_caches():
    """Clear rate limiting caches before each test."""
    clear_rate_limit_caches()
    yield
    clear_rate_limit_caches()


VALID_REPLY = {
    "author_name": "Test User",
    "author_url": "https://test.example.com",
    "content": "Great post, thanks for sharing!",
    "target": "https://blog.example.com/my-post/",
    "website": "",  # honeypot empty
}


# =========================================================================
# Unit Tests: Validation
# =========================================================================

class TestValidation:
    def test_valid_reply(self):
        errors = validate_reply(VALID_REPLY, ["https://blog.example.com"])
        assert errors == []

    def test_missing_name(self):
        data = {**VALID_REPLY, "author_name": ""}
        errors = validate_reply(data, ["https://blog.example.com"])
        assert any("Name" in e for e in errors)

    def test_missing_content(self):
        data = {**VALID_REPLY, "content": ""}
        errors = validate_reply(data, ["https://blog.example.com"])
        assert any("content" in e.lower() for e in errors)

    def test_content_too_short(self):
        data = {**VALID_REPLY, "content": "x"}
        errors = validate_reply(data, ["https://blog.example.com"])
        assert any("short" in e.lower() for e in errors)

    def test_content_too_long(self):
        data = {**VALID_REPLY, "content": "x" * 2001}
        errors = validate_reply(data, ["https://blog.example.com"])
        assert any("2000" in e for e in errors)

    def test_missing_target(self):
        data = {**VALID_REPLY, "target": ""}
        errors = validate_reply(data, ["https://blog.example.com"])
        assert any("Target" in e for e in errors)

    def test_target_wrong_origin(self):
        data = {**VALID_REPLY, "target": "https://evil.example.com/post"}
        errors = validate_reply(data, ["https://blog.example.com"])
        assert any("allowed" in e.lower() for e in errors)

    def test_invalid_author_url(self):
        data = {**VALID_REPLY, "author_url": "not-a-url"}
        errors = validate_reply(data, ["https://blog.example.com"])
        assert any("website" in e.lower() or "url" in e.lower() for e in errors)

    def test_javascript_url_rejected(self):
        data = {**VALID_REPLY, "author_url": "javascript:alert(1)"}
        errors = validate_reply(data, ["https://blog.example.com"])
        assert any("url" in e.lower() for e in errors)

    def test_honeypot_filled_returns_no_errors(self):
        """Honeypot filled = bot. Return empty errors so caller silently accepts."""
        data = {**VALID_REPLY, "website": "http://spam.com"}
        errors = validate_reply(data, ["https://blog.example.com"])
        assert errors == []

    def test_is_honeypot_filled(self):
        assert is_honeypot_filled({"website": "spam"}) is True
        assert is_honeypot_filled({"website": ""}) is False
        assert is_honeypot_filled({}) is False


class TestUrlValidation:
    def test_valid_https(self):
        assert validate_url("https://example.com") == "https://example.com"

    def test_valid_http(self):
        assert validate_url("http://example.com") == "http://example.com"

    def test_empty(self):
        assert validate_url("") is None

    def test_ftp_rejected(self):
        assert validate_url("ftp://example.com") is None

    def test_javascript_rejected(self):
        assert validate_url("javascript:alert(1)") is None

    def test_no_scheme(self):
        assert validate_url("example.com") is None


class TestUtilities:
    def test_generate_reply_id_length(self):
        rid = generate_reply_id()
        assert len(rid) == 16
        assert rid.isalnum()

    def test_generate_reply_id_unique(self):
        ids = {generate_reply_id() for _ in range(100)}
        assert len(ids) == 100

    def test_hash_ip_deterministic(self):
        h1 = hash_ip("192.168.1.1")
        h2 = hash_ip("192.168.1.1")
        assert h1 == h2
        assert len(h1) == 16

    def test_hash_ip_different_for_different_ips(self):
        assert hash_ip("192.168.1.1") != hash_ip("192.168.1.2")

    def test_sanitize_text_strips(self):
        assert sanitize_text("  hello  ", 100) == "hello"

    def test_sanitize_text_truncates(self):
        assert sanitize_text("hello world", 5) == "hello"

    def test_build_reply_record_uses_configured_timezone(self):
        reply = build_reply_record(
            VALID_REPLY,
            "127.0.0.1",
            timezone_name="America/Los_Angeles",
        )
        # PST/PDT offsets vary by date; either offset is valid.
        assert reply["created_at"].endswith("-08:00") or reply["created_at"].endswith("-07:00")


# =========================================================================
# Unit Tests: Storage
# =========================================================================

class TestReplyStorage:
    def test_put_and_get(self, store):
        reply = build_reply_record(VALID_REPLY, "127.0.0.1")
        store.put_reply(reply)

        retrieved = store.get_reply(reply["id"])
        assert retrieved is not None
        assert retrieved["author_name"] == "Test User"
        assert retrieved["content"] == "Great post, thanks for sharing!"
        assert retrieved["target"] == "https://blog.example.com/my-post/"

    def test_get_nonexistent(self, store):
        assert store.get_reply("nonexistent123456") is None

    def test_duplicate_id_fails(self, store):
        reply = build_reply_record(VALID_REPLY, "127.0.0.1")
        store.put_reply(reply)
        with pytest.raises(Exception):
            store.put_reply(reply)

    def test_delete_reply(self, store):
        reply = build_reply_record(VALID_REPLY, "127.0.0.1")
        store.put_reply(reply)

        assert store.delete_reply(reply["id"]) is True
        assert store.get_reply(reply["id"]) is None

    def test_delete_reply_nonexistent(self, store):
        assert store.delete_reply("missing-reply-id") is False


# =========================================================================
# Unit Tests: Rendering
# =========================================================================

class TestRenderHentry:
    def test_contains_microformats(self):
        reply = build_reply_record(VALID_REPLY, "127.0.0.1")
        html = render_reply_hentry(reply, "Test Blog")
        assert "h-entry" in html
        assert "h-card" in html
        assert "e-content" in html
        assert "u-in-reply-to" in html
        assert "dt-published" in html

    def test_escapes_html(self):
        data = {**VALID_REPLY, "author_name": "<script>alert(1)</script>", "content": "<b>bold</b>"}
        reply = build_reply_record(data, "127.0.0.1")
        html = render_reply_hentry(reply)
        assert "<script>" not in html
        assert "&lt;script&gt;" in html
        assert "<b>" not in html

    def test_author_url_nofollow(self):
        reply = build_reply_record(VALID_REPLY, "127.0.0.1")
        html = render_reply_hentry(reply)
        assert 'rel="nofollow noopener"' in html

    def test_noindex(self):
        reply = build_reply_record(VALID_REPLY, "127.0.0.1")
        html = render_reply_hentry(reply)
        assert "noindex" in html

    def test_no_author_url(self):
        data = {**VALID_REPLY, "author_url": ""}
        reply = build_reply_record(data, "127.0.0.1")
        html = render_reply_hentry(reply)
        assert "u-url" not in html
        assert '<span class="p-name">' in html


# =========================================================================
# Unit Tests: Webmention Discovery
# =========================================================================

class TestWebmentionDiscovery:
    @patch("indieweb.webmention._build_session")
    @patch("indieweb.webmention._is_private_or_loopback", return_value=False)
    def test_discover_from_link_header(self, mock_private, mock_session_fn):
        mock_resp = MagicMock()
        mock_resp.headers = {"Link": '<https://wm.example.com/webmention>; rel="webmention"'}
        mock_resp.ok = True
        mock_resp.raise_for_status = MagicMock()
        mock_resp.close = MagicMock()
        mock_session = MagicMock()
        mock_session.get.return_value = mock_resp
        mock_session_fn.return_value = mock_session

        endpoint = discover_webmention_endpoint("https://example.com/post")
        assert endpoint == "https://wm.example.com/webmention"

    @patch("indieweb.webmention._build_session")
    @patch("indieweb.webmention._is_private_or_loopback", return_value=False)
    def test_discover_from_html_link(self, mock_private, mock_session_fn):
        html_body = b'<html><head><link rel="webmention" href="https://wm.example.com/x/webmention" /></head></html>'
        mock_resp = MagicMock()
        mock_resp.headers = {}
        mock_resp.raise_for_status = MagicMock()
        mock_resp.encoding = "utf-8"
        mock_resp.iter_content = MagicMock(return_value=iter([html_body]))
        mock_resp.close = MagicMock()
        mock_session = MagicMock()
        mock_session.get.return_value = mock_resp
        mock_session_fn.return_value = mock_session

        endpoint = discover_webmention_endpoint("https://example.com/post")
        assert endpoint == "https://wm.example.com/x/webmention"

    @patch("indieweb.webmention._build_session")
    @patch("indieweb.webmention._is_private_or_loopback", return_value=False)
    def test_discover_from_html_link_reverse_attrs(self, mock_private, mock_session_fn):
        html_body = b'<html><head><link href="/webmention" rel="webmention" /></head></html>'
        mock_resp = MagicMock()
        mock_resp.headers = {}
        mock_resp.raise_for_status = MagicMock()
        mock_resp.encoding = "utf-8"
        mock_resp.iter_content = MagicMock(return_value=iter([html_body]))
        mock_resp.close = MagicMock()
        mock_session = MagicMock()
        mock_session.get.return_value = mock_resp
        mock_session_fn.return_value = mock_session

        endpoint = discover_webmention_endpoint("https://example.com/post")
        assert endpoint == "https://example.com/webmention"

    @patch("indieweb.webmention._build_session")
    @patch("indieweb.webmention._is_private_or_loopback", return_value=False)
    def test_discover_returns_none_when_not_found(self, mock_private, mock_session_fn):
        html_body = b"<html><body>Hello</body></html>"
        mock_resp = MagicMock()
        mock_resp.headers = {}
        mock_resp.raise_for_status = MagicMock()
        mock_resp.encoding = "utf-8"
        mock_resp.iter_content = MagicMock(return_value=iter([html_body]))
        mock_resp.close = MagicMock()
        mock_session = MagicMock()
        mock_session.get.return_value = mock_resp
        mock_session_fn.return_value = mock_session

        assert discover_webmention_endpoint("https://example.com/post") is None

    @patch("indieweb.webmention._build_session")
    @patch("indieweb.webmention._is_private_or_loopback", return_value=False)
    def test_discover_handles_network_error(self, mock_private, mock_session_fn):
        import requests as req
        mock_session = MagicMock()
        mock_session.get.side_effect = req.exceptions.ConnectionError("timeout")
        mock_session_fn.return_value = mock_session
        assert discover_webmention_endpoint("https://example.com/post") is None


class TestSendWebmention:
    @patch("indieweb.webmention._build_session")
    @patch("indieweb.webmention._is_private_or_loopback", return_value=False)
    @patch("indieweb.webmention.discover_webmention_endpoint")
    def test_successful_send(self, mock_discover, mock_private, mock_session_fn):
        mock_discover.return_value = "https://wm.example.com/webmention"
        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.status_code = 202
        mock_resp.headers = {"Location": "https://wm.example.com/status/123"}
        mock_session = MagicMock()
        mock_session.post.return_value = mock_resp
        mock_session_fn.return_value = mock_session

        result = send_webmention("https://reply.example.com/reply/abc", "https://blog.example.com/post")
        assert result.success is True
        assert result.status_code == 202

    @patch("indieweb.webmention.discover_webmention_endpoint")
    def test_no_endpoint_found(self, mock_discover):
        mock_discover.return_value = None
        result = send_webmention("https://reply.example.com/reply/abc", "https://blog.example.com/post")
        assert result.success is False
        assert "No webmention endpoint" in result.message


# =========================================================================
# Integration Tests: Flask Endpoints
# =========================================================================

class TestReplyFormEndpoint:
    def test_serves_form(self, client):
        resp = client.get("/webmention?url=https://blog.example.com/my-post/")
        assert resp.status_code == 200
        assert b"Send a Webmention" in resp.data
        assert b'data-target-valid="true"' in resp.data
        assert resp.headers.get("Cache-Control") == "no-store, max-age=0"
        assert b"Content-Security-Policy" in b"\r\n".join(
            f"{k}: {v}".encode() for k, v in resp.headers
        )

    def test_invalid_target_shows_invalid_state(self, client):
        resp = client.get("/webmention?url=https://blog.example.com/does-not-exist/")
        assert resp.status_code == 200
        assert b'data-target-valid="false"' in resp.data
        assert b"Target post does not exist." in resp.data

    def test_missing_target_shows_invalid_state(self, client):
        resp = client.get("/webmention")
        assert resp.status_code == 200
        assert b'data-target-valid="false"' in resp.data
        assert b"invalid or missing" in resp.data

    def test_disabled_returns_404(self):
        config = {
            "webmention_reply": {"enabled": False},
            "cors": {"enabled": False},
            "pushover": {"enabled": False},
        }
        app = create_app(Queue(), config=config)
        app.config["TESTING"] = True
        resp = app.test_client().get("/webmention")
        assert resp.status_code == 404


class TestSubmitReplyEndpoint:
    class _ImmediateThread:
        """Thread stub that runs target immediately for deterministic tests."""

        def __init__(self, target=None, daemon=None):
            self._target = target
            self.daemon = daemon

        def start(self):
            if self._target:
                self._target()

    @patch("indieweb.webmention.send_webmention")
    def test_successful_submission(self, mock_send, client):
        mock_send.return_value = WebmentionResult(success=True, status_code=202, message="ok")
        resp = client.post(
            "/api/webmention/reply",
            json=VALID_REPLY,
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        assert "id" in data

    @patch("threading.Thread", _ImmediateThread)
    @patch("indieweb.webmention.send_webmention")
    def test_source_url_uses_target_origin(self, mock_send, client):
        mock_send.return_value = WebmentionResult(success=True, status_code=202, message="ok")
        resp = client.post(
            "/api/webmention/reply",
            json=VALID_REPLY,
            content_type="application/json",
        )
        assert resp.status_code == 200
        reply_id = resp.get_json()["id"]

        called_source, called_target = mock_send.call_args[0]
        assert called_source == f"https://blog.example.com/reply/{reply_id}"
        assert called_target == VALID_REPLY["target"]

    def test_missing_name(self, client):
        data = {**VALID_REPLY, "author_name": ""}
        resp = client.post("/api/webmention/reply", json=data, content_type="application/json")
        assert resp.status_code == 400
        assert "Name" in resp.get_json()["error"]

    def test_missing_content(self, client):
        data = {**VALID_REPLY, "content": ""}
        resp = client.post("/api/webmention/reply", json=data, content_type="application/json")
        assert resp.status_code == 400

    def test_wrong_target_origin(self, client):
        data = {**VALID_REPLY, "target": "https://evil.com/post"}
        resp = client.post("/api/webmention/reply", json=data, content_type="application/json")
        assert resp.status_code == 400
        assert "allowed" in resp.get_json()["error"].lower()

    def test_target_post_must_exist(self, client):
        data = {**VALID_REPLY, "target": "https://blog.example.com/does-not-exist/"}
        resp = client.post("/api/webmention/reply", json=data, content_type="application/json")
        assert resp.status_code == 400
        assert "does not exist" in resp.get_json()["error"].lower()

    def test_target_must_match_canonical_post_url(self, client):
        data = {**VALID_REPLY, "target": "https://blog.example.com/2026/my-post/"}
        resp = client.post("/api/webmention/reply", json=data, content_type="application/json")
        assert resp.status_code == 400
        assert "canonical" in resp.get_json()["error"].lower()

    def test_target_root_url_rejected(self, client):
        data = {**VALID_REPLY, "target": "https://blog.example.com/"}
        resp = client.post("/api/webmention/reply", json=data, content_type="application/json")
        assert resp.status_code == 400
        assert "must point to a post" in resp.get_json()["error"].lower()

    def test_honeypot_silently_accepted(self, client):
        data = {**VALID_REPLY, "website": "http://spam.com"}
        resp = client.post("/api/webmention/reply", json=data, content_type="application/json")
        assert resp.status_code == 200
        assert resp.get_json()["id"] == "accepted"

    def test_rate_limiting(self, client):
        for i in range(5):
            resp = client.post("/api/webmention/reply", json=VALID_REPLY, content_type="application/json")
            assert resp.status_code == 200

        resp = client.post("/api/webmention/reply", json=VALID_REPLY, content_type="application/json")
        assert resp.status_code == 429

    def test_non_json_rejected(self, client):
        resp = client.post("/api/webmention/reply", data="not json", content_type="text/plain")
        assert resp.status_code == 400

    def test_disabled_returns_404(self):
        config = {
            "webmention_reply": {"enabled": False},
            "cors": {"enabled": False},
            "pushover": {"enabled": False},
        }
        app = create_app(Queue(), config=config)
        app.config["TESTING"] = True
        resp = app.test_client().post(
            "/api/webmention/reply", json=VALID_REPLY, content_type="application/json"
        )
        assert resp.status_code == 404

    def test_target_verification_unavailable_without_ghost_api(self):
        config = {
            "webmention_reply": {
                "enabled": True,
                "allowed_target_origins": ["https://blog.example.com"],
            },
            "interactions": {"cache_directory": ""},
            "cors": {"enabled": False},
            "pushover": {"enabled": False},
        }
        app = create_app(Queue(), config=config)
        app.config["TESTING"] = True
        with tempfile.TemporaryDirectory() as tmp:
            app.config["INTERACTIONS_STORAGE_PATH"] = tmp
            resp = app.test_client().post(
                "/api/webmention/reply", json=VALID_REPLY, content_type="application/json"
            )
            assert resp.status_code == 503
            assert "verification" in resp.get_json()["error"].lower()

    @patch("threading.Thread", _ImmediateThread)
    @patch("indieweb.webmention.send_webmention")
    def test_refused_4xx_reply_is_deleted(self, mock_send, client, app_with_replies):
        mock_send.return_value = WebmentionResult(
            success=False,
            status_code=400,
            message="invalid_source",
            endpoint="https://example.com/webmention",
        )
        resp = client.post(
            "/api/webmention/reply",
            json=VALID_REPLY,
            content_type="application/json",
        )
        assert resp.status_code == 200
        reply_id = resp.get_json()["id"]

        store = InteractionDataStore(app_with_replies.config["INTERACTIONS_STORAGE_PATH"])
        assert store.get_reply(reply_id) is None

    @patch("threading.Thread", _ImmediateThread)
    @patch("indieweb.webmention.send_webmention")
    def test_non_refusal_failure_keeps_reply(self, mock_send, client, app_with_replies):
        mock_send.return_value = WebmentionResult(
            success=False,
            status_code=0,
            message="Request timed out",
            endpoint="https://example.com/webmention",
        )
        resp = client.post(
            "/api/webmention/reply",
            json=VALID_REPLY,
            content_type="application/json",
        )
        assert resp.status_code == 200
        reply_id = resp.get_json()["id"]

        store = InteractionDataStore(app_with_replies.config["INTERACTIONS_STORAGE_PATH"])
        assert store.get_reply(reply_id) is not None

    @patch("threading.Thread", _ImmediateThread)
    @patch("indieweb.webmention.send_webmention")
    def test_404_refusal_reply_is_deleted(self, mock_send, client, app_with_replies):
        mock_send.return_value = WebmentionResult(
            success=False,
            status_code=404,
            message="target domain not found",
            endpoint="https://example.com/webmention",
        )
        resp = client.post(
            "/api/webmention/reply",
            json=VALID_REPLY,
            content_type="application/json",
        )
        assert resp.status_code == 200
        reply_id = resp.get_json()["id"]

        store = InteractionDataStore(app_with_replies.config["INTERACTIONS_STORAGE_PATH"])
        assert store.get_reply(reply_id) is None

    @patch("threading.Thread", _ImmediateThread)
    @patch("indieweb.webmention.send_webmention")
    def test_5xx_failure_keeps_reply(self, mock_send, client, app_with_replies):
        """Server errors should not delete the reply (may be transient)."""
        mock_send.return_value = WebmentionResult(
            success=False,
            status_code=500,
            message="Internal Server Error",
            endpoint="https://example.com/webmention",
        )
        resp = client.post(
            "/api/webmention/reply",
            json=VALID_REPLY,
            content_type="application/json",
        )
        assert resp.status_code == 200
        reply_id = resp.get_json()["id"]

        store = InteractionDataStore(app_with_replies.config["INTERACTIONS_STORAGE_PATH"])
        assert store.get_reply(reply_id) is not None


class TestReplyPageEndpoint:
    @patch("indieweb.webmention.send_webmention")
    def test_serves_hentry(self, mock_send, client, app_with_replies):
        mock_send.return_value = WebmentionResult(success=True, status_code=202, message="ok")

        # Submit a reply first
        resp = client.post("/api/webmention/reply", json=VALID_REPLY, content_type="application/json")
        reply_id = resp.get_json()["id"]

        # Fetch the h-entry page
        resp = client.get(f"/reply/{reply_id}")
        assert resp.status_code == 200
        assert b"h-entry" in resp.data
        assert b"u-in-reply-to" in resp.data
        assert b"Test User" in resp.data

    def test_invalid_id_format(self, client):
        resp = client.get("/reply/../../etc/passwd")
        assert resp.status_code == 404

    def test_nonexistent_reply(self, client):
        resp = client.get("/reply/abcdef1234567890")
        assert resp.status_code == 404


class TestTurnstileVerification:
    def test_required_when_configured(self):
        config = {
            "webmention_reply": {
                "enabled": True,
                "allowed_target_origins": ["https://blog.example.com"],
                "turnstile_secret_key": "test-secret",
            },
            "interactions": {"cache_directory": ""},
            "cors": {"enabled": False},
            "pushover": {"enabled": False},
        }
        app = create_app(Queue(), config=config)
        app.config["TESTING"] = True
        with tempfile.TemporaryDirectory() as tmp:
            app.config["INTERACTIONS_STORAGE_PATH"] = tmp
            resp = app.test_client().post(
                "/api/webmention/reply", json=VALID_REPLY, content_type="application/json"
            )
            assert resp.status_code == 400
            assert "CAPTCHA" in resp.get_json()["error"]
