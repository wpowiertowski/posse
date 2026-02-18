"""
Unit Tests for IndieWeb Module.

This test suite validates the webmention integration functionality,
including the generic WebmentionClient, tag-based filtering, and
configuration parsing.

Test Coverage:
    - WebmentionClient initialization and configuration
    - Tag-matched webmention sending (successful and failed)
    - Error response parsing
    - Tag checking utilities
    - Configuration parsing

Testing Strategy:
    Uses unittest.mock to simulate HTTP interactions without
    making actual network requests.

Running Tests:
    $ pytest tests/test_indieweb.py -v
    $ pytest tests/test_indieweb.py --cov=indieweb
"""
import pytest
from unittest.mock import patch, MagicMock
import requests

from indieweb.webmention import (
    WebmentionClient,
    WebmentionTarget,
    WebmentionResult,
    _is_private_or_loopback,
    _build_session,
    WEBMENTION_USER_AGENT,
    MAX_DISCOVERY_RESPONSE_BYTES,
    MAX_REDIRECTS,
    discover_webmention_endpoint,
    send_webmention,
)
from indieweb.utils import has_tag, get_webmention_config


class TestWebmentionResult:
    """Test suite for WebmentionResult dataclass."""

    def test_success_result(self):
        """Test creating a successful result."""
        result = WebmentionResult(
            success=True,
            status_code=200,
            message="Webmention accepted",
            location="https://example.com/status/123",
            target_name="Test Target",
        )

        assert result.success is True
        assert result.status_code == 200
        assert result.message == "Webmention accepted"
        assert result.location == "https://example.com/status/123"
        assert result.target_name == "Test Target"

    def test_failure_result(self):
        """Test creating a failure result."""
        result = WebmentionResult(
            success=False,
            status_code=400,
            message="no_link_found: The source document does not contain a link to the target"
        )

        assert result.success is False
        assert result.status_code == 400
        assert "no_link_found" in result.message
        assert result.location is None

    def test_connection_error_result(self):
        """Test creating a connection error result."""
        result = WebmentionResult(
            success=False,
            status_code=0,
            message="Request timed out"
        )

        assert result.success is False
        assert result.status_code == 0
        assert result.message == "Request timed out"


class TestWebmentionTarget:
    """Test suite for WebmentionTarget dataclass."""

    def test_create_target(self):
        target = WebmentionTarget(
            name="Test Target",
            endpoint="https://example.com/webmention",
            target="https://example.com",
            tag="testtag",
            timeout=45.0,
        )
        assert target.name == "Test Target"
        assert target.endpoint == "https://example.com/webmention"
        assert target.target == "https://example.com"
        assert target.tag == "testtag"
        assert target.timeout == 45.0

    def test_default_timeout(self):
        target = WebmentionTarget(
            name="Test",
            endpoint="https://example.com/webmention",
            target="https://example.com",
            tag="test",
        )
        assert target.timeout == 30.0


