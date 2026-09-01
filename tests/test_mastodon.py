"""
Integration Tests for Mastodon Client Module.

This test suite validates the Mastodon authentication functionality
by testing login with provided credentials from Docker secrets.

Test Coverage:
    - Login with credentials from secrets
    - Posting with and without media attachments
    - Media download and upload functionality

Testing Strategy:
    Tests use mocked credentials from Docker secrets to verify
    authentication initialization works correctly.

Running Tests:
    $ PYTHONPATH=src python -m unittest tests.test_mastodon -v
"""
import unittest
from unittest.mock import patch, MagicMock, call
import tempfile
import os
import time

from mastodon import MastodonRatelimitError
from requests.structures import CaseInsensitiveDict

from social.mastodon_client import (
    MastodonClient,
    RATELIMIT_RESET_FALLBACK_SECONDS,
)


class TestMastodonClient(unittest.TestCase):
    """Test suite for MastodonClient class."""
    
    @patch("config.read_secret_file")
    @patch("social.mastodon_client.Mastodon")
    def test_login_with_provided_secrets(self, mock_mastodon, mock_read_secret):
        """Test login with credentials loaded from secrets."""
        # Mock secret file reading to simulate Docker secrets
        mock_read_secret.return_value = "test_access_token"
        
        config = {
            "mastodon": {
                "accounts": [
                    {
                        "name": "test",
                        "instance_url": "https://mastodon.social",
                        "access_token_file": "/run/secrets/mastodon_access_token"
                    }
                ]
            }
        }
        
        clients = MastodonClient.from_config(config)
        
        # Verify client is properly initialized with secrets
        self.assertEqual(len(clients), 1)
        client = clients[0]
        self.assertTrue(client.enabled)
        self.assertEqual(client.instance_url, "https://mastodon.social")
        self.assertEqual(client.access_token, "test_access_token")
        self.assertIsNotNone(client.api)
    
    @patch("social.mastodon_client.Mastodon")
    def test_post_without_media(self, mock_mastodon):
        """Test posting status without media attachments."""
        # Setup mock API
        mock_api = MagicMock()
        mock_mastodon.return_value = mock_api
        mock_api.status_post.return_value = {
            "id": "123",
            "url": "https://mastodon.social/@user/123",
            "content": "Test post"
        }
        
        # Create client
        client = MastodonClient(
            instance_url="https://mastodon.social",
            access_token="test_token"
        )
        
        # Post without media
        result = client.post("Test post")
        
        # Verify status_post was called without media_ids (an idempotency_key
        # is also passed so retries don't create duplicate posts).
        mock_api.status_post.assert_called_once()
        status_args = mock_api.status_post.call_args.kwargs
        self.assertEqual(status_args["status"], "Test post")
        self.assertEqual(status_args["visibility"], "public")
        self.assertFalse(status_args["sensitive"])
        self.assertIsNone(status_args["spoiler_text"])
        self.assertIsNone(status_args["media_ids"])
        self.assertTrue(status_args["idempotency_key"])
        
        # Verify result
        self.assertIsNotNone(result)
        self.assertEqual(result["url"], "https://mastodon.social/@user/123")
    
    @patch("social.base_client.os.path.exists")
    @patch("social.base_client.os.makedirs")
    @patch("builtins.open", create=True)
    @patch("social.base_client.requests.get")
    @patch("social.mastodon_client.Mastodon")
    def test_post_with_single_image(self, mock_mastodon, mock_requests_get, mock_open, mock_makedirs, mock_exists):
        """Test posting status with a single image attachment."""
        # Mock that file doesn't exist (not cached)
        mock_exists.return_value = False
        
        # Setup mock API
        mock_api = MagicMock()
        mock_mastodon.return_value = mock_api
        mock_api.media_post.return_value = {"id": "media123"}
        mock_api.status_post.return_value = {
            "id": "456",
            "url": "https://mastodon.social/@user/456",
            "media_attachments": [{"id": "media123"}]
        }
        
        # Mock image download
        mock_response = MagicMock()
        mock_response.content = b"fake_image_data"
        mock_response.raise_for_status = MagicMock()
        mock_requests_get.return_value = mock_response
        
        # Create client
        client = MastodonClient(
            instance_url="https://mastodon.social",
            access_token="test_token"
        )
        
        # Post with single image
        result = client.post(
            "Check out this photo!",
            media_urls=["https://example.com/image.jpg"],
            media_descriptions=["A beautiful sunset"]
        )
        
        # Verify image was downloaded
        mock_requests_get.assert_called_once_with(
            "https://example.com/image.jpg",
            timeout=30
        )
        
        # Verify media was uploaded with description
        self.assertEqual(mock_api.media_post.call_count, 1)
        upload_args = mock_api.media_post.call_args
        self.assertEqual(upload_args[1]["description"], "A beautiful sunset")
        
        # Verify status was posted with media_ids
        mock_api.status_post.assert_called_once()
        status_args = mock_api.status_post.call_args[1]
        self.assertEqual(status_args["status"], "Check out this photo!")
        self.assertEqual(status_args["media_ids"], ["media123"])
        
        # Verify result
        self.assertIsNotNone(result)
        self.assertEqual(result["url"], "https://mastodon.social/@user/456")
    
    @patch("social.base_client.os.path.exists")
    @patch("social.base_client.os.makedirs")
    @patch("builtins.open", create=True)
    @patch("social.base_client.requests.get")
    @patch("social.mastodon_client.Mastodon")
    def test_post_with_multiple_images(self, mock_mastodon, mock_requests_get, mock_open, mock_makedirs, mock_exists):
        """Test posting status with multiple image attachments."""
        # Mock that files don't exist (not cached)
        mock_exists.return_value = False
        
        # Setup mock API
        mock_api = MagicMock()
        mock_mastodon.return_value = mock_api
        mock_api.media_post.side_effect = [
            {"id": "media1"},
            {"id": "media2"},
            {"id": "media3"}
        ]
        mock_api.status_post.return_value = {
            "id": "789",
            "url": "https://mastodon.social/@user/789",
            "media_attachments": [
                {"id": "media1"},
                {"id": "media2"},
                {"id": "media3"}
            ]
        }
        
        # Mock image downloads
        mock_response = MagicMock()
        mock_response.content = b"fake_image_data"
        mock_response.raise_for_status = MagicMock()
        mock_requests_get.return_value = mock_response
        
        # Create client
        client = MastodonClient(
            instance_url="https://mastodon.social",
            access_token="test_token"
        )
        
        # Post with multiple images
        result = client.post(
            "Gallery post!",
            media_urls=[
                "https://example.com/image1.jpg",
                "https://example.com/image2.jpg",
                "https://example.com/image3.jpg"
            ],
            media_descriptions=["First image", "Second image", "Third image"]
        )
        
        # Verify all images were downloaded
        self.assertEqual(mock_requests_get.call_count, 3)
        
        # Verify all media were uploaded
        self.assertEqual(mock_api.media_post.call_count, 3)
        
        # Verify status was posted with all media_ids
        mock_api.status_post.assert_called_once()
        status_args = mock_api.status_post.call_args[1]
        self.assertEqual(status_args["media_ids"], ["media1", "media2", "media3"])
        
        # Verify result
        self.assertIsNotNone(result)
    
    @patch("social.base_client.os.path.exists")
    @patch("social.base_client.requests.get")
    @patch("social.mastodon_client.Mastodon")
    def test_post_with_failed_image_download(self, mock_mastodon, mock_requests_get, mock_exists):
        """Test posting when image download fails - should still post without media."""
        # Mock that file doesn't exist
        mock_exists.return_value = False
        
        # Setup mock API
        mock_api = MagicMock()
        mock_mastodon.return_value = mock_api
        mock_api.status_post.return_value = {
            "id": "999",
            "url": "https://mastodon.social/@user/999"
        }
        
        # Mock failed image download
        mock_requests_get.side_effect = Exception("Network error")
        
        # Create client
        client = MastodonClient(
            instance_url="https://mastodon.social",
            access_token="test_token"
        )
        
        # Post with image URL that will fail to download
        result = client.post(
            "Text post",
            media_urls=["https://example.com/broken.jpg"]
        )
        
        # Verify download was attempted
        mock_requests_get.assert_called_once()
        
        # Verify media_post was NOT called (no successful download)
        mock_api.media_post.assert_not_called()
        
        # Verify status was still posted without media
        mock_api.status_post.assert_called_once()
        status_args = mock_api.status_post.call_args[1]
        self.assertEqual(status_args["media_ids"], None)
        
        # Verify result
        self.assertIsNotNone(result)
    
    @patch("social.mastodon_client.Mastodon")
    def test_post_disabled_client(self, mock_mastodon):
        """Test posting with disabled client returns None."""
        # Create disabled client (no access token)
        client = MastodonClient(
            instance_url="https://mastodon.social",
            access_token=None
        )
        
        # Attempt to post
        result = client.post("Test post")
        
        # Verify no API calls were made
        mock_mastodon.return_value.status_post.assert_not_called()

        # Verify result is None
        self.assertIsNone(result)


