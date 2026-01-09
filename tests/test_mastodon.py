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

from mastodon_client.mastodon_client import MastodonClient


class TestMastodonClient(unittest.TestCase):
    """Test suite for MastodonClient class."""
    
    @patch("config.read_secret_file")
    @patch("mastodon_client.mastodon_client.Mastodon")
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
    
    @patch("mastodon_client.mastodon_client.Mastodon")
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
        
        # Verify status_post was called without media_ids
        mock_api.status_post.assert_called_once_with(
            status="Test post",
            visibility="public",
            sensitive=False,
            spoiler_text=None,
            media_ids=None
        )
        
        # Verify result
        self.assertIsNotNone(result)
        self.assertEqual(result["url"], "https://mastodon.social/@user/123")
    
    @patch("mastodon_client.mastodon_client.requests.get")
    @patch("mastodon_client.mastodon_client.Mastodon")
    def test_post_with_single_image(self, mock_mastodon, mock_requests_get):
        """Test posting status with a single image attachment."""
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
    
    @patch("mastodon_client.mastodon_client.requests.get")
    @patch("mastodon_client.mastodon_client.Mastodon")
    def test_post_with_multiple_images(self, mock_mastodon, mock_requests_get):
        """Test posting status with multiple image attachments."""
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
    
    @patch("mastodon_client.mastodon_client.requests.get")
    @patch("mastodon_client.mastodon_client.Mastodon")
    def test_post_with_failed_image_download(self, mock_mastodon, mock_requests_get):
        """Test posting when image download fails - should still post without media."""
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
    
    @patch("mastodon_client.mastodon_client.Mastodon")
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