class TestWebmentionClient:
    """Test suite for WebmentionClient class."""

    def _make_target(self, **overrides):
        defaults = {
            "name": "Test Target",
            "endpoint": "https://example.com/webmention",
            "target": "https://example.com",
            "tag": "testtag",
        }
        defaults.update(overrides)
        return WebmentionTarget(**defaults)

    def _mock_session(self, mock_response=None, side_effect=None):
        """Create a mock session for testing."""
        session = MagicMock()
        if side_effect:
            session.post.side_effect = side_effect
        elif mock_response:
            session.post.return_value = mock_response
        return session

    def test_init_empty(self):
        """Test initialization with no targets."""
        client = WebmentionClient()
        assert client.targets == []

    def test_init_with_targets(self):
        """Test initialization with targets."""
        target = self._make_target()
        client = WebmentionClient([target])
        assert len(client.targets) == 1
        assert client.targets[0] is target

    def test_from_config(self):
        """Test creating client from configuration."""
        config = {
            "webmention": {
                "targets": [
                    {
                        "name": "IndieWeb News",
                        "endpoint": "https://news.indieweb.org/en/webmention",
                        "target": "https://news.indieweb.org/en",
                        "tag": "indiewebnews",
                        "timeout": 45,
                    },
                    {
                        "name": "Another",
                        "endpoint": "https://other.example.com/webmention",
                        "target": "https://other.example.com",
                        "tag": "syndicate",
                    },
                ]
            }
        }

        client = WebmentionClient.from_config(config)

        assert len(client.targets) == 2
        assert client.targets[0].name == "IndieWeb News"
        assert client.targets[0].endpoint == "https://news.indieweb.org/en/webmention"
        assert client.targets[0].target == "https://news.indieweb.org/en"
        assert client.targets[0].tag == "indiewebnews"
        assert client.targets[0].timeout == 45
        assert client.targets[1].name == "Another"
        assert client.targets[1].timeout == 30.0  # default

    def test_from_config_empty(self):
        """Test creating client from empty configuration."""
        client = WebmentionClient.from_config({})
        assert client.targets == []

    @patch("indieweb.webmention._build_session")
    @patch("indieweb.webmention._is_private_or_loopback", return_value=False)
    def test_send_for_post_matching_tag(self, mock_private, mock_session_fn):
        """Test sending webmention when tag matches."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.headers = {"Location": "https://example.com/status/123"}
        mock_session = self._mock_session(mock_response)
        mock_session_fn.return_value = mock_session

        target = self._make_target(tag="indiewebnews")
        client = WebmentionClient([target])
        results = client.send_for_post("https://blog.example.com/my-post", ["indiewebnews"])

        assert len(results) == 1
        assert results[0].success is True
        assert results[0].status_code == 200
        assert results[0].target_name == "Test Target"
        assert results[0].endpoint == "https://example.com/webmention"

        call_args = mock_session.post.call_args
        assert call_args[0][0] == "https://example.com/webmention"
        assert call_args[1]["data"]["source"] == "https://blog.example.com/my-post"
        assert call_args[1]["data"]["target"] == "https://example.com"

    def test_send_for_post_no_matching_tag(self):
        """Test that no webmention is sent when tag doesn't match."""
        target = self._make_target(tag="indiewebnews")
        client = WebmentionClient([target])
        results = client.send_for_post("https://blog.example.com/my-post", ["technology"])

        assert results == []

    @patch("indieweb.webmention._build_session")
    @patch("indieweb.webmention._is_private_or_loopback", return_value=False)
    def test_send_for_post_case_insensitive_tags(self, mock_private, mock_session_fn):
        """Test that tag matching is case-insensitive."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.headers = {}
        mock_session_fn.return_value = self._mock_session(mock_response)

        target = self._make_target(tag="IndieWebNews")
        client = WebmentionClient([target])
        results = client.send_for_post("https://blog.example.com/my-post", ["indiewebnews"])

        assert len(results) == 1
        assert results[0].success is True

    @patch("indieweb.webmention._build_session")
    @patch("indieweb.webmention._is_private_or_loopback", return_value=False)
    def test_send_for_post_multiple_targets(self, mock_private, mock_session_fn):
        """Test sending to multiple matching targets."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.headers = {}
        mock_session_fn.return_value = self._mock_session(mock_response)

        target1 = self._make_target(name="Target 1", tag="syndicate")
        target2 = self._make_target(name="Target 2", tag="syndicate",
                                     endpoint="https://other.example.com/wm",
                                     target="https://other.example.com")
        target3 = self._make_target(name="Target 3", tag="othertag")
        client = WebmentionClient([target1, target2, target3])
        results = client.send_for_post("https://blog.example.com/post", ["syndicate"])

        assert len(results) == 2
        assert results[0].target_name == "Target 1"
        assert results[1].target_name == "Target 2"

    @patch("indieweb.webmention._build_session")
    @patch("indieweb.webmention._is_private_or_loopback", return_value=False)
    def test_send_webmention_accepted_201(self, mock_private, mock_session_fn):
        """Test webmention accepted with 201 status."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 201
        mock_response.headers = {}
        mock_session_fn.return_value = self._mock_session(mock_response)

        target = self._make_target()
        client = WebmentionClient([target])
        results = client.send_for_post("https://blog.example.com/my-post", ["testtag"])

        assert results[0].success is True
        assert results[0].status_code == 201

    @patch("indieweb.webmention._build_session")
    @patch("indieweb.webmention._is_private_or_loopback", return_value=False)
    def test_send_webmention_accepted_202(self, mock_private, mock_session_fn):
        """Test webmention accepted with 202 status."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 202
        mock_response.headers = {}
        mock_session_fn.return_value = self._mock_session(mock_response)

        target = self._make_target()
        client = WebmentionClient([target])
        results = client.send_for_post("https://blog.example.com/my-post", ["testtag"])

        assert results[0].success is True
        assert results[0].status_code == 202

    @patch("indieweb.webmention._build_session")
    @patch("indieweb.webmention._is_private_or_loopback", return_value=False)
    def test_send_webmention_no_link_found(self, mock_private, mock_session_fn):
        """Test webmention rejection when u-syndication link is missing."""
        mock_response = MagicMock()
        mock_response.ok = False
        mock_response.status_code = 400
        mock_response.json.return_value = {
            "error": "no_link_found",
            "error_description": "The source document does not contain a link to the target"
        }
        mock_session_fn.return_value = self._mock_session(mock_response)

        target = self._make_target()
        client = WebmentionClient([target])
        results = client.send_for_post("https://blog.example.com/my-post", ["testtag"])

        assert results[0].success is False
        assert results[0].status_code == 400
        assert "does not contain a link" in results[0].message

    @patch("indieweb.webmention._build_session")
    @patch("indieweb.webmention._is_private_or_loopback", return_value=False)
    def test_send_webmention_error_json_without_description(self, mock_private, mock_session_fn):
        """Test error parsing when error_description is missing."""
        mock_response = MagicMock()
        mock_response.ok = False
        mock_response.status_code = 400
        mock_response.json.return_value = {
            "error": "unknown_error"
        }
        mock_session_fn.return_value = self._mock_session(mock_response)

        target = self._make_target()
        client = WebmentionClient([target])
        results = client.send_for_post("https://blog.example.com/my-post", ["testtag"])

        assert results[0].success is False
        assert "unknown_error" in results[0].message

    @patch("indieweb.webmention._build_session")
    @patch("indieweb.webmention._is_private_or_loopback", return_value=False)
    def test_send_webmention_error_text_response(self, mock_private, mock_session_fn):
        """Test error parsing when response is plain text."""
        mock_response = MagicMock()
        mock_response.ok = False
        mock_response.status_code = 500
        mock_response.json.side_effect = Exception("Not JSON")
        mock_response.text = "Internal Server Error"
        mock_response.reason = "Internal Server Error"
        mock_session_fn.return_value = self._mock_session(mock_response)

        target = self._make_target()
        client = WebmentionClient([target])
        results = client.send_for_post("https://blog.example.com/my-post", ["testtag"])

        assert results[0].success is False
        assert results[0].status_code == 500
        assert "500" in results[0].message

    @patch("indieweb.webmention._build_session")
    @patch("indieweb.webmention._is_private_or_loopback", return_value=False)
    def test_send_webmention_timeout(self, mock_private, mock_session_fn):
        """Test webmention request timeout."""
        mock_session_fn.return_value = self._mock_session(
            side_effect=requests.exceptions.Timeout("Request timed out")
        )

        target = self._make_target()
        client = WebmentionClient([target])
        results = client.send_for_post("https://blog.example.com/my-post", ["testtag"])

        assert results[0].success is False
        assert results[0].status_code == 0
        assert "timed out" in results[0].message

    @patch("indieweb.webmention._build_session")
    @patch("indieweb.webmention._is_private_or_loopback", return_value=False)
    def test_send_webmention_connection_error(self, mock_private, mock_session_fn):
        """Test webmention connection error."""
        mock_session_fn.return_value = self._mock_session(
            side_effect=requests.exceptions.ConnectionError("Connection refused")
        )

        target = self._make_target()
        client = WebmentionClient([target])
        results = client.send_for_post("https://blog.example.com/my-post", ["testtag"])

        assert results[0].success is False
        assert results[0].status_code == 0
        assert "Request failed" in results[0].message

    @patch("indieweb.webmention._build_session")
    @patch("indieweb.webmention._is_private_or_loopback", return_value=False)
    def test_send_webmention_timeout_value(self, mock_private, mock_session_fn):
        """Test that custom timeout is passed to requests."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.headers = {}
        mock_session = self._mock_session(mock_response)
        mock_session_fn.return_value = mock_session

        target = self._make_target(timeout=60.0)
        client = WebmentionClient([target])
        client.send_for_post("https://blog.example.com/my-post", ["testtag"])

        assert mock_session.post.call_args[1]["timeout"] == 60.0


class TestHasTag:
    """Test suite for has_tag utility function."""

    def test_tag_present_by_slug(self):
        """Test detection when tag is present by slug."""
        tags = [
            {"name": "Technology", "slug": "technology"},
            {"name": "IndieWebNews", "slug": "indiewebnews"}
        ]

        assert has_tag(tags, "indiewebnews") is True

    def test_tag_present_by_name(self):
        """Test detection when tag matches by name."""
        tags = [
            {"name": "Technology", "slug": "technology"},
            {"name": "indiewebnews", "slug": "different-slug"}
        ]

        assert has_tag(tags, "indiewebnews") is True

    def test_tag_absent(self):
        """Test when tag is not present."""
        tags = [
            {"name": "Technology", "slug": "technology"},
            {"name": "Personal", "slug": "personal"}
        ]

        assert has_tag(tags, "indiewebnews") is False

    def test_empty_tags(self):
        """Test with empty tags list."""
        assert has_tag([], "anything") is False

    def test_none_tags(self):
        """Test with None tags."""
        assert has_tag(None, "anything") is False

    def test_case_insensitive_matching(self):
        """Test that tag matching is case-insensitive."""
        tags_upper = [{"name": "INDIEWEBNEWS", "slug": "INDIEWEBNEWS"}]
        tags_mixed = [{"name": "IndieWebNews", "slug": "IndieWebNews"}]
        tags_lower = [{"name": "indiewebnews", "slug": "indiewebnews"}]

        assert has_tag(tags_upper, "indiewebnews") is True
        assert has_tag(tags_mixed, "indiewebnews") is True
        assert has_tag(tags_lower, "indiewebnews") is True

    def test_custom_tag_slug(self):
        """Test with custom tag slug."""
        tags = [
            {"name": "MyCustomTag", "slug": "mycustomtag"}
        ]

        assert has_tag(tags, "mycustomtag") is True
        assert has_tag(tags, "indiewebnews") is False

    def test_malformed_tag_dict(self):
        """Test handling of malformed tag dictionaries."""
        tags = [
            {"name": "Technology"},  # Missing slug
            {"slug": "personal"},  # Missing name
            {},  # Empty dict
            "not-a-dict"  # Not a dict at all
        ]

        assert has_tag(tags, "indiewebnews") is False

    def test_tag_with_hash_prefix(self):
        """Test that tags with # prefix are handled."""
        tags = [
            {"name": "#indiewebnews", "slug": "hash-indiewebnews"}
        ]

        # The function checks slug, which doesn't have hash
        assert has_tag(tags, "hash-indiewebnews") is True

    def test_partial_match_not_accepted(self):
        """Test that partial matches are not accepted."""
        tags = [
            {"name": "indiewebnews-extended", "slug": "indiewebnews-extended"}
        ]

        assert has_tag(tags, "indiewebnews") is False


