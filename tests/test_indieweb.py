"""
Unit Tests for IndieWeb Module.

This test suite validates the IndieWeb integration functionality,
including webmention sending to IndieWeb News and tag-based filtering.

Test Coverage:
    - IndieWebNewsClient initialization and configuration
    - Webmention sending (successful and failed)
    - Error response parsing
    - Tag checking utilities
    - Configuration parsing

Testing Strategy:
    Uses unittest.mock to simulate HTTP interactions without
    making actual network requests. This provides:
    - Fast test execution (no network overhead)
    - Isolation (no external dependencies)
    - Deterministic results (controlled responses)
    - No actual submissions to IndieWeb News

Running Tests:
    $ pytest tests/test_indieweb.py -v
    $ pytest tests/test_indieweb.py --cov=indieweb
"""
import pytest
from unittest.mock import patch, MagicMock
import requests

from indieweb.webmention import IndieWebNewsClient, WebmentionResult, send_to_indieweb_news
from indieweb.utils import has_indieweb_tag, get_indieweb_config, DEFAULT_INDIEWEB_TAG


class TestWebmentionResult:
    """Test suite for WebmentionResult dataclass."""

    def test_success_result(self):
        """Test creating a successful result."""
        result = WebmentionResult(
            success=True,
            status_code=200,
            message="Webmention accepted",
            location="https://news.indieweb.org/status/123"
        )

        assert result.success is True
        assert result.status_code == 200
        assert result.message == "Webmention accepted"
        assert result.location == "https://news.indieweb.org/status/123"

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


