"""
Tests for W3C webmention receiver and query endpoint.

Covers:
- POST /webmention receiver (validation, rate limiting, storage)
- GET /api/webmentions query endpoint
- Webmention verification logic (source link check, microformats parsing)
- Storage methods for received webmentions

Running Tests:
    $ PYTHONPATH=src python -m pytest tests/test_webmention_receiver.py -v
"""
import pytest
import tempfile
from queue import Queue
from unittest.mock import patch, MagicMock

from ghost.ghost import create_app, clear_rate_limit_caches
from interactions.storage import InteractionDataStore
from indieweb.receiver import (
    verify_webmention,
    _source_links_to_target,
    _extract_hentry_metadata,
    _determine_mention_type,
)


# =========================================================================
# Fixtures
# =========================================================================

@pytest.fixture
def receiver_config():
    """Config with webmention receiver enabled."""
    return {
        "webmention_receiver": {
            "enabled": True,
            "allowed_target_origins": ["https://blog.example.com"],
            "rate_limit": 10,
            "rate_limit_window_seconds": 60,
        },
        "webmention_reply": {
            "enabled": False,
        },
        "interactions": {"cache_directory": ""},
        "cors": {"enabled": False},
        "pushover": {"enabled": False},
    }


@pytest.fixture
def app_with_receiver(receiver_config, tmp_path):
    """Flask test app with webmention receiver enabled."""
    receiver_config["interactions"]["cache_directory"] = str(tmp_path)
    q = Queue()
    app = create_app(q, config=receiver_config)
    app.config["INTERACTIONS_STORAGE_PATH"] = str(tmp_path)
    app.config["TESTING"] = True
    return app


@pytest.fixture
def client(app_with_receiver):
    """Flask test client."""
    return app_with_receiver.test_client()


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


# =========================================================================
# POST /webmention - Receiver Endpoint Tests
# =========================================================================

class TestReceiverEndpoint:
    def test_valid_webmention_returns_202(self, client):
        """POST with valid source and target returns 202 Accepted."""
        with patch("indieweb.webmention._is_private_or_loopback", return_value=False), \
             patch("indieweb.receiver.verify_webmention"):
            response = client.post(
                "/webmention",
                data={"source": "https://external.example.com/post", "target": "https://blog.example.com/my-post"},
                content_type="application/x-www-form-urlencoded",
            )
        assert response.status_code == 202
        data = response.get_json()
        assert data["status"] == "accepted"

    def test_missing_source_returns_400(self, client):
        response = client.post(
            "/webmention",
            data={"target": "https://blog.example.com/my-post"},
            content_type="application/x-www-form-urlencoded",
        )
        assert response.status_code == 400

    def test_missing_target_returns_400(self, client):
        response = client.post(
            "/webmention",
            data={"source": "https://external.example.com/post"},
            content_type="application/x-www-form-urlencoded",
        )
        assert response.status_code == 400

    def test_missing_both_returns_400(self, client):
        response = client.post(
            "/webmention",
            data={},
            content_type="application/x-www-form-urlencoded",
        )
        assert response.status_code == 400

    def test_invalid_content_type_returns_415(self, client):
        response = client.post(
            "/webmention",
            data='{"source": "https://a.com", "target": "https://b.com"}',
            content_type="application/json",
        )
        assert response.status_code == 415

    def test_invalid_source_url_returns_400(self, client):
        response = client.post(
            "/webmention",
            data={"source": "not-a-url", "target": "https://blog.example.com/my-post"},
            content_type="application/x-www-form-urlencoded",
        )
        assert response.status_code == 400

    def test_invalid_target_url_returns_400(self, client):
        response = client.post(
            "/webmention",
            data={"source": "https://external.example.com/post", "target": "ftp://invalid"},
            content_type="application/x-www-form-urlencoded",
        )
        assert response.status_code == 400

    def test_target_not_in_allowed_origins_returns_400(self, client):
        response = client.post(
            "/webmention",
            data={
                "source": "https://external.example.com/post",
                "target": "https://other-site.com/post",
            },
            content_type="application/x-www-form-urlencoded",
        )
        assert response.status_code == 400

    def test_private_source_blocked(self, client):
        with patch("indieweb.webmention._is_private_or_loopback", return_value=True):
            response = client.post(
                "/webmention",
                data={
                    "source": "https://localhost/post",
                    "target": "https://blog.example.com/my-post",
                },
                content_type="application/x-www-form-urlencoded",
            )
        assert response.status_code == 400

    def test_rate_limit_returns_429(self, client):
        """Exceeding rate limit returns 429."""
        with patch("indieweb.webmention._is_private_or_loopback", return_value=False), \
             patch("indieweb.receiver.verify_webmention"):
            for _ in range(10):
                client.post(
                    "/webmention",
                    data={
                        "source": "https://external.example.com/post",
                        "target": "https://blog.example.com/my-post",
                    },
                    content_type="application/x-www-form-urlencoded",
                )
            # 11th request should be rate limited
            response = client.post(
                "/webmention",
                data={
                    "source": "https://external.example.com/post",
                    "target": "https://blog.example.com/my-post",
                },
                content_type="application/x-www-form-urlencoded",
            )
        assert response.status_code == 429

    def test_disabled_receiver_returns_404(self, tmp_path):
        """Disabled receiver returns 404."""
        config = {
            "webmention_receiver": {"enabled": False},
            "webmention_reply": {"enabled": False},
            "interactions": {"cache_directory": str(tmp_path)},
            "cors": {"enabled": False},
            "pushover": {"enabled": False},
        }
        q = Queue()
        app = create_app(q, config=config)
        app.config["TESTING"] = True
        clear_rate_limit_caches()

        with app.test_client() as c:
            response = c.post(
                "/webmention",
                data={
                    "source": "https://external.example.com/post",
                    "target": "https://blog.example.com/my-post",
                },
                content_type="application/x-www-form-urlencoded",
            )
        assert response.status_code == 404