class TestGetWebmentionConfig:
    """Test suite for get_webmention_config utility function."""

    def test_full_config(self):
        """Test extracting full webmention configuration."""
        config = {
            "webmention": {
                "enabled": True,
                "targets": [
                    {
                        "name": "IndieWeb News",
                        "endpoint": "https://news.indieweb.org/en/webmention",
                        "target": "https://news.indieweb.org/en",
                        "tag": "indiewebnews",
                        "timeout": 45,
                    }
                ],
            }
        }

        result = get_webmention_config(config)

        assert result["enabled"] is True
        assert len(result["targets"]) == 1
        assert result["targets"][0]["name"] == "IndieWeb News"
        assert result["targets"][0]["endpoint"] == "https://news.indieweb.org/en/webmention"

    def test_empty_config(self):
        """Test extracting from empty configuration uses defaults."""
        result = get_webmention_config({})

        assert result["enabled"] is False
        assert result["targets"] == []

    def test_enabled_no_targets(self):
        """Test configuration with enabled but no targets."""
        config = {
            "webmention": {
                "enabled": True,
            }
        }

        result = get_webmention_config(config)

        assert result["enabled"] is True
        assert result["targets"] == []

class TestPushoverWebmentionNotifications:
    """Test suite for Pushover webmention notifications."""

    @patch("notifications.pushover.requests.post")
    def test_notify_webmention_success(self, mock_post):
        """Test webmention success notification."""
        from notifications.pushover import PushoverNotifier

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response

        notifier = PushoverNotifier(
            app_token="test_app_token",
            user_key="test_user_key"
        )

        result = notifier.notify_webmention_success(
            post_title="My Post",
            post_url="https://blog.example.com/my-post",
            target_name="IndieWeb News",
        )

        assert result is True
        call_data = mock_post.call_args[1]["data"]
        assert "IndieWeb News" in call_data["title"]
        assert "My Post" in call_data["message"]
        assert call_data["url"] == "https://blog.example.com/my-post"
        assert call_data["priority"] == 0  # Normal priority

    @patch("notifications.pushover.requests.post")
    def test_notify_webmention_failure(self, mock_post):
        """Test webmention failure notification."""
        from notifications.pushover import PushoverNotifier

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response

        notifier = PushoverNotifier(
            app_token="test_app_token",
            user_key="test_user_key"
        )

        result = notifier.notify_webmention_failure(
            post_title="My Post",
            post_url="https://blog.example.com/my-post",
            error="no_link_found: The source document does not contain a link to the target",
            target_name="IndieWeb News",
        )

        assert result is True
        call_data = mock_post.call_args[1]["data"]
        assert "IndieWeb News" in call_data["title"]
        assert "My Post" in call_data["message"]
        assert "no_link_found" in call_data["message"]
        assert call_data["priority"] == 1  # High priority for errors