class TestIndieWebNewsClient:
    """Test suite for IndieWebNewsClient class."""

    def test_init_with_defaults(self):
        """Test initialization with default values."""
        client = IndieWebNewsClient()

        assert client.endpoint == IndieWebNewsClient.DEFAULT_ENDPOINT
        assert client.target == IndieWebNewsClient.DEFAULT_TARGET
        assert client.timeout == IndieWebNewsClient.DEFAULT_TIMEOUT

    def test_init_with_custom_values(self):
        """Test initialization with custom values."""
        client = IndieWebNewsClient(
            endpoint="https://custom.endpoint/webmention",
            target="https://custom.target/page",
            timeout=60.0
        )

        assert client.endpoint == "https://custom.endpoint/webmention"
        assert client.target == "https://custom.target/page"
        assert client.timeout == 60.0

    def test_from_config_with_custom_values(self):
        """Test creating client from configuration."""
        config = {
            "indieweb": {
                "news": {
                    "endpoint": "https://custom.endpoint/webmention",
                    "target": "https://custom.target/page",
                    "timeout": 45
                }
            }
        }

        client = IndieWebNewsClient.from_config(config)

        assert client.endpoint == "https://custom.endpoint/webmention"
        assert client.target == "https://custom.target/page"
        assert client.timeout == 45

    def test_from_config_with_defaults(self):
        """Test creating client from empty configuration uses defaults."""
        config = {}

        client = IndieWebNewsClient.from_config(config)

        assert client.endpoint == IndieWebNewsClient.DEFAULT_ENDPOINT
        assert client.target == IndieWebNewsClient.DEFAULT_TARGET
        assert client.timeout == IndieWebNewsClient.DEFAULT_TIMEOUT

    @patch("indieweb.webmention.requests.post")
    def test_send_webmention_success(self, mock_post):
        """Test successful webmention sending."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.headers = {"Location": "https://news.indieweb.org/status/123"}
        mock_post.return_value = mock_response

        client = IndieWebNewsClient()
        result = client.send_webmention("https://blog.example.com/my-post")

        assert result.success is True
        assert result.status_code == 200
        assert result.message == "Webmention accepted"
        assert result.location == "https://news.indieweb.org/status/123"

        # Verify request parameters
        call_args = mock_post.call_args
        assert call_args[0][0] == IndieWebNewsClient.DEFAULT_ENDPOINT
        assert call_args[1]["data"]["source"] == "https://blog.example.com/my-post"
        assert call_args[1]["data"]["target"] == IndieWebNewsClient.DEFAULT_TARGET
        assert call_args[1]["headers"]["Content-Type"] == "application/x-www-form-urlencoded"

    @patch("indieweb.webmention.requests.post")
    def test_send_webmention_accepted_201(self, mock_post):
        """Test webmention accepted with 201 status."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 201
        mock_response.headers = {}
        mock_post.return_value = mock_response

        client = IndieWebNewsClient()
        result = client.send_webmention("https://blog.example.com/my-post")

        assert result.success is True
        assert result.status_code == 201

    @patch("indieweb.webmention.requests.post")
    def test_send_webmention_accepted_202(self, mock_post):
        """Test webmention accepted with 202 status."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 202
        mock_response.headers = {}
        mock_post.return_value = mock_response

        client = IndieWebNewsClient()
        result = client.send_webmention("https://blog.example.com/my-post")

        assert result.success is True
        assert result.status_code == 202

    @patch("indieweb.webmention.requests.post")
    def test_send_webmention_no_link_found(self, mock_post):
        """Test webmention rejection when u-syndication link is missing."""
        mock_response = MagicMock()
        mock_response.ok = False
        mock_response.status_code = 400
        mock_response.json.return_value = {
            "error": "no_link_found",
            "error_description": "The source document does not contain a link to the target"
        }
        mock_post.return_value = mock_response

        client = IndieWebNewsClient()
        result = client.send_webmention("https://blog.example.com/my-post")

        assert result.success is False
        assert result.status_code == 400
        assert "does not contain a link" in result.message

    @patch("indieweb.webmention.requests.post")
    def test_send_webmention_source_not_found(self, mock_post):
        """Test webmention rejection when source URL returns 404."""
        mock_response = MagicMock()
        mock_response.ok = False
        mock_response.status_code = 400
        mock_response.json.return_value = {
            "error": "source_not_found",
            "error_description": "The source document could not be fetched"
        }
        mock_post.return_value = mock_response

        client = IndieWebNewsClient()
        result = client.send_webmention("https://blog.example.com/nonexistent")

        assert result.success is False
        assert result.status_code == 400
        assert "could not be fetched" in result.message

    @patch("indieweb.webmention.requests.post")
    def test_send_webmention_error_json_without_description(self, mock_post):
        """Test error parsing when error_description is missing."""
        mock_response = MagicMock()
        mock_response.ok = False
        mock_response.status_code = 400
        mock_response.json.return_value = {
            "error": "unknown_error"
        }
        mock_post.return_value = mock_response

        client = IndieWebNewsClient()
        result = client.send_webmention("https://blog.example.com/my-post")

        assert result.success is False
        assert "unknown_error" in result.message

    @patch("indieweb.webmention.requests.post")
    def test_send_webmention_error_text_response(self, mock_post):
        """Test error parsing when response is plain text."""
        mock_response = MagicMock()
        mock_response.ok = False
        mock_response.status_code = 500
        mock_response.json.side_effect = Exception("Not JSON")
        mock_response.text = "Internal Server Error"
        mock_response.reason = "Internal Server Error"
        mock_post.return_value = mock_response

        client = IndieWebNewsClient()
        result = client.send_webmention("https://blog.example.com/my-post")

        assert result.success is False
        assert result.status_code == 500
        assert "500" in result.message

    @patch("indieweb.webmention.requests.post")
    def test_send_webmention_timeout(self, mock_post):
        """Test webmention request timeout."""
        mock_post.side_effect = requests.exceptions.Timeout("Request timed out")

        client = IndieWebNewsClient()
        result = client.send_webmention("https://blog.example.com/my-post")

        assert result.success is False
        assert result.status_code == 0
        assert "timed out" in result.message

    @patch("indieweb.webmention.requests.post")
    def test_send_webmention_connection_error(self, mock_post):
        """Test webmention connection error."""
        mock_post.side_effect = requests.exceptions.ConnectionError("Connection refused")

        client = IndieWebNewsClient()
        result = client.send_webmention("https://blog.example.com/my-post")

        assert result.success is False
        assert result.status_code == 0
        assert "Request failed" in result.message

    @patch("indieweb.webmention.requests.post")
    def test_send_webmention_with_custom_target(self, mock_post):
        """Test webmention with custom target URL."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.headers = {}
        mock_post.return_value = mock_response

        client = IndieWebNewsClient(target="https://custom.target/page")
        result = client.send_webmention("https://blog.example.com/my-post")

        assert result.success is True
        call_data = mock_post.call_args[1]["data"]
        assert call_data["target"] == "https://custom.target/page"

    @patch("indieweb.webmention.requests.post")
    def test_send_webmention_timeout_value(self, mock_post):
        """Test that custom timeout is passed to requests."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.headers = {}
        mock_post.return_value = mock_response

        client = IndieWebNewsClient(timeout=60.0)
        client.send_webmention("https://blog.example.com/my-post")

        assert mock_post.call_args[1]["timeout"] == 60.0


class TestSendToIndieWebNews:
    """Test suite for send_to_indieweb_news convenience function."""

    @patch("indieweb.webmention.requests.post")
    def test_send_without_config(self, mock_post):
        """Test sending without configuration uses defaults."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.headers = {}
        mock_post.return_value = mock_response

        result = send_to_indieweb_news("https://blog.example.com/my-post")

        assert result.success is True
        call_args = mock_post.call_args
        assert call_args[0][0] == IndieWebNewsClient.DEFAULT_ENDPOINT

    @patch("indieweb.webmention.requests.post")
    def test_send_with_config(self, mock_post):
        """Test sending with custom configuration."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.headers = {}
        mock_post.return_value = mock_response

        config = {
            "indieweb": {
                "news": {
                    "endpoint": "https://custom.endpoint/webmention"
                }
            }
        }

        result = send_to_indieweb_news("https://blog.example.com/my-post", config)

        assert result.success is True
        call_args = mock_post.call_args
        assert call_args[0][0] == "https://custom.endpoint/webmention"


class TestHasIndiewebTag:
    """Test suite for has_indieweb_tag utility function."""

    def test_tag_present_by_slug(self):
        """Test detection when tag is present by slug."""
        tags = [
            {"name": "Technology", "slug": "technology"},
            {"name": "IndieWebNews", "slug": "indiewebnews"}
        ]

        assert has_indieweb_tag(tags) is True

    def test_tag_present_by_name(self):
        """Test detection when tag matches by name."""
        tags = [
            {"name": "Technology", "slug": "technology"},
            {"name": "indiewebnews", "slug": "different-slug"}
        ]

        assert has_indieweb_tag(tags) is True

    def test_tag_absent(self):
        """Test when IndieWeb tag is not present."""
        tags = [
            {"name": "Technology", "slug": "technology"},
            {"name": "Personal", "slug": "personal"}
        ]

        assert has_indieweb_tag(tags) is False

    def test_empty_tags(self):
        """Test with empty tags list."""
        assert has_indieweb_tag([]) is False

    def test_none_tags(self):
        """Test with None tags."""
        assert has_indieweb_tag(None) is False

    def test_case_insensitive_matching(self):
        """Test that tag matching is case-insensitive."""
        tags_upper = [{"name": "INDIEWEBNEWS", "slug": "INDIEWEBNEWS"}]
        tags_mixed = [{"name": "IndieWebNews", "slug": "IndieWebNews"}]
        tags_lower = [{"name": "indiewebnews", "slug": "indiewebnews"}]

        assert has_indieweb_tag(tags_upper) is True
        assert has_indieweb_tag(tags_mixed) is True
        assert has_indieweb_tag(tags_lower) is True

    def test_custom_tag_slug(self):
        """Test with custom tag slug."""
        tags = [
            {"name": "MyCustomTag", "slug": "mycustomtag"}
        ]

        assert has_indieweb_tag(tags, "mycustomtag") is True
        assert has_indieweb_tag(tags, "indiewebnews") is False

    def test_malformed_tag_dict(self):
        """Test handling of malformed tag dictionaries."""
        tags = [
            {"name": "Technology"},  # Missing slug
            {"slug": "personal"},  # Missing name
            {},  # Empty dict
            "not-a-dict"  # Not a dict at all
        ]

        assert has_indieweb_tag(tags) is False

    def test_tag_with_hash_prefix(self):
        """Test that tags with # prefix are handled."""
        tags = [
            {"name": "#indiewebnews", "slug": "hash-indiewebnews"}
        ]

        # The function checks slug, which doesn't have hash
        assert has_indieweb_tag(tags, "hash-indiewebnews") is True

    def test_partial_match_not_accepted(self):
        """Test that partial matches are not accepted."""
        tags = [
            {"name": "indiewebnews-extended", "slug": "indiewebnews-extended"}
        ]

        assert has_indieweb_tag(tags) is False

    def test_default_tag_slug(self):
        """Test that default tag slug is correct."""
        assert DEFAULT_INDIEWEB_TAG == "indiewebnews"


