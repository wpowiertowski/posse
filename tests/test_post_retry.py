"""Tests for transient-error retries in Mastodon and Bluesky publish paths.

When a syndication target returns a transient error (5xx, network blip,
rate limit), the client should retry with exponential backoff a few
times before giving up. Permanent errors should fail immediately
without burning retry attempts.
"""
import unittest
from unittest.mock import patch, MagicMock

from mastodon import (
    MastodonError,
    MastodonNetworkError,
    MastodonRatelimitError,
    MastodonServerError,
)

from social.mastodon_client import MastodonClient
from social.bluesky_client import BlueskyClient


def _make_mastodon_client(mock_mastodon):
    mock_api = MagicMock()
    mock_mastodon.return_value = mock_api
    client = MastodonClient(
        instance_url="https://mastodon.social",
        access_token="test_token",
        account_name="test",
    )
    return client, mock_api


class TestMastodonRetry(unittest.TestCase):
    """Mastodon transient-error retry behavior."""

    @patch("social.base_client.time.sleep")
    @patch("social.mastodon_client.Mastodon")
    def test_retries_on_503_then_succeeds(self, mock_mastodon, mock_sleep):
        client, mock_api = _make_mastodon_client(mock_mastodon)

        # Two 503s, then success on the third attempt
        mock_api.status_post.side_effect = [
            MastodonServerError("Mastodon API returned error", 503, "Service Unavailable", None),
            MastodonServerError("Mastodon API returned error", 503, "Service Unavailable", None),
            {"id": "1", "url": "https://mastodon.social/@u/1"},
        ]

        result = client.post("Hello")

        self.assertIsNotNone(result)
        self.assertEqual(result["url"], "https://mastodon.social/@u/1")
        self.assertEqual(mock_api.status_post.call_count, 3)
        # Should have slept twice (before retry 2 and retry 3)
        self.assertEqual(mock_sleep.call_count, 2)

    @patch("social.base_client.time.sleep")
    @patch("social.mastodon_client.Mastodon")
    def test_retries_on_network_error_then_succeeds(self, mock_mastodon, mock_sleep):
        client, mock_api = _make_mastodon_client(mock_mastodon)

        mock_api.status_post.side_effect = [
            MastodonNetworkError("Connection reset"),
            {"id": "2", "url": "https://mastodon.social/@u/2"},
        ]

        result = client.post("Hello")

        self.assertIsNotNone(result)
        self.assertEqual(mock_api.status_post.call_count, 2)
        self.assertEqual(mock_sleep.call_count, 1)

    @patch("social.base_client.time.sleep")
    @patch("social.mastodon_client.Mastodon")
    def test_retries_on_rate_limit_then_succeeds(self, mock_mastodon, mock_sleep):
        client, mock_api = _make_mastodon_client(mock_mastodon)

        mock_api.status_post.side_effect = [
            MastodonRatelimitError("Rate limited"),
            {"id": "3", "url": "https://mastodon.social/@u/3"},
        ]

        result = client.post("Hello")

        self.assertIsNotNone(result)
        self.assertEqual(mock_api.status_post.call_count, 2)

    @patch("social.base_client.time.sleep")
    @patch("social.mastodon_client.Mastodon")
    def test_exhausts_retries_then_returns_none(self, mock_mastodon, mock_sleep):
        client, mock_api = _make_mastodon_client(mock_mastodon)

        # Always returns 503 — should exhaust retries and return None
        mock_api.status_post.side_effect = MastodonServerError(
            "Mastodon API returned error", 503, "Service Unavailable", None
        )

        result = client.post("Hello")

        self.assertIsNone(result)
        # Default is MAX_POST_RETRIES=2 → 3 total attempts
        self.assertEqual(mock_api.status_post.call_count, 3)
        self.assertEqual(mock_sleep.call_count, 2)

    @patch("social.base_client.time.sleep")
    @patch("social.mastodon_client.Mastodon")
    def test_non_transient_error_does_not_retry(self, mock_mastodon, mock_sleep):
        client, mock_api = _make_mastodon_client(mock_mastodon)

        # Generic MastodonError (4xx-like) is not transient
        mock_api.status_post.side_effect = MastodonError(
            "Mastodon API returned error", 422, "Unprocessable Entity", None
        )

        result = client.post("Hello")

        self.assertIsNone(result)
        # Only one attempt — no retries for permanent errors
        self.assertEqual(mock_api.status_post.call_count, 1)
        mock_sleep.assert_not_called()


class TestBlueskyTransientDetection(unittest.TestCase):
    """Bluesky transient-error classifier (string-based)."""

    def test_503_message_detected(self):
        self.assertTrue(
            BlueskyClient._is_transient_error(Exception("Server returned 503 Service Unavailable"))
        )

    def test_502_message_detected(self):
        self.assertTrue(BlueskyClient._is_transient_error(Exception("HTTP 502 Bad Gateway")))

    def test_429_message_detected(self):
        self.assertTrue(BlueskyClient._is_transient_error(Exception("HTTP 429 Too Many Requests")))

    def test_timeout_keyword_detected(self):
        self.assertTrue(BlueskyClient._is_transient_error(Exception("Request timed out")))

    def test_connection_keyword_detected(self):
        self.assertTrue(BlueskyClient._is_transient_error(Exception("Connection reset by peer")))

    def test_400_not_detected(self):
        self.assertFalse(BlueskyClient._is_transient_error(Exception("HTTP 400 Bad Request")))

    def test_401_not_detected(self):
        self.assertFalse(BlueskyClient._is_transient_error(Exception("HTTP 401 Unauthorized")))

    def test_unrelated_message_not_detected(self):
        self.assertFalse(BlueskyClient._is_transient_error(Exception("Invalid post content")))


class TestRetryHelper(unittest.TestCase):
    """Sanity checks for the shared _retry_with_backoff helper."""

    @patch("social.base_client.time.sleep")
    def test_returns_immediately_on_success(self, mock_sleep):
        calls = []

        def fn():
            calls.append(1)
            return "ok"

        from social.base_client import SocialMediaClient

        result = SocialMediaClient._retry_with_backoff(
            fn, is_transient=lambda e: True, operation_name="test"
        )
        self.assertEqual(result, "ok")
        self.assertEqual(len(calls), 1)
        mock_sleep.assert_not_called()

    @patch("social.base_client.time.sleep")
    def test_non_transient_propagates_without_sleep(self, mock_sleep):
        from social.base_client import SocialMediaClient

        def fn():
            raise ValueError("permanent")

        with self.assertRaises(ValueError):
            SocialMediaClient._retry_with_backoff(
                fn, is_transient=lambda e: False, operation_name="test"
            )
        mock_sleep.assert_not_called()


if __name__ == "__main__":
    unittest.main()