# =========================================================================
# SSRF Protection Tests
# =========================================================================

class TestIsPrivateOrLoopback:
    """Test suite for _is_private_or_loopback SSRF protection."""

    @patch("indieweb.webmention.socket.getaddrinfo")
    def test_blocks_loopback_ipv4(self, mock_getaddrinfo):
        mock_getaddrinfo.return_value = [
            (2, 1, 0, "", ("127.0.0.1", 0)),
        ]
        assert _is_private_or_loopback("http://localhost/webmention") is True

    @patch("indieweb.webmention.socket.getaddrinfo")
    def test_blocks_loopback_ipv6(self, mock_getaddrinfo):
        mock_getaddrinfo.return_value = [
            (10, 1, 0, "", ("::1", 0, 0, 0)),
        ]
        assert _is_private_or_loopback("http://localhost/webmention") is True

    @patch("indieweb.webmention.socket.getaddrinfo")
    def test_blocks_private_10_network(self, mock_getaddrinfo):
        mock_getaddrinfo.return_value = [
            (2, 1, 0, "", ("10.0.0.1", 0)),
        ]
        assert _is_private_or_loopback("http://internal.local/webmention") is True

    @patch("indieweb.webmention.socket.getaddrinfo")
    def test_blocks_private_192_168(self, mock_getaddrinfo):
        mock_getaddrinfo.return_value = [
            (2, 1, 0, "", ("192.168.1.1", 0)),
        ]
        assert _is_private_or_loopback("http://router.local/webmention") is True

    @patch("indieweb.webmention.socket.getaddrinfo")
    def test_blocks_private_172_16(self, mock_getaddrinfo):
        mock_getaddrinfo.return_value = [
            (2, 1, 0, "", ("172.16.0.1", 0)),
        ]
        assert _is_private_or_loopback("http://private.local/webmention") is True

    @patch("indieweb.webmention.socket.getaddrinfo")
    def test_allows_public_address(self, mock_getaddrinfo):
        mock_getaddrinfo.return_value = [
            (2, 1, 0, "", ("93.184.216.34", 0)),
        ]
        assert _is_private_or_loopback("https://example.com/webmention") is False

    @patch("indieweb.webmention.socket.getaddrinfo")
    def test_blocks_dns_resolution_failure(self, mock_getaddrinfo):
        import socket
        mock_getaddrinfo.side_effect = socket.gaierror("Name or service not known")
        assert _is_private_or_loopback("http://nonexistent.local/webmention") is True

    def test_blocks_url_without_hostname(self):
        assert _is_private_or_loopback("not-a-url") is True

    @patch("indieweb.webmention.socket.getaddrinfo")
    def test_blocks_link_local(self, mock_getaddrinfo):
        mock_getaddrinfo.return_value = [
            (2, 1, 0, "", ("169.254.1.1", 0)),
        ]
        assert _is_private_or_loopback("http://link-local.test/webmention") is True