class TestGetIndiewebConfig:
    """Test suite for get_indieweb_config utility function."""

    def test_full_config(self):
        """Test extracting full IndieWeb configuration."""
        config = {
            "indieweb": {
                "enabled": True,
                "news": {
                    "endpoint": "https://custom.endpoint/webmention",
                    "target": "https://custom.target/page",
                    "tag": "customtag",
                    "timeout": 45
                }
            }
        }

        result = get_indieweb_config(config)

        assert result["enabled"] is True
        assert result["news"]["endpoint"] == "https://custom.endpoint/webmention"
        assert result["news"]["target"] == "https://custom.target/page"
        assert result["news"]["tag"] == "customtag"
        assert result["news"]["timeout"] == 45

    def test_empty_config(self):
        """Test extracting from empty configuration uses defaults."""
        result = get_indieweb_config({})

        assert result["enabled"] is False
        assert result["news"]["endpoint"] == "https://news.indieweb.org/en/webmention"
        assert result["news"]["target"] == "https://news.indieweb.org/en"
        assert result["news"]["tag"] == "indiewebnews"
        assert result["news"]["timeout"] == 30

    def test_partial_config(self):
        """Test extracting partial configuration fills in defaults."""
        config = {
            "indieweb": {
                "enabled": True,
                "news": {
                    "tag": "customtag"
                }
            }
        }

        result = get_indieweb_config(config)

        assert result["enabled"] is True
        assert result["news"]["endpoint"] == "https://news.indieweb.org/en/webmention"
        assert result["news"]["tag"] == "customtag"

    def test_missing_news_section(self):
        """Test configuration without news section."""
        config = {
            "indieweb": {
                "enabled": True
            }
        }

        result = get_indieweb_config(config)

        assert result["enabled"] is True
        assert result["news"]["endpoint"] == "https://news.indieweb.org/en/webmention"
        assert result["news"]["tag"] == "indiewebnews"