# =========================================================================
# GET /api/webmentions - Query Endpoint Tests
# =========================================================================

class TestQueryEndpoint:
    def test_query_with_valid_target(self, client, app_with_receiver):
        """GET with valid target returns webmentions array."""
        # Insert a verified webmention directly
        storage_path = app_with_receiver.config["INTERACTIONS_STORAGE_PATH"]
        store = InteractionDataStore(storage_path)
        store.put_received_webmention("https://source.example.com/post", "https://blog.example.com/my-post", "2024-01-01T00:00:00Z")
        store.update_webmention_verification(
            source="https://source.example.com/post",
            target="https://blog.example.com/my-post",
            status="verified",
            mention_type="reply",
            author_name="Test Author",
            author_url="https://source.example.com",
            content_text="Great post!",
            verified_at="2024-01-01T00:01:00Z",
        )

        response = client.get("/api/webmentions?target=https://blog.example.com/my-post")
        assert response.status_code == 200
        data = response.get_json()
        assert "webmentions" in data
        assert len(data["webmentions"]) == 1
        wm = data["webmentions"][0]
        assert wm["source_url"] == "https://source.example.com/post"
        assert wm["mention_type"] == "reply"
        assert wm["author_name"] == "Test Author"

    def test_query_without_target_returns_400(self, client):
        response = client.get("/api/webmentions")
        assert response.status_code == 400

    def test_query_empty_result(self, client):
        response = client.get("/api/webmentions?target=https://blog.example.com/no-mentions")
        assert response.status_code == 200
        data = response.get_json()
        assert data["webmentions"] == []

    def test_query_invalid_target_returns_400(self, client):
        response = client.get("/api/webmentions?target=not-a-url")
        assert response.status_code == 400

    def test_query_only_returns_verified(self, client, app_with_receiver):
        """Pending and rejected webmentions are not returned."""
        storage_path = app_with_receiver.config["INTERACTIONS_STORAGE_PATH"]
        store = InteractionDataStore(storage_path)
        target = "https://blog.example.com/my-post"

        # One pending
        store.put_received_webmention("https://pending.example.com", target, "2024-01-01T00:00:00Z")
        # One rejected
        store.put_received_webmention("https://rejected.example.com", target, "2024-01-01T00:00:00Z")
        store.update_webmention_verification(
            source="https://rejected.example.com", target=target,
            status="rejected", verified_at="2024-01-01T00:01:00Z",
        )
        # One verified
        store.put_received_webmention("https://verified.example.com", target, "2024-01-01T00:00:00Z")
        store.update_webmention_verification(
            source="https://verified.example.com", target=target,
            status="verified", mention_type="mention",
            verified_at="2024-01-01T00:01:00Z",
        )

        response = client.get(f"/api/webmentions?target={target}")
        assert response.status_code == 200
        data = response.get_json()
        assert len(data["webmentions"]) == 1
        assert data["webmentions"][0]["source_url"] == "https://verified.example.com"

    def test_query_disabled_returns_404(self, tmp_path):
        config = {
            "webmention_receiver": {"enabled": False},
            "webmention_reply": {"enabled": False},
            "interactions": {"cache_directory": str(tmp_path)},
            "cors": {"enabled": False},
            "pushover": {"enabled": False},
        }
        q = Queue()
        app = create_app(q, config=config)
        app.config["TESTING"] = True
        clear_rate_limit_caches()

        with app.test_client() as c:
            response = c.get("/api/webmentions?target=https://blog.example.com/post")
        assert response.status_code == 404