# =========================================================================
# Session / User-Agent / Redirect Limit Tests
# =========================================================================

class TestBuildSession:
    """Test suite for _build_session configuration."""

    def test_user_agent_contains_webmention(self):
        session = _build_session()
        assert "Webmention" in session.headers["User-Agent"]

    def test_redirect_limit(self):
        session = _build_session()
        assert session.max_redirects == MAX_REDIRECTS
        assert session.max_redirects == 20


class TestDiscoveryProtections:
    """Test discovery with SSRF protection, redirect limit, and size cap."""

    @patch("indieweb.webmention._is_private_or_loopback")
    def test_discovery_blocks_private_target(self, mock_private):
        mock_private.return_value = True
        result = discover_webmention_endpoint("http://localhost/post")
        assert result is None

    @patch("indieweb.webmention._is_private_or_loopback", return_value=False)
    @patch("indieweb.webmention._build_session")
    def test_discovery_handles_too_many_redirects(self, mock_session_fn, mock_private):
        mock_session = MagicMock()
        mock_session.get.side_effect = requests.exceptions.TooManyRedirects("too many redirects")
        mock_session_fn.return_value = mock_session
        result = discover_webmention_endpoint("https://redirect-loop.example.com/post")
        assert result is None

    @patch("indieweb.webmention._is_private_or_loopback", return_value=False)
    @patch("indieweb.webmention._build_session")
    def test_discovery_respects_size_limit(self, mock_session_fn, mock_private):
        """Large response bodies are truncated; endpoint still found if in head."""
        mock_response = MagicMock()
        mock_response.headers = {}
        mock_response.raise_for_status = MagicMock()
        mock_response.encoding = "utf-8"
        # Simulate a response body with webmention link near the start
        html_body = b'<html><head><link rel="webmention" href="/wm" /></head>'
        html_body += b"x" * (MAX_DISCOVERY_RESPONSE_BYTES + 1000)

        # iter_content returns chunks
        def iter_chunks(chunk_size=8192, decode_unicode=False):
            offset = 0
            while offset < len(html_body):
                yield html_body[offset:offset + chunk_size]
                offset += chunk_size

        mock_response.iter_content = iter_chunks
        mock_response.close = MagicMock()

        mock_session = MagicMock()
        mock_session.get.return_value = mock_response
        mock_session_fn.return_value = mock_session

        result = discover_webmention_endpoint("https://example.com/post")
        assert result == "https://example.com/wm"


