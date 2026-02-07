"""
Unit Tests for Webmention Receiver Endpoint.

Tests the W3C Webmention receiving endpoint that accepts incoming
webmentions for Ghost blog posts, including URL validation,
Ghost post restriction, source verification, and storage.

Running Tests:
    $ pytest tests/test_webmention_receiver.py -v
"""
import pytest
from queue import Queue
from unittest.mock import patch, MagicMock

from ghost.ghost import create_app
from indieweb.webmention_receiver import (
    ReceivedWebmention,
    WebmentionStore,
    _is_valid_url,
    _is_ghost_post_url,
    _verify_source_links_to_target,
)


BLOG_URL = "https://blog.example.com"


def _make_config(receiver_enabled=True, blog_url=BLOG_URL):
    """Create a test configuration with webmention receiver settings."""
    return {
        "ghost": {
            "content_api": {
                "url": blog_url,
                "key": "test-key",
            }
        },
        "webmention": {
            "receiver_enabled": receiver_enabled,
        },
    }


@pytest.fixture
def app_and_client():
    """Create Flask test client with webmention receiver enabled."""
    config = _make_config()
    test_queue = Queue()
    app = create_app(test_queue, config=config)
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield app, client


@pytest.fixture
def client(app_and_client):
    """Shortcut for just the test client."""
    _, client = app_and_client
    return client


@pytest.fixture
def disabled_client():
    """Create Flask test client with webmention receiver disabled."""
    config = _make_config(receiver_enabled=False)
    test_queue = Queue()
    app = create_app(test_queue, config=config)
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


# =============================================================================
# URL Validation Tests
# =============================================================================


class TestIsValidUrl:
    """Tests for _is_valid_url helper."""

    def test_valid_https(self):
        assert _is_valid_url("https://example.com/post") is True

    def test_valid_http(self):
        assert _is_valid_url("http://example.com/post") is True

    def test_empty_string(self):
        assert _is_valid_url("") is False

    def test_none(self):
        assert _is_valid_url(None) is False

    def test_no_scheme(self):
        assert _is_valid_url("example.com/post") is False

    def test_ftp_scheme(self):
        assert _is_valid_url("ftp://example.com/file") is False

    def test_too_long(self):
        assert _is_valid_url("https://example.com/" + "a" * 3000) is False

    def test_javascript_scheme(self):
        assert _is_valid_url("javascript:alert(1)") is False


class TestIsGhostPostUrl:
    """Tests for _is_ghost_post_url helper."""

    def test_valid_post_url(self):
        assert _is_ghost_post_url(
            "https://blog.example.com/my-post/", BLOG_URL
        ) is True

    def test_valid_post_url_no_trailing_slash(self):
        assert _is_ghost_post_url(
            "https://blog.example.com/my-post", BLOG_URL
        ) is True

    def test_nested_path(self):
        assert _is_ghost_post_url(
            "https://blog.example.com/category/my-post/", BLOG_URL
        ) is True

    def test_root_url_rejected(self):
        """Root URL of the blog is not a post."""
        assert _is_ghost_post_url(BLOG_URL, BLOG_URL) is False
        assert _is_ghost_post_url(BLOG_URL + "/", BLOG_URL) is False

    def test_different_domain_rejected(self):
        assert _is_ghost_post_url(
            "https://evil.com/my-post/", BLOG_URL
        ) is False

    def test_subdomain_rejected(self):
        assert _is_ghost_post_url(
            "https://sub.blog.example.com/post", BLOG_URL
        ) is False

    def test_empty_blog_url(self):
        assert _is_ghost_post_url("https://example.com/post", "") is False

    def test_empty_target(self):
        assert _is_ghost_post_url("", BLOG_URL) is False

    def test_case_insensitive(self):
        assert _is_ghost_post_url(
            "https://Blog.Example.Com/my-post/", BLOG_URL
        ) is True


# =============================================================================
# Source Verification Tests
# =============================================================================