# =========================================================================
# Verification Logic Tests
# =========================================================================

class TestSourceLinksToTarget:
    def test_exact_match(self):
        html = '<a href="https://blog.example.com/post">Link</a>'
        assert _source_links_to_target(html, "https://blog.example.com/post") is True

    def test_trailing_slash_match(self):
        html = '<a href="https://blog.example.com/post/">Link</a>'
        assert _source_links_to_target(html, "https://blog.example.com/post") is True

    def test_no_match(self):
        html = '<a href="https://other.example.com/post">Link</a>'
        assert _source_links_to_target(html, "https://blog.example.com/post") is False

    def test_link_tag_match(self):
        html = '<link rel="canonical" href="https://blog.example.com/post">'
        assert _source_links_to_target(html, "https://blog.example.com/post") is True


class TestExtractHentryMetadata:
    def test_basic_hentry(self):
        html = """
        <div class="h-entry">
            <a class="p-author h-card" href="https://author.example.com">
                <img class="u-photo" src="https://author.example.com/photo.jpg">
                Jane Doe
            </a>
            <div class="e-content">This is a reply.</div>
            <a class="u-in-reply-to" href="https://blog.example.com/post"></a>
        </div>
        """
        metadata = _extract_hentry_metadata(html, "https://source.example.com/reply", "https://blog.example.com/post")
        assert metadata["mention_type"] == "reply"
        assert metadata["author_name"] == "Jane Doe"
        assert metadata["content_text"] == "This is a reply."

    def test_like_of(self):
        html = """
        <div class="h-entry">
            <a class="u-like-of" href="https://blog.example.com/post"></a>
        </div>
        """
        metadata = _extract_hentry_metadata(html, "https://source.example.com", "https://blog.example.com/post")
        assert metadata["mention_type"] == "like"

    def test_repost_of(self):
        html = """
        <div class="h-entry">
            <a class="u-repost-of" href="https://blog.example.com/post"></a>
        </div>
        """
        metadata = _extract_hentry_metadata(html, "https://source.example.com", "https://blog.example.com/post")
        assert metadata["mention_type"] == "repost"

    def test_plain_mention(self):
        html = """
        <div class="h-entry">
            <div class="e-content">
                Check out <a href="https://blog.example.com/post">this post</a>!
            </div>
        </div>
        """
        metadata = _extract_hentry_metadata(html, "https://source.example.com", "https://blog.example.com/post")
        assert metadata["mention_type"] == "mention"

    def test_no_microformats(self):
        html = "<html><body><p>Just text</p></body></html>"
        metadata = _extract_hentry_metadata(html, "https://source.example.com", "https://blog.example.com/post")
        assert metadata["mention_type"] == "mention"
        assert metadata["author_name"] == ""