class TestRatelimitResetBackfill(unittest.TestCase):
    """Test suite for the missing X-RateLimit-Reset workaround.

    Pixelfed sends X-RateLimit-Limit/Remaining but no X-RateLimit-Reset, which
    makes Mastodon.py raise MastodonRatelimitError on every request.
    """

    @staticmethod
    def _response(headers):
        """Build a stub response carrying case-insensitive headers."""
        response = MagicMock()
        response.headers = CaseInsensitiveDict(headers)
        return response

    def test_reset_injected_when_missing(self):
        """A missing reset header is filled in with a future epoch time."""
        response = self._response({
            "X-RateLimit-Limit": "512",
            "X-RateLimit-Remaining": "511",
        })

        MastodonClient._backfill_ratelimit_reset(response)

        reset = int(response.headers["X-RateLimit-Reset"])
        self.assertGreater(reset, int(time.time()))

    def test_existing_reset_is_preserved(self):
        """A well-behaved instance's reset header is left untouched."""
        response = self._response({
            "X-RateLimit-Remaining": "42",
            "X-RateLimit-Reset": "2026-09-01T03:13:08.000Z",
        })

        MastodonClient._backfill_ratelimit_reset(response)

        self.assertEqual(
            response.headers["X-RateLimit-Reset"], "2026-09-01T03:13:08.000Z"
        )

    def test_no_injection_without_remaining_header(self):
        """Without X-RateLimit-Remaining, Mastodon.py never reads reset."""
        response = self._response({"Content-Type": "application/json"})

        MastodonClient._backfill_ratelimit_reset(response)

        self.assertNotIn("X-RateLimit-Reset", response.headers)

    def test_retry_after_seconds_used_for_reset(self):
        """Retry-After in seconds is preferred over the fallback window."""
        response = self._response({
            "X-RateLimit-Remaining": "0",
            "Retry-After": "60",
        })

        before = int(time.time())
        MastodonClient._backfill_ratelimit_reset(response)

        reset = int(response.headers["X-RateLimit-Reset"])
        # Allow a second of slack for clock movement during the call.
        self.assertGreaterEqual(reset, before + 60)
        self.assertLessEqual(reset, before + 61)

    def test_malformed_retry_after_falls_back(self):
        """An HTTP-date Retry-After falls back instead of raising."""
        response = self._response({
            "X-RateLimit-Remaining": "0",
            "Retry-After": "Wed, 01 Sep 2026 03:13:08 GMT",
        })

        before = int(time.time())
        MastodonClient._backfill_ratelimit_reset(response)

        reset = int(response.headers["X-RateLimit-Reset"])
        self.assertGreaterEqual(reset, before + RATELIMIT_RESET_FALLBACK_SECONDS)

    @patch("social.mastodon_client.Mastodon")
    def test_session_hook_registered_on_api_client(self, mock_mastodon):
        """The client hands Mastodon.py a session carrying the hook."""
        MastodonClient(
            instance_url="https://pixelfed.social",
            access_token="test_access_token",
        )

        session = mock_mastodon.call_args[1]["session"]
        self.assertIn(
            MastodonClient._backfill_ratelimit_reset, session.hooks["response"]
        )

    def test_ratelimit_error_is_not_retried(self):
        """Rate limit errors must not be retried: posting is not idempotent.

        The exception surfaces after the server has already processed the
        request, so a retry risks duplicating a post.
        """
        self.assertFalse(
            MastodonClient._is_transient_error(MastodonRatelimitError("boom"))
        )