class TestVerifySourceLinksToTarget:
    """Tests for _verify_source_links_to_target."""

    @patch("indieweb.webmention_receiver.requests.get")
    def test_source_contains_target(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = '<html><a href="https://blog.example.com/my-post/">link</a></html>'
        mock_get.return_value = mock_response

        verified, error = _verify_source_links_to_target(
            "https://other.site/reply", "https://blog.example.com/my-post/"
        )

        assert verified is True
        assert error is None

    @patch("indieweb.webmention_receiver.requests.get")
    def test_source_contains_target_without_trailing_slash(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = '<html><a href="https://blog.example.com/my-post">link</a></html>'
        mock_get.return_value = mock_response

        verified, error = _verify_source_links_to_target(
            "https://other.site/reply", "https://blog.example.com/my-post/"
        )

        assert verified is True
        assert error is None

    @patch("indieweb.webmention_receiver.requests.get")
    def test_source_does_not_contain_target(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "<html><p>No links here</p></html>"
        mock_get.return_value = mock_response

        verified, error = _verify_source_links_to_target(
            "https://other.site/reply", "https://blog.example.com/my-post/"
        )

        assert verified is False
        assert "does not contain a link" in error

    @patch("indieweb.webmention_receiver.requests.get")
    def test_source_returns_404(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_get.return_value = mock_response

        verified, error = _verify_source_links_to_target(
            "https://other.site/gone", "https://blog.example.com/my-post/"
        )

        assert verified is False
        assert "404" in error

    @patch("indieweb.webmention_receiver.requests.get")
    def test_source_timeout(self, mock_get):
        import requests as req
        mock_get.side_effect = req.exceptions.Timeout("timed out")

        verified, error = _verify_source_links_to_target(
            "https://slow.site/reply", "https://blog.example.com/my-post/"
        )

        assert verified is False
        assert "Timeout" in error

    @patch("indieweb.webmention_receiver.requests.get")
    def test_source_connection_error(self, mock_get):
        import requests as req
        mock_get.side_effect = req.exceptions.ConnectionError("refused")

        verified, error = _verify_source_links_to_target(
            "https://down.site/reply", "https://blog.example.com/my-post/"
        )

        assert verified is False
        assert "Error fetching" in error


# =============================================================================
# WebmentionStore Tests
# =============================================================================


class TestWebmentionStore:
    """Tests for WebmentionStore."""

    def test_add_and_retrieve(self):
        store = WebmentionStore()
        mention = ReceivedWebmention(
            source="https://other.site/reply",
            target="https://blog.example.com/post/",
            verified=True,
        )
        store.add(mention)

        results = store.get_for_target("https://blog.example.com/post/")
        assert len(results) == 1
        assert results[0].source == "https://other.site/reply"

    def test_empty_store(self):
        store = WebmentionStore()
        assert store.get_for_target("https://blog.example.com/post/") == []
        assert store.count() == 0

    def test_update_existing_mention(self):
        """Same source+target should replace, not duplicate."""
        store = WebmentionStore()
        mention1 = ReceivedWebmention(
            source="https://other.site/reply",
            target="https://blog.example.com/post/",
            verified=False,
        )
        mention2 = ReceivedWebmention(
            source="https://other.site/reply",
            target="https://blog.example.com/post/",
            verified=True,
        )
        store.add(mention1)
        store.add(mention2)

        results = store.get_for_target("https://blog.example.com/post/")
        assert len(results) == 1
        assert results[0].verified is True

    def test_multiple_sources_same_target(self):
        store = WebmentionStore()
        store.add(ReceivedWebmention(
            source="https://site-a.com/reply",
            target="https://blog.example.com/post/",
            verified=True,
        ))
        store.add(ReceivedWebmention(
            source="https://site-b.com/reply",
            target="https://blog.example.com/post/",
            verified=True,
        ))

        results = store.get_for_target("https://blog.example.com/post/")
        assert len(results) == 2
        assert store.count() == 2

    def test_different_targets(self):
        store = WebmentionStore()
        store.add(ReceivedWebmention(
            source="https://other.site/reply1",
            target="https://blog.example.com/post-a/",
            verified=True,
        ))
        store.add(ReceivedWebmention(
            source="https://other.site/reply2",
            target="https://blog.example.com/post-b/",
            verified=True,
        ))

        assert len(store.get_for_target("https://blog.example.com/post-a/")) == 1
        assert len(store.get_for_target("https://blog.example.com/post-b/")) == 1
        assert store.count() == 2


# =============================================================================
# Endpoint Integration Tests
# =============================================================================


class TestWebmentionEndpoint:
    """Tests for the POST /webmention endpoint."""

    @patch("indieweb.webmention_receiver._verify_source_links_to_target")
    def test_valid_webmention_form_encoded(self, mock_verify, client):
        """Test accepting a valid webmention via form data."""
        mock_verify.return_value = (True, None)

        response = client.post("/webmention", data={
            "source": "https://other.site/reply",
            "target": "https://blog.example.com/my-post/",
        })

        assert response.status_code == 202
        data = response.get_json()
        assert data["status"] == "accepted"
        assert data["verified"] is True

    @patch("indieweb.webmention_receiver._verify_source_links_to_target")
    def test_valid_webmention_json(self, mock_verify, client):
        """Test accepting a valid webmention via JSON body."""
        mock_verify.return_value = (True, None)

        response = client.post("/webmention", json={
            "source": "https://other.site/reply",
            "target": "https://blog.example.com/my-post/",
        })

        assert response.status_code == 202
        data = response.get_json()
        assert data["status"] == "accepted"

    def test_missing_source(self, client):
        response = client.post("/webmention", data={
            "target": "https://blog.example.com/my-post/",
        })

        assert response.status_code == 400
        assert "source" in response.get_json()["message"]

    def test_missing_target(self, client):
        response = client.post("/webmention", data={
            "source": "https://other.site/reply",
        })

        assert response.status_code == 400
        assert "target" in response.get_json()["message"]

    def test_invalid_source_url(self, client):
        response = client.post("/webmention", data={
            "source": "not-a-url",
            "target": "https://blog.example.com/my-post/",
        })

        assert response.status_code == 400
        assert "Invalid source" in response.get_json()["message"]

    def test_invalid_target_url(self, client):
        response = client.post("/webmention", data={
            "source": "https://other.site/reply",
            "target": "not-a-url",
        })

        assert response.status_code == 400
        assert "Invalid target" in response.get_json()["message"]

    def test_same_source_and_target(self, client):
        response = client.post("/webmention", data={
            "source": "https://blog.example.com/my-post/",
            "target": "https://blog.example.com/my-post/",
        })

        assert response.status_code == 400
        assert "different" in response.get_json()["message"]

    def test_target_not_on_blog(self, client):
        """Target must be a Ghost post on the configured blog."""
        response = client.post("/webmention", data={
            "source": "https://other.site/reply",
            "target": "https://evil.com/fake-post/",
        })

        assert response.status_code == 400
        assert "not a valid post" in response.get_json()["message"]

    def test_target_is_blog_root(self, client):
        """Root URL of the blog is not a valid post target."""
        response = client.post("/webmention", data={
            "source": "https://other.site/reply",
            "target": "https://blog.example.com/",
        })

        assert response.status_code == 400

    @patch("indieweb.webmention_receiver._verify_source_links_to_target")
    def test_unverified_webmention_still_stored(self, mock_verify, app_and_client):
        """Webmentions that fail verification are still stored."""
        mock_verify.return_value = (False, "Source does not contain a link to the target URL")
        app, client = app_and_client

        response = client.post("/webmention", data={
            "source": "https://other.site/no-link",
            "target": "https://blog.example.com/my-post/",
        })

        assert response.status_code == 202
        data = response.get_json()
        assert data["verified"] is False

        # Check it's stored
        store = app.config["WEBMENTION_STORE"]
        mentions = store.get_for_target("https://blog.example.com/my-post/")
        assert len(mentions) == 1
        assert mentions[0].verified is False


    @patch("indieweb.webmention_receiver._verify_source_links_to_target")
    def test_unverified_response_includes_error(self, mock_verify, client):
        """Widget can display the verification error to the user."""
        mock_verify.return_value = (False, "Source does not contain a link to the target URL")

        response = client.post("/webmention", data={
            "source": "https://other.site/no-link",
            "target": "https://blog.example.com/my-post/",
        })

        assert response.status_code == 202
        data = response.get_json()
        assert data["verified"] is False
        assert "verification_error" in data
        assert "does not contain a link" in data["verification_error"]

    @patch("indieweb.webmention_receiver._verify_source_links_to_target")
    def test_verified_response_no_error(self, mock_verify, client):
        """Successful verification should not include verification_error."""
        mock_verify.return_value = (True, None)

        response = client.post("/webmention", data={
            "source": "https://other.site/reply",
            "target": "https://blog.example.com/my-post/",
        })

        assert response.status_code == 202
        data = response.get_json()
        assert data["verified"] is True
        assert "verification_error" not in data


class TestWebmentionLinkHeader:
    """Tests for the Link header advertising the webmention endpoint."""

    def test_link_header_on_health(self, client):
        """All responses should include the Link header for discovery."""
        response = client.get("/health")
        assert 'rel="webmention"' in response.headers.get("Link", "")

    def test_link_header_on_webmention_get(self, client):
        response = client.get("/webmention")
        assert 'rel="webmention"' in response.headers.get("Link", "")

    @patch("indieweb.webmention_receiver._verify_source_links_to_target")
    def test_link_header_on_webmention_post(self, mock_verify, client):
        mock_verify.return_value = (True, None)
        response = client.post("/webmention", data={
            "source": "https://other.site/reply",
            "target": "https://blog.example.com/my-post/",
        })
        assert 'rel="webmention"' in response.headers.get("Link", "")


class TestWebmentionGetEndpoint:
    """Tests for the GET /webmention endpoint."""

    def test_get_endpoint_info(self, client):
        response = client.get("/webmention")

        assert response.status_code == 200
        data = response.get_json()
        assert data["status"] == "ok"
        assert data["blog_url"] == BLOG_URL
        assert data["total_webmentions"] == 0


class TestWebmentionRetrievalEndpoint:
    """Tests for the GET /api/webmentions/<path> endpoint."""

    @patch("indieweb.webmention_receiver._verify_source_links_to_target")
    def test_get_webmentions_for_post(self, mock_verify, app_and_client):
        mock_verify.return_value = (True, None)
        app, client = app_and_client

        # First, send a webmention
        client.post("/webmention", data={
            "source": "https://other.site/reply",
            "target": "https://blog.example.com/my-post/",
        })

        # Now retrieve it
        response = client.get("/api/webmentions/my-post/")

        assert response.status_code == 200
        data = response.get_json()
        assert data["count"] == 1
        assert data["webmentions"][0]["source"] == "https://other.site/reply"
        assert data["webmentions"][0]["verified"] is True

    def test_get_webmentions_empty(self, client):
        response = client.get("/api/webmentions/nonexistent-post/")

        assert response.status_code == 200
        data = response.get_json()
        assert data["count"] == 0
        assert data["webmentions"] == []


class TestWebmentionReceiverDisabled:
    """Tests when webmention receiver is disabled."""

    def test_endpoint_not_registered_when_disabled(self, disabled_client):
        response = disabled_client.post("/webmention", data={
            "source": "https://other.site/reply",
            "target": "https://blog.example.com/my-post/",
        })

        assert response.status_code == 404

    def test_get_not_registered_when_disabled(self, disabled_client):
        response = disabled_client.get("/webmention")
        assert response.status_code == 404
