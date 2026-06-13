"""Tests for transient-error retries in Mastodon and Bluesky publish paths.

When a syndication target returns a transient error (5xx, connection blip),
the client should retry with exponential backoff a few times before giving
up. Permanent errors should fail immediately without burning retry attempts,
and retries must not produce duplicate posts.
"""
import unittest
from unittest.mock import patch, MagicMock

from mastodon import (
    MastodonError,
    MastodonNetworkError,
    MastodonRatelimitError,
    MastodonServerError,
)
from atproto.exceptions import InvokeTimeoutError, NetworkError, RequestException

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


class _Resp:
    """Minimal stand-in for an atproto Response carrying a status code."""

    def __init__(self, status_code):
        self.status_code = status_code


def _request_exception(status_code):
    return RequestException(response=_Resp(status_code))


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
    def test_rate_limit_is_not_retried(self, mock_mastodon, mock_sleep):
        client, mock_api = _make_mastodon_client(mock_mastodon)

        # Mastodon.py honors rate limits internally (ratelimit_method="wait"),
        # so a 429 should never be retried here with blind backoff.
        mock_api.status_post.side_effect = MastodonRatelimitError("Rate limited")

        result = client.post("Hello")

        self.assertIsNone(result)
        self.assertEqual(mock_api.status_post.call_count, 1)
        mock_sleep.assert_not_called()

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

    @patch("social.base_client.time.sleep")
    @patch("social.mastodon_client.Mastodon")
    def test_idempotency_key_is_stable_across_retries(self, mock_mastodon, mock_sleep):
        client, mock_api = _make_mastodon_client(mock_mastodon)

        mock_api.status_post.side_effect = [
            MastodonServerError("Mastodon API returned error", 503, "Service Unavailable", None),
            {"id": "1", "url": "https://mastodon.social/@u/1"},
        ]

        client.post("Hello")

        self.assertEqual(mock_api.status_post.call_count, 2)
        keys = {call.kwargs["idempotency_key"] for call in mock_api.status_post.call_args_list}
        # All attempts must share one non-empty key so the server dedupes a
        # retry that lands after the original write already committed.
        self.assertEqual(len(keys), 1)
        self.assertTrue(next(iter(keys)))

    @patch("social.base_client.time.sleep")
    @patch("social.mastodon_client.Mastodon")
    def test_media_upload_retries_on_transient(self, mock_mastodon, mock_sleep):
        client, mock_api = _make_mastodon_client(mock_mastodon)

        # First media_post attempt is a transient 503, second succeeds.
        mock_api.media_post.side_effect = [
            MastodonServerError("Mastodon API returned error", 503, "Service Unavailable", None),
            {"id": "media-1"},
        ]
        mock_api.status_post.return_value = {"id": "1", "url": "https://mastodon.social/@u/1"}

        with patch.object(client, "_download_image", return_value="/tmp/fake.jpg"):
            result = client.post("Hello", media_urls=["https://example.com/a.jpg"])

        self.assertIsNotNone(result)
        self.assertEqual(mock_api.media_post.call_count, 2)
        # The successfully uploaded media id must reach status_post.
        self.assertEqual(mock_api.status_post.call_args.kwargs["media_ids"], ["media-1"])


class TestBlueskyTransientDetection(unittest.TestCase):
    """Bluesky transient-error classifier (structured atproto exceptions)."""

    def test_500_status_detected(self):
        self.assertTrue(BlueskyClient._is_transient_error(_request_exception(500)))

    def test_502_status_detected(self):
        self.assertTrue(BlueskyClient._is_transient_error(_request_exception(502)))

    def test_503_status_detected(self):
        self.assertTrue(BlueskyClient._is_transient_error(_request_exception(503)))

    def test_429_status_detected(self):
        self.assertTrue(BlueskyClient._is_transient_error(_request_exception(429)))

    def test_network_error_detected(self):
        self.assertTrue(BlueskyClient._is_transient_error(NetworkError()))

    def test_read_timeout_not_retried(self):
        # Read timeouts are ambiguous (the write may have committed), so they
        # must not be retried — retrying is the main duplicate-post hazard.
        self.assertFalse(BlueskyClient._is_transient_error(InvokeTimeoutError()))

    def test_400_status_not_detected(self):
        self.assertFalse(BlueskyClient._is_transient_error(_request_exception(400)))

    def test_401_status_not_detected(self):
        self.assertFalse(BlueskyClient._is_transient_error(_request_exception(401)))

    def test_unrelated_exception_not_detected(self):
        self.assertFalse(BlueskyClient._is_transient_error(ValueError("Invalid post content")))


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