class TestSendWebmentionProtections:
    """Test send_webmention with SSRF protection and redirect limit."""

    @patch("indieweb.webmention.discover_webmention_endpoint")
    @patch("indieweb.webmention._is_private_or_loopback")
    def test_send_blocks_private_endpoint(self, mock_private, mock_discover):
        mock_discover.return_value = "http://localhost:8080/webmention"
        mock_private.return_value = True
        result = send_webmention("https://source.example.com/reply/abc", "https://target.example.com/post")
        assert result.success is False
        assert "private or loopback" in result.message

    @patch("indieweb.webmention.discover_webmention_endpoint")
    @patch("indieweb.webmention._is_private_or_loopback", return_value=False)
    @patch("indieweb.webmention._build_session")
    def test_send_handles_too_many_redirects(self, mock_session_fn, mock_private, mock_discover):
        mock_discover.return_value = "https://redirect-loop.example.com/webmention"
        mock_session = MagicMock()
        mock_session.post.side_effect = requests.exceptions.TooManyRedirects("too many redirects")
        mock_session_fn.return_value = mock_session
        result = send_webmention("https://source.example.com/reply/abc", "https://target.example.com/post")
        assert result.success is False
        assert "redirect" in result.message.lower()

    @patch("indieweb.webmention._is_private_or_loopback", return_value=True)
    @patch("indieweb.webmention.requests.post")
    def test_client_blocks_private_endpoint(self, mock_post, mock_private):
        target = WebmentionTarget(
            name="Local Target",
            endpoint="http://localhost/webmention",
            target="http://localhost",
            tag="test",
        )
        client = WebmentionClient([target])
        results = client.send_for_post("https://blog.example.com/post", ["test"])
        assert len(results) == 1
        assert results[0].success is False
        assert "private or loopback" in results[0].message
        mock_post.assert_not_called()