class TestVerifyWebmention:
    def test_source_links_to_target_verified(self, store):
        """Source page that links to target is verified."""
        html = '<html><body><a href="https://blog.example.com/post">Link</a></body></html>'
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.encoding = "utf-8"
        mock_response.iter_content = MagicMock(return_value=[html.encode()])
        mock_response.close = MagicMock()

        source = "https://source.example.com/post"
        target = "https://blog.example.com/post"
        store.put_received_webmention(source, target, "2024-01-01T00:00:00Z")

        with patch("indieweb.receiver._is_private_or_loopback", return_value=False), \
             patch("indieweb.receiver._build_session") as mock_session:
            mock_session.return_value.get.return_value = mock_response
            verify_webmention(source, target, store)

        webmentions = store.get_webmentions_for_target(target)
        assert len(webmentions) == 1
        assert webmentions[0]["source_url"] == source

    def test_source_does_not_link_to_target_rejected(self, store):
        """Source page without link to target is rejected."""
        html = '<html><body><a href="https://other.example.com">Other</a></body></html>'
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.encoding = "utf-8"
        mock_response.iter_content = MagicMock(return_value=[html.encode()])
        mock_response.close = MagicMock()

        source = "https://source.example.com/post"
        target = "https://blog.example.com/post"
        store.put_received_webmention(source, target, "2024-01-01T00:00:00Z")

        with patch("indieweb.receiver._is_private_or_loopback", return_value=False), \
             patch("indieweb.receiver._build_session") as mock_session:
            mock_session.return_value.get.return_value = mock_response
            verify_webmention(source, target, store)

        webmentions = store.get_webmentions_for_target(target)
        assert len(webmentions) == 0  # rejected, not returned

    def test_source_404_deletes_webmention(self, store):
        """Source returning 404 deletes the webmention."""
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.ok = False
        mock_response.close = MagicMock()

        source = "https://source.example.com/post"
        target = "https://blog.example.com/post"
        store.put_received_webmention(source, target, "2024-01-01T00:00:00Z")

        with patch("indieweb.receiver._is_private_or_loopback", return_value=False), \
             patch("indieweb.receiver._build_session") as mock_session:
            mock_session.return_value.get.return_value = mock_response
            verify_webmention(source, target, store)

        # Should be deleted, not just rejected
        webmentions = store.get_webmentions_for_target(target)
        assert len(webmentions) == 0

    def test_source_410_deletes_webmention(self, store):
        """Source returning 410 Gone deletes the webmention."""
        mock_response = MagicMock()
        mock_response.status_code = 410
        mock_response.ok = False
        mock_response.close = MagicMock()

        source = "https://source.example.com/post"
        target = "https://blog.example.com/post"
        store.put_received_webmention(source, target, "2024-01-01T00:00:00Z")

        with patch("indieweb.receiver._is_private_or_loopback", return_value=False), \
             patch("indieweb.receiver._build_session") as mock_session:
            mock_session.return_value.get.return_value = mock_response
            verify_webmention(source, target, store)

        webmentions = store.get_webmentions_for_target(target)
        assert len(webmentions) == 0

    def test_ssrf_blocked_rejected(self, store):
        """Private/loopback source URL is rejected."""
        source = "https://localhost/post"
        target = "https://blog.example.com/post"
        store.put_received_webmention(source, target, "2024-01-01T00:00:00Z")

        with patch("indieweb.receiver._is_private_or_loopback", return_value=True):
            verify_webmention(source, target, store)

        webmentions = store.get_webmentions_for_target(target)
        assert len(webmentions) == 0  # rejected


# =========================================================================
# Storage Tests
# =========================================================================

class TestReceivedWebmentionStorage:
    def test_put_and_get(self, store):
        store.put_received_webmention("https://s.com", "https://t.com", "2024-01-01T00:00:00Z")
        store.update_webmention_verification(
            source="https://s.com", target="https://t.com",
            status="verified", mention_type="mention",
            verified_at="2024-01-01T00:01:00Z",
        )
        results = store.get_webmentions_for_target("https://t.com")
        assert len(results) == 1
        assert results[0]["source_url"] == "https://s.com"

    def test_upsert_resets_to_pending(self, store):
        """Re-submitting a webmention resets status to pending."""
        store.put_received_webmention("https://s.com", "https://t.com", "2024-01-01T00:00:00Z")
        store.update_webmention_verification(
            source="https://s.com", target="https://t.com",
            status="verified", verified_at="2024-01-01T00:01:00Z",
        )
        # Re-submit
        store.put_received_webmention("https://s.com", "https://t.com", "2024-01-02T00:00:00Z")
        # Should be pending again, not returned in verified query
        results = store.get_webmentions_for_target("https://t.com")
        assert len(results) == 0

    def test_delete(self, store):
        store.put_received_webmention("https://s.com", "https://t.com", "2024-01-01T00:00:00Z")
        assert store.delete_received_webmention("https://s.com", "https://t.com") is True
        assert store.delete_received_webmention("https://s.com", "https://t.com") is False

    def test_empty_source_skipped(self, store):
        store.put_received_webmention("", "https://t.com", "2024-01-01T00:00:00Z")
        results = store.get_webmentions_for_target("https://t.com")
        assert len(results) == 0

    def test_multiple_targets(self, store):
        """Webmentions for different targets are separated."""
        store.put_received_webmention("https://s1.com", "https://t1.com", "2024-01-01T00:00:00Z")
        store.put_received_webmention("https://s2.com", "https://t2.com", "2024-01-01T00:00:00Z")
        store.update_webmention_verification(
            source="https://s1.com", target="https://t1.com",
            status="verified", verified_at="2024-01-01T00:01:00Z",
        )
        store.update_webmention_verification(
            source="https://s2.com", target="https://t2.com",
            status="verified", verified_at="2024-01-01T00:01:00Z",
        )
        r1 = store.get_webmentions_for_target("https://t1.com")
        r2 = store.get_webmentions_for_target("https://t2.com")
        assert len(r1) == 1
        assert len(r2) == 1
        assert r1[0]["source_url"] == "https://s1.com"
        assert r2[0]["source_url"] == "https://s2.com"