class TestPushoverIndieWebNotifications:
    """Test suite for Pushover IndieWeb notifications."""

    @patch("notifications.pushover.requests.post")
    def test_notify_indieweb_success(self, mock_post):
        """Test IndieWeb success notification."""
        from notifications.pushover import PushoverNotifier

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response

        notifier = PushoverNotifier(
            app_token="test_app_token",
            user_key="test_user_key"
        )

        result = notifier.notify_indieweb_success(
            post_title="My IndieWeb Post",
            post_url="https://blog.example.com/my-post"
        )

        assert result is True
        call_data = mock_post.call_args[1]["data"]
        assert "🌐 IndieWeb News" in call_data["title"]
        assert "My IndieWeb Post" in call_data["message"]
        assert call_data["url"] == "https://blog.example.com/my-post"
        assert call_data["priority"] == 0  # Normal priority

    @patch("notifications.pushover.requests.post")
    def test_notify_indieweb_failure(self, mock_post):
        """Test IndieWeb failure notification."""
        from notifications.pushover import PushoverNotifier

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response

        notifier = PushoverNotifier(
            app_token="test_app_token",
            user_key="test_user_key"
        )

        result = notifier.notify_indieweb_failure(
            post_title="My IndieWeb Post",
            post_url="https://blog.example.com/my-post",
            error="no_link_found: The source document does not contain a link to the target"
        )

        assert result is True
        call_data = mock_post.call_args[1]["data"]
        assert "❌ IndieWeb News Failed" in call_data["title"]
        assert "My IndieWeb Post" in call_data["message"]
        assert "no_link_found" in call_data["message"]
        assert call_data["priority"] == 1  # High priority for errors
