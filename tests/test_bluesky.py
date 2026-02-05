"""
Integration Tests for Bluesky Client Module.

This test suite validates the Bluesky authentication functionality
by testing login with provided credentials from Docker secrets.

Test Coverage:
    - Login with credentials from secrets
    - Posting to Bluesky
    - Credential verification
    - Image compression for blob size limits

Testing Strategy:
    Tests use mocked credentials from Docker secrets to verify
    authentication initialization works correctly.

Running Tests:
    $ PYTHONPATH=src python -m unittest tests.test_bluesky -v
"""
import io
import unittest
from unittest.mock import patch, MagicMock, call

from PIL import Image

from atproto import models
from social.bluesky_client import BlueskyClient


class TestBlueskyClient(unittest.TestCase):
    """Test suite for BlueskyClient class."""
    
    @patch("config.read_secret_file")
    @patch("social.bluesky_client.Client")
    def test_login_with_provided_secrets(self, mock_client_class, mock_read_secret):
        """Test login with credentials loaded from secrets."""
        # Mock secret file reading to simulate Docker secrets
        mock_read_secret.return_value = "test_app_password"
        
        # Mock ATProto Client
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        
        config = {
            "bluesky": {
                "accounts": [
                    {
                        "name": "test",
                        "instance_url": "https://bsky.social",
                        "handle": "user.bsky.social",
                        "app_password_file": "/run/secrets/bluesky_app_password"
                    }
                ]
            }
        }
        
        clients = BlueskyClient.from_config(config)
        
        # Verify client is properly initialized with secrets
        self.assertEqual(len(clients), 1)
        client = clients[0]
        self.assertTrue(client.enabled)
        self.assertEqual(client.instance_url, "https://bsky.social")
        self.assertEqual(client.handle, "user.bsky.social")
        self.assertEqual(client.app_password, "test_app_password")
        self.assertIsNotNone(client.api)
        
        # Verify login was called with correct credentials
        mock_client.login.assert_called_once_with(
            login="user.bsky.social",
            password="test_app_password"
        )
    
    @patch("config.read_secret_file")
    @patch("social.bluesky_client.Client")
    def test_login_with_access_token_file_fallback(self, mock_client_class, mock_read_secret):
        """Test that access_token_file works as fallback for app_password_file."""
        # Mock secret file reading
        mock_read_secret.return_value = "test_app_password"
        
        # Mock ATProto Client
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        
        config = {
            "bluesky": {
                "accounts": [
                    {
                        "name": "test",
                        "instance_url": "https://bsky.social",
                        "handle": "user.bsky.social",
                        "access_token_file": "/run/secrets/bluesky_access_token"
                    }
                ]
            }
        }
        
        clients = BlueskyClient.from_config(config)
        
        # Verify client is properly initialized
        self.assertEqual(len(clients), 1)
        client = clients[0]
        self.assertTrue(client.enabled)
        self.assertEqual(client.app_password, "test_app_password")
    
    @patch("social.bluesky_client.Client")
    def test_post_success(self, mock_client_class):
        """Test posting status to Bluesky successfully."""
        # Setup mock API
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        
        # Mock send_post result
        mock_result = MagicMock()
        mock_result.uri = "at://did:plc:abc123/app.bsky.feed.post/xyz789"
        mock_result.cid = "bafyreiabc123"
        mock_client.send_post.return_value = mock_result
        
        # Create client
        client = BlueskyClient(
            instance_url="https://bsky.social",
            handle="user.bsky.social",
            app_password="test_password"
        )
        
        # Post content
        result = client.post("Hello Bluesky!")
        
        # Verify send_post was called
        mock_client.send_post.assert_called_once()
        
        # Verify result
        self.assertIsNotNone(result)
        self.assertEqual(result["uri"], "at://did:plc:abc123/app.bsky.feed.post/xyz789")
        self.assertEqual(result["cid"], "bafyreiabc123")
    
    @patch("social.bluesky_client.Client")
    def test_post_disabled_client(self, mock_client_class):
        """Test posting with disabled client returns None."""
        # Create disabled client (no handle)
        client = BlueskyClient(
            instance_url="https://bsky.social",
            handle=None,
            app_password="test_password"
        )
        
        # Attempt to post
        result = client.post("Test post")
        
        # Verify result is None
        self.assertIsNone(result)
    
    @patch("social.bluesky_client.Client")
    def test_post_failure(self, mock_client_class):
        """Test posting when API call fails."""
        # Setup mock API
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        
        # Mock send_post to raise exception
        mock_client.send_post.side_effect = Exception("API Error")
        
        # Create client
        client = BlueskyClient(
            instance_url="https://bsky.social",
            handle="user.bsky.social",
            app_password="test_password"
        )
        
        # Attempt to post
        result = client.post("Test post")
        
        # Verify result is None
        self.assertIsNone(result)
    
    @patch("social.bluesky_client.Client")
    def test_verify_credentials_success(self, mock_client_class):
        """Test verifying credentials successfully."""
        # Setup mock API
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        
        # Mock session and profile
        mock_client.me = MagicMock()
        mock_client.me.did = "did:plc:abc123"
        
        mock_profile = MagicMock()
        mock_profile.handle = "user.bsky.social"
        mock_profile.did = "did:plc:abc123"
        mock_profile.display_name = "Test User"
        mock_client.get_profile.return_value = mock_profile
        
        # Create client
        client = BlueskyClient(
            instance_url="https://bsky.social",
            handle="user.bsky.social",
            app_password="test_password"
        )
        
        # Verify credentials
        result = client.verify_credentials()
        
        # Verify get_profile was called
        mock_client.get_profile.assert_called_once_with(actor="did:plc:abc123")
        
        # Verify result
        self.assertIsNotNone(result)
        self.assertEqual(result["handle"], "user.bsky.social")
        self.assertEqual(result["did"], "did:plc:abc123")
        self.assertEqual(result["display_name"], "Test User")
    
    @patch("social.bluesky_client.Client")
    def test_verify_credentials_no_session(self, mock_client_class):
        """Test verifying credentials when no session exists."""
        # Setup mock API
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        
        # Mock missing session
        mock_client.me = None
        
        # Create client
        client = BlueskyClient(
            instance_url="https://bsky.social",
            handle="user.bsky.social",
            app_password="test_password"
        )
        
        # Verify credentials
        result = client.verify_credentials()
        
        # Verify result is None
        self.assertIsNone(result)
    
    @patch("social.bluesky_client.Client")
    def test_verify_credentials_disabled_client(self, mock_client_class):
        """Test verifying credentials with disabled client."""
        # Create disabled client
        client = BlueskyClient(
            instance_url="https://bsky.social",
            handle=None,
            app_password="test_password"
        )
        
        # Verify credentials
        result = client.verify_credentials()
        
        # Verify result is None
        self.assertIsNone(result)
    
    @patch("social.bluesky_client.Client")
    def test_verify_credentials_failure(self, mock_client_class):
        """Test verifying credentials when API call fails."""
        # Setup mock API
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        
        # Mock session
        mock_client.me = MagicMock()
        mock_client.me.did = "did:plc:abc123"
        
        # Mock get_profile to raise exception
        mock_client.get_profile.side_effect = Exception("API Error")
        
        # Create client
        client = BlueskyClient(
            instance_url="https://bsky.social",
            handle="user.bsky.social",
            app_password="test_password"
        )
        
        # Verify credentials
        result = client.verify_credentials()
        
        # Verify result is None
        self.assertIsNone(result)
    
    @patch("config.read_secret_file")
    @patch("social.bluesky_client.Client")
    def test_multiple_accounts_from_config(self, mock_client_class, mock_read_secret):
        """Test creating multiple Bluesky clients from config."""
        # Mock secret file reading with different values
        mock_read_secret.side_effect = ["password1", "password2"]
        
        # Mock ATProto Client
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        
        config = {
            "bluesky": {
                "accounts": [
                    {
                        "name": "personal",
                        "instance_url": "https://bsky.social",
                        "handle": "user1.bsky.social",
                        "app_password_file": "/run/secrets/bluesky_personal"
                    },
                    {
                        "name": "work",
                        "instance_url": "https://bsky.social",
                        "handle": "user2.bsky.social",
                        "app_password_file": "/run/secrets/bluesky_work"
                    }
                ]
            }
        }
        
        clients = BlueskyClient.from_config(config)
        
        # Verify two clients were created
        self.assertEqual(len(clients), 2)
        
        # Verify first client
        self.assertEqual(clients[0].account_name, "personal")
        self.assertEqual(clients[0].handle, "user1.bsky.social")
        self.assertEqual(clients[0].app_password, "password1")
        
        # Verify second client
        self.assertEqual(clients[1].account_name, "work")
        self.assertEqual(clients[1].handle, "user2.bsky.social")
        self.assertEqual(clients[1].app_password, "password2")
    
    @patch("config.read_secret_file")
    @patch("social.bluesky_client.Client")
    def test_disabled_account_missing_handle(self, mock_client_class, mock_read_secret):
        """Test that account is disabled when handle is missing."""
        mock_read_secret.return_value = "password"
        
        config = {
            "bluesky": {
                "accounts": [
                    {
                        "name": "test",
                        "instance_url": "https://bsky.social",
                        "app_password_file": "/run/secrets/bluesky"
                    }
                ]
            }
        }
        
        clients = BlueskyClient.from_config(config)
        
        # Verify client is disabled
        self.assertEqual(len(clients), 1)
        self.assertFalse(clients[0].enabled)
    
    @patch("config.read_secret_file")
    @patch("social.bluesky_client.Client")
    def test_disabled_account_missing_password(self, mock_client_class, mock_read_secret):
        """Test that account is disabled when password is missing."""
        mock_read_secret.return_value = None
        
        config = {
            "bluesky": {
                "accounts": [
                    {
                        "name": "test",
                        "instance_url": "https://bsky.social",
                        "handle": "user.bsky.social",
                        "app_password_file": "/run/secrets/bluesky"
                    }
                ]
            }
        }
        
        clients = BlueskyClient.from_config(config)
        
        # Verify client is disabled
        self.assertEqual(len(clients), 1)
        self.assertFalse(clients[0].enabled)
    
    @patch("social.bluesky_client.models")
    @patch("social.base_client.os.path.exists")
    @patch("social.base_client.os.makedirs")
    @patch("builtins.open", create=True)
    @patch("social.base_client.requests.get")
    @patch("social.bluesky_client.Client")
    def test_post_with_single_image(self, mock_client_class, mock_requests_get, mock_open, mock_makedirs, mock_exists, mock_models):
        """Test posting status with a single image attachment."""
        # Mock that file doesn't exist (not cached)
        mock_exists.return_value = False
        
        # Setup mock API
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        
        # Mock image download
        mock_response = MagicMock()
        mock_response.content = b"fake_image_data"
        mock_response.raise_for_status = MagicMock()
        mock_requests_get.return_value = mock_response
        
        # Mock upload_blob result
        mock_blob_result = MagicMock()
        mock_blob_result.blob = MagicMock()
        mock_client.upload_blob.return_value = mock_blob_result
        
        # Mock models.AppBskyEmbedImages
        mock_image = MagicMock()
        mock_image.alt = "A beautiful sunset"
        mock_image.image = mock_blob_result.blob
        mock_models.AppBskyEmbedImages.Image.return_value = mock_image
        
        mock_embed = MagicMock(spec=models.AppBskyEmbedImages.Main)
        mock_embed.images = [mock_image]
        mock_models.AppBskyEmbedImages.Main.return_value = mock_embed
        
        # Mock send_post result
        mock_result = MagicMock()
        mock_result.uri = "at://did:plc:abc123/app.bsky.feed.post/xyz789"
        mock_result.cid = "bafyreiabc123"
        mock_client.send_post.return_value = mock_result
        
        # Create client
        client = BlueskyClient(
            instance_url="https://bsky.social",
            handle="user.bsky.social",
            app_password="test_password"
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
        
        # Verify blob was uploaded
        self.assertEqual(mock_client.upload_blob.call_count, 1)
        
        # Verify models were called correctly
        mock_models.AppBskyEmbedImages.Image.assert_called_once_with(
            alt="A beautiful sunset",
            image=mock_blob_result.blob
        )
        mock_models.AppBskyEmbedImages.Main.assert_called_once()
        
        # Verify send_post was called with embed
        mock_client.send_post.assert_called_once()
        send_post_call = mock_client.send_post.call_args
        embed = send_post_call[1]['embed']
        self.assertEqual(embed, mock_embed)
        
        # Verify result
        self.assertIsNotNone(result)
        self.assertEqual(result["uri"], "at://did:plc:abc123/app.bsky.feed.post/xyz789")
        self.assertEqual(result["cid"], "bafyreiabc123")
    
    @patch("social.bluesky_client.models")
    @patch("social.base_client.os.path.exists")
    @patch("social.base_client.os.makedirs")
    @patch("builtins.open", create=True)
    @patch("social.base_client.requests.get")
    @patch("social.bluesky_client.Client")
    def test_post_with_multiple_images(self, mock_client_class, mock_requests_get, mock_open, mock_makedirs, mock_exists, mock_models):
        """Test posting status with multiple image attachments."""
        # Mock that files don't exist (not cached)
        mock_exists.return_value = False
        
        # Setup mock API
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        
        # Mock image downloads
        mock_response = MagicMock()
        mock_response.content = b"fake_image_data"
        mock_response.raise_for_status = MagicMock()
        mock_requests_get.return_value = mock_response
        
        # Mock upload_blob results
        mock_blob1 = MagicMock()
        mock_blob1.blob = MagicMock()
        mock_blob2 = MagicMock()
        mock_blob2.blob = MagicMock()
        mock_blob3 = MagicMock()
        mock_blob3.blob = MagicMock()
        mock_client.upload_blob.side_effect = [mock_blob1, mock_blob2, mock_blob3]
        
        # Mock models.AppBskyEmbedImages
        mock_image1 = MagicMock()
        mock_image1.alt = "First image"
        mock_image2 = MagicMock()
        mock_image2.alt = "Second image"
        mock_image3 = MagicMock()
        mock_image3.alt = "Third image"
        mock_models.AppBskyEmbedImages.Image.side_effect = [mock_image1, mock_image2, mock_image3]
        
        mock_embed = MagicMock(spec=models.AppBskyEmbedImages.Main)
        mock_embed.images = [mock_image1, mock_image2, mock_image3]
        mock_models.AppBskyEmbedImages.Main.return_value = mock_embed
        
        # Mock send_post result
        mock_result = MagicMock()
        mock_result.uri = "at://did:plc:abc123/app.bsky.feed.post/xyz789"
        mock_result.cid = "bafyreiabc123"
        mock_client.send_post.return_value = mock_result
        
        # Create client
        client = BlueskyClient(
            instance_url="https://bsky.social",
            handle="user.bsky.social",
            app_password="test_password"
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
        
        # Verify all blobs were uploaded
        self.assertEqual(mock_client.upload_blob.call_count, 3)
        
        # Verify models were called correctly
        self.assertEqual(mock_models.AppBskyEmbedImages.Image.call_count, 3)
        mock_models.AppBskyEmbedImages.Main.assert_called_once()
        
        # Verify send_post was called with embed
        mock_client.send_post.assert_called_once()
        send_post_call = mock_client.send_post.call_args
        embed = send_post_call[1]['embed']
        self.assertEqual(embed, mock_embed)
        
        # Verify result
        self.assertIsNotNone(result)
    
    @patch("social.base_client.os.path.exists")
    @patch("social.base_client.requests.get")
    @patch("social.bluesky_client.Client")
    def test_post_with_failed_image_download(self, mock_client_class, mock_requests_get, mock_exists):
        """Test posting when image download fails - should still post without media."""
        # Mock that file doesn't exist
        mock_exists.return_value = False
        
        # Setup mock API
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        
        # Mock failed image download
        mock_requests_get.side_effect = Exception("Network error")
        
        # Mock send_post result
        mock_result = MagicMock()
        mock_result.uri = "at://did:plc:abc123/app.bsky.feed.post/xyz789"
        mock_result.cid = "bafyreiabc123"
        mock_client.send_post.return_value = mock_result
        
        # Create client
        client = BlueskyClient(
            instance_url="https://bsky.social",
            handle="user.bsky.social",
            app_password="test_password"
        )
        
        # Post with image URL that will fail to download
        result = client.post(
            "Text post",
            media_urls=["https://example.com/broken.jpg"]
        )
        
        # Verify download was attempted
        mock_requests_get.assert_called_once()
        
        # Verify upload_blob was NOT called (no successful download)
        mock_client.upload_blob.assert_not_called()
        
        # Verify send_post was still called without embed
        mock_client.send_post.assert_called_once()
        send_post_call = mock_client.send_post.call_args
        self.assertEqual(send_post_call[1]['embed'], None)
        
        # Verify result
        self.assertIsNotNone(result)
    
    @patch("social.bluesky_client.models")
    @patch("social.base_client.os.path.exists")
    @patch("social.base_client.os.makedirs")
    @patch("builtins.open", create=True)
    @patch("social.base_client.requests.get")
    @patch("social.bluesky_client.Client")
    def test_post_without_image_descriptions(self, mock_client_class, mock_requests_get, mock_open, mock_makedirs, mock_exists, mock_models):
        """Test posting with images but no alt text descriptions."""
        # Mock that file doesn't exist (not cached)
        mock_exists.return_value = False
        
        # Setup mock API
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        
        # Mock image download
        mock_response = MagicMock()
        mock_response.content = b"fake_image_data"
        mock_response.raise_for_status = MagicMock()
        mock_requests_get.return_value = mock_response
        
        # Mock upload_blob result
        mock_blob_result = MagicMock()
        mock_blob_result.blob = MagicMock()
        mock_client.upload_blob.return_value = mock_blob_result
        
        # Mock models.AppBskyEmbedImages
        mock_image = MagicMock()
        mock_image.alt = ""
        mock_image.image = mock_blob_result.blob
        mock_models.AppBskyEmbedImages.Image.return_value = mock_image
        
        mock_embed = MagicMock(spec=models.AppBskyEmbedImages.Main)
        mock_embed.images = [mock_image]
        mock_models.AppBskyEmbedImages.Main.return_value = mock_embed
        
        # Mock send_post result
        mock_result = MagicMock()
        mock_result.uri = "at://did:plc:abc123/app.bsky.feed.post/xyz789"
        mock_result.cid = "bafyreiabc123"
        mock_client.send_post.return_value = mock_result
        
        # Create client
        client = BlueskyClient(
            instance_url="https://bsky.social",
            handle="user.bsky.social",
            app_password="test_password"
        )
        
        # Post with image but no descriptions
        result = client.post(
            "Photo post",
            media_urls=["https://example.com/image.jpg"]
        )
        
        # Verify models were called correctly with empty alt text
        mock_models.AppBskyEmbedImages.Image.assert_called_once_with(
            alt="",
            image=mock_blob_result.blob
        )
        mock_models.AppBskyEmbedImages.Main.assert_called_once()
        
        # Verify send_post was called with embed
        mock_client.send_post.assert_called_once()
        send_post_call = mock_client.send_post.call_args
        embed = send_post_call[1]['embed']
        self.assertEqual(embed, mock_embed)
        
        # Verify result
        self.assertIsNotNone(result)
    
    @patch("builtins.open", create=True)
    @patch("social.bluesky_client.Client")
    def test_post_with_upload_blob_failure(self, mock_client_class, mock_open):
        """Test posting when blob upload fails - should still post without that image."""
        # Setup mock API
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        
        # Mock file open
        mock_file = MagicMock()
        mock_file.read.return_value = b"fake_image_data"
        mock_file.__enter__.return_value = mock_file
        mock_open.return_value = mock_file
        
        # Mock upload_blob to raise exception
        mock_client.upload_blob.side_effect = Exception("Upload failed")
        
        # Mock send_post result
        mock_result = MagicMock()
        mock_result.uri = "at://did:plc:abc123/app.bsky.feed.post/xyz789"
        mock_result.cid = "bafyreiabc123"
        mock_client.send_post.return_value = mock_result
        
        # Create client
        client = BlueskyClient(
            instance_url="https://bsky.social",
            handle="user.bsky.social",
            app_password="test_password"
        )
        
        # Mock _download_image to return a valid path
        with patch.object(client, '_download_image', return_value='/tmp/test.jpg'):
            # Post with image
            result = client.post(
                "Text post",
                media_urls=["https://example.com/image.jpg"]
            )
        
        # Verify upload_blob was called
        mock_client.upload_blob.assert_called_once()
        
        # Verify send_post was still called without embed
        mock_client.send_post.assert_called_once()
        send_post_call = mock_client.send_post.call_args
        self.assertEqual(send_post_call[1]['embed'], None)
        
        # Verify result
        self.assertIsNotNone(result)
    
    @patch("social.bluesky_client.Client")
    def test_post_with_links(self, mock_client_class):
        """Test posting content with URLs to ensure they are properly formatted as links."""
        # Setup mock API
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        
        # Mock send_post result
        mock_result = MagicMock()
        mock_result.uri = "at://did:plc:abc123/app.bsky.feed.post/xyz789"
        mock_result.cid = "bafyreiabc123"
        mock_client.send_post.return_value = mock_result
        
        # Create client
        client = BlueskyClient(
            instance_url="https://bsky.social",
            handle="user.bsky.social",
            app_password="test_password"
        )
        
        # Post with a URL
        content = "Check out https://example.com for more info"
        result = client.post(content)
        
        # Verify send_post was called
        mock_client.send_post.assert_called_once()
        
        # Get the TextBuilder argument
        text_builder_arg = mock_client.send_post.call_args[0][0]
        
        # Verify the text is correct
        self.assertEqual(text_builder_arg.build_text(), content)
        
        # Verify that facets were created (link should have facets)
        facets = text_builder_arg.build_facets()
        self.assertGreater(len(facets), 0, "Expected at least one facet for the URL")
        
        # Verify result
        self.assertIsNotNone(result)
    
    @patch("social.bluesky_client.Client")
    def test_post_with_hashtags(self, mock_client_class):
        """Test posting content with hashtags to ensure they are properly formatted as tags."""
        # Setup mock API
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        
        # Mock send_post result
        mock_result = MagicMock()
        mock_result.uri = "at://did:plc:abc123/app.bsky.feed.post/xyz789"
        mock_result.cid = "bafyreiabc123"
        mock_client.send_post.return_value = mock_result
        
        # Create client
        client = BlueskyClient(
            instance_url="https://bsky.social",
            handle="user.bsky.social",
            app_password="test_password"
        )
        
        # Post with hashtags
        content = "Hello world #python #atproto #bluesky"
        result = client.post(content)
        
        # Verify send_post was called
        mock_client.send_post.assert_called_once()
        
        # Get the TextBuilder argument
        text_builder_arg = mock_client.send_post.call_args[0][0]
        
        # Verify the text is correct
        self.assertEqual(text_builder_arg.build_text(), content)
        
        # Verify that facets were created (hashtags should have facets)
        facets = text_builder_arg.build_facets()
        self.assertEqual(len(facets), 3, "Expected three facets for three hashtags")
        
        # Verify all facets are Tag type
        for facet in facets:
            self.assertEqual(len(facet.features), 1, "Each facet should have one feature")
            self.assertIsInstance(facet.features[0], models.AppBskyRichtextFacet.Tag,
                                "Facet should be a Tag type")
        
        # Verify result
        self.assertIsNotNone(result)
    
    @patch("social.bluesky_client.Client")
    def test_post_with_links_and_hashtags(self, mock_client_class):
        """Test posting content with both URLs and hashtags."""
        # Setup mock API
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        
        # Mock send_post result
        mock_result = MagicMock()
        mock_result.uri = "at://did:plc:abc123/app.bsky.feed.post/xyz789"
        mock_result.cid = "bafyreiabc123"
        mock_client.send_post.return_value = mock_result
        
        # Create client
        client = BlueskyClient(
            instance_url="https://bsky.social",
            handle="user.bsky.social",
            app_password="test_password"
        )
        
        # Post with both URLs and hashtags
        content = "Check out https://atproto.blue for the SDK docs #python #atproto"
        result = client.post(content)
        
        # Verify send_post was called
        mock_client.send_post.assert_called_once()
        
        # Get the TextBuilder argument
        text_builder_arg = mock_client.send_post.call_args[0][0]
        
        # Verify the text is correct
        self.assertEqual(text_builder_arg.build_text(), content)
        
        # Verify that facets were created (1 link + 2 hashtags = 3 facets)
        facets = text_builder_arg.build_facets()
        self.assertEqual(len(facets), 3, "Expected three facets (1 link, 2 hashtags)")
        
        # Verify facet types: first should be Link, rest should be Tags
        self.assertIsInstance(facets[0].features[0], models.AppBskyRichtextFacet.Link,
                            "First facet should be a Link")
        self.assertIsInstance(facets[1].features[0], models.AppBskyRichtextFacet.Tag,
                            "Second facet should be a Tag")
        self.assertIsInstance(facets[2].features[0], models.AppBskyRichtextFacet.Tag,
                            "Third facet should be a Tag")
        
        # Verify result
        self.assertIsNotNone(result)
    
    @patch("social.bluesky_client.Client")
    def test_post_with_multiple_urls(self, mock_client_class):
        """Test posting content with multiple URLs."""
        # Setup mock API
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        
        # Mock send_post result
        mock_result = MagicMock()
        mock_result.uri = "at://did:plc:abc123/app.bsky.feed.post/xyz789"
        mock_result.cid = "bafyreiabc123"
        mock_client.send_post.return_value = mock_result
        
        # Create client
        client = BlueskyClient(
            instance_url="https://bsky.social",
            handle="user.bsky.social",
            app_password="test_password"
        )
        
        # Post with multiple URLs
        content = "Visit https://example.com and https://atproto.blue for more"
        result = client.post(content)
        
        # Verify send_post was called
        mock_client.send_post.assert_called_once()
        
        # Get the TextBuilder argument
        text_builder_arg = mock_client.send_post.call_args[0][0]
        
        # Verify the text is correct
        self.assertEqual(text_builder_arg.build_text(), content)
        
        # Verify that facets were created (2 URLs)
        facets = text_builder_arg.build_facets()
        self.assertEqual(len(facets), 2, "Expected two facets for two URLs")
        
        # Verify result
        self.assertIsNotNone(result)
    
    @patch("social.bluesky_client.Client")
    def test_post_plain_text_without_links_or_tags(self, mock_client_class):
        """Test posting plain text without URLs or hashtags still works."""
        # Setup mock API
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        
        # Mock send_post result
        mock_result = MagicMock()
        mock_result.uri = "at://did:plc:abc123/app.bsky.feed.post/xyz789"
        mock_result.cid = "bafyreiabc123"
        mock_client.send_post.return_value = mock_result
        
        # Create client
        client = BlueskyClient(
            instance_url="https://bsky.social",
            handle="user.bsky.social",
            app_password="test_password"
        )
        
        # Post plain text
        content = "Just a simple message without any links or hashtags"
        result = client.post(content)
        
        # Verify send_post was called
        mock_client.send_post.assert_called_once()
        
        # Get the TextBuilder argument
        text_builder_arg = mock_client.send_post.call_args[0][0]
        
        # Verify the text is correct
        self.assertEqual(text_builder_arg.build_text(), content)
        
        # Verify that no facets were created
        facets = text_builder_arg.build_facets()
        self.assertEqual(len(facets), 0, "Expected no facets for plain text")
        
        # Verify result
        self.assertIsNotNone(result)
    
    @patch("social.bluesky_client.Client")
    def test_post_with_url_ending_with_punctuation(self, mock_client_class):
        """Test that URLs at the end of sentences don't include trailing punctuation."""
        # Setup mock API
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        # Mock send_post result
        mock_result = MagicMock()
        mock_result.uri = "at://did:plc:abc123/app.bsky.feed.post/xyz789"
        mock_result.cid = "bafyreiabc123"
        mock_client.send_post.return_value = mock_result

        # Create client
        client = BlueskyClient(
            instance_url="https://bsky.social",
            handle="user.bsky.social",
            app_password="test_password"
        )

        # Post with URL ending with period
        content = "Visit https://example.com."
        result = client.post(content)

        # Verify send_post was called
        mock_client.send_post.assert_called_once()

        # Get the TextBuilder argument
        text_builder_arg = mock_client.send_post.call_args[0][0]

        # Verify the text is correct (should include the period after the URL)
        self.assertEqual(text_builder_arg.build_text(), content)

        # Verify that facets were created
        facets = text_builder_arg.build_facets()
        self.assertEqual(len(facets), 1, "Expected one facet for the URL")

        # Verify the URL doesn't include the trailing period
        self.assertIsInstance(facets[0].features[0], models.AppBskyRichtextFacet.Link)
        # The link text should be the URL without the trailing period
        link_text = content.encode('UTF-8')[facets[0].index.byte_start:facets[0].index.byte_end].decode('UTF-8')
        self.assertEqual(link_text, "https://example.com", "URL should not include trailing period")

        # Verify result
        self.assertIsNotNone(result)

    @patch("social.bluesky_client.Client")
    def test_post_re_authenticates_before_posting(self, mock_client_class):
        """Test that post() re-authenticates before each post to avoid ExpiredToken errors."""
        # Setup mock API
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        # Mock send_post result
        mock_result = MagicMock()
        mock_result.uri = "at://did:plc:abc123/app.bsky.feed.post/xyz789"
        mock_result.cid = "bafyreiabc123"
        mock_client.send_post.return_value = mock_result

        # Create client
        client = BlueskyClient(
            instance_url="https://bsky.social",
            handle="user.bsky.social",
            app_password="test_password"
        )

        # Reset login call count after initial setup
        initial_login_count = mock_client.login.call_count

        # Post content
        result = client.post("Hello Bluesky!")

        # Verify login was called again during re-authentication
        self.assertEqual(
            mock_client.login.call_count,
            initial_login_count + 1,
            "Expected login to be called during re-authentication before post"
        )

        # Verify login was called with correct credentials
        mock_client.login.assert_called_with(
            login="user.bsky.social",
            password="test_password"
        )

        # Verify result
        self.assertIsNotNone(result)
        self.assertEqual(result["uri"], "at://did:plc:abc123/app.bsky.feed.post/xyz789")

    @patch("social.bluesky_client.Client")
    def test_post_fails_when_re_authentication_fails(self, mock_client_class):
        """Test that post() returns None when re-authentication fails."""
        # Setup mock API for initial setup
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        # Create client (initial login succeeds)
        client = BlueskyClient(
            instance_url="https://bsky.social",
            handle="user.bsky.social",
            app_password="test_password"
        )

        # Make login fail for re-authentication
        mock_client.login.side_effect = Exception("Auth failed - token revoked")

        # Attempt to post
        result = client.post("Test post")

        # Verify result is None because re-authentication failed
        self.assertIsNone(result)

        # Verify send_post was NOT called (we should fail before attempting to post)
        mock_client.send_post.assert_not_called()

    @patch("social.bluesky_client.Client")
    def test_multiple_posts_re_authenticate_each_time(self, mock_client_class):
        """Test that each post call re-authenticates to ensure fresh tokens."""
        # Setup mock API
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        # Mock send_post result
        mock_result = MagicMock()
        mock_result.uri = "at://did:plc:abc123/app.bsky.feed.post/xyz789"
        mock_result.cid = "bafyreiabc123"
        mock_client.send_post.return_value = mock_result

        # Create client
        client = BlueskyClient(
            instance_url="https://bsky.social",
            handle="user.bsky.social",
            app_password="test_password"
        )

        # Reset login call count after initial setup
        initial_login_count = mock_client.login.call_count

        # Post multiple times
        client.post("First post")
        client.post("Second post")
        client.post("Third post")

        # Verify login was called for each post (3 re-authentications)
        self.assertEqual(
            mock_client.login.call_count,
            initial_login_count + 3,
            "Expected login to be called once per post for re-authentication"
        )


class TestBlueskyImageCompression(unittest.TestCase):
    """Test suite for BlueskyClient._compress_image method."""

    @staticmethod
    def _make_jpeg(width, height, quality=95):
        """Create a JPEG image of the given dimensions and return its bytes."""
        img = Image.new('RGB', (width, height), color='red')
        buf = io.BytesIO()
        img.save(buf, format='JPEG', quality=quality)
        return buf.getvalue()

    @staticmethod
    def _make_png_rgba(width, height):
        """Create an RGBA PNG image and return its bytes."""
        img = Image.new('RGBA', (width, height), color=(255, 0, 0, 128))
        buf = io.BytesIO()
        img.save(buf, format='PNG')
        return buf.getvalue()

    def test_small_image_returned_unchanged(self):
        """Images already under the size limit should be returned as-is."""
        small_data = self._make_jpeg(100, 100)
        result = BlueskyClient._compress_image(small_data, max_size=1_000_000)
        self.assertEqual(result, small_data)

    def test_large_image_is_compressed_below_limit(self):
        """A large image should be compressed to fit under max_size."""
        # Create a large noisy image that compresses poorly
        img = Image.new('RGB', (4000, 3000), color='red')
        # Add noise-like pattern to make it harder to compress
        pixels = img.load()
        for x in range(0, 4000, 2):
            for y in range(0, 3000, 2):
                pixels[x, y] = ((x * 7) % 256, (y * 13) % 256, ((x + y) * 3) % 256)
        buf = io.BytesIO()
        img.save(buf, format='JPEG', quality=100)
        large_data = buf.getvalue()

        # Ensure the test data is actually over the limit
        self.assertGreater(len(large_data), 1_000_000)

        result = BlueskyClient._compress_image(large_data, max_size=1_000_000)
        self.assertLessEqual(len(result), 1_000_000)

    def test_image_resized_to_max_dimension(self):
        """Images wider than max_dimension should be resized."""
        # Create a noisy 5000x2500 image that exceeds the size limit
        img = Image.new('RGB', (5000, 2500), color='red')
        pixels = img.load()
        for x in range(0, 5000, 2):
            for y in range(0, 2500, 2):
                pixels[x, y] = ((x * 7) % 256, (y * 13) % 256, ((x + y) * 3) % 256)
        buf = io.BytesIO()
        img.save(buf, format='JPEG', quality=100)
        data = buf.getvalue()
        # Use a max_size just below the data size to force compression
        result = BlueskyClient._compress_image(data, max_size=len(data) - 1, max_dimension=2500)
        result_img = Image.open(io.BytesIO(result))
        self.assertLessEqual(max(result_img.size), 2500)

    def test_tall_image_resized_to_max_dimension(self):
        """Images taller than max_dimension should be resized along height."""
        # Create a noisy 1500x4000 image that exceeds the size limit
        img = Image.new('RGB', (1500, 4000), color='blue')
        pixels = img.load()
        for x in range(0, 1500, 2):
            for y in range(0, 4000, 2):
                pixels[x, y] = ((x * 11) % 256, (y * 7) % 256, ((x + y) * 5) % 256)
        buf = io.BytesIO()
        img.save(buf, format='JPEG', quality=100)
        data = buf.getvalue()
        # Use a max_size just below the data size to force compression
        result = BlueskyClient._compress_image(data, max_size=len(data) - 1, max_dimension=2500)
        result_img = Image.open(io.BytesIO(result))
        self.assertLessEqual(result_img.height, 2500)
        # Aspect ratio should be approximately preserved
        expected_width = int(1500 * (2500 / 4000))
        self.assertAlmostEqual(result_img.width, expected_width, delta=1)

    def test_image_within_dimension_not_resized(self):
        """Images within max_dimension should not be resized."""
        data = self._make_jpeg(2000, 1500)
        result = BlueskyClient._compress_image(data, max_size=10_000_000, max_dimension=2500)
        result_img = Image.open(io.BytesIO(result))
        self.assertEqual(result_img.size, (2000, 1500))

    def test_rgba_image_converted_to_rgb(self):
        """RGBA images should be converted to RGB for JPEG output."""
        # Create a noisy RGBA image so it's large enough to trigger compression
        img = Image.new('RGBA', (3000, 3000), color=(255, 0, 0, 128))
        pixels = img.load()
        for x in range(0, 3000, 2):
            for y in range(0, 3000, 2):
                pixels[x, y] = ((x * 7) % 256, (y * 13) % 256, ((x + y) * 3) % 256, 200)
        buf = io.BytesIO()
        img.save(buf, format='PNG')
        rgba_data = buf.getvalue()

        # Use a max_size that forces compression
        result = BlueskyClient._compress_image(rgba_data, max_size=len(rgba_data) - 1)
        self.assertLessEqual(len(result), len(rgba_data) - 1)
        # Verify it's a valid JPEG with RGB mode
        result_img = Image.open(io.BytesIO(result))
        self.assertEqual(result_img.mode, 'RGB')

    def test_corrupt_image_returns_original(self):
        """If the image can't be opened, the original data should be returned."""
        corrupt_data = b'\x00' * 2_000_000  # Not a valid image
        result = BlueskyClient._compress_image(corrupt_data, max_size=1_000_000)
        self.assertEqual(result, corrupt_data)

    def test_quality_reduction_produces_valid_jpeg(self):
        """Compressed output should be a valid JPEG image."""
        img = Image.new('RGB', (3500, 2500), color='blue')
        pixels = img.load()
        for x in range(0, 3500, 2):
            for y in range(0, 2500, 2):
                pixels[x, y] = ((x * 11) % 256, (y * 7) % 256, ((x + y) * 5) % 256)
        buf = io.BytesIO()
        img.save(buf, format='JPEG', quality=100)
        large_data = buf.getvalue()

        if len(large_data) <= 1_000_000:
            self.skipTest("Test image not large enough to trigger compression")

        result = BlueskyClient._compress_image(large_data, max_size=1_000_000)
        # Verify valid JPEG
        result_img = Image.open(io.BytesIO(result))
        self.assertEqual(result_img.format, 'JPEG')

    @patch("social.bluesky_client.models")
    @patch("builtins.open", create=True)
    @patch("social.bluesky_client.Client")
    def test_post_compresses_image_before_upload(self, mock_client_class, mock_open, mock_models):
        """Test that the post method compresses images before uploading."""
        # Setup mock API
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        # Create a large image to trigger compression
        img = Image.new('RGB', (4000, 3000), color='green')
        pixels = img.load()
        for x in range(0, 4000, 3):
            for y in range(0, 3000, 3):
                pixels[x, y] = ((x * 7) % 256, (y * 13) % 256, ((x + y) * 3) % 256)
        buf = io.BytesIO()
        img.save(buf, format='JPEG', quality=100)
        large_image_data = buf.getvalue()

        # Mock file open to return our large image
        mock_file = MagicMock()
        mock_file.read.return_value = large_image_data
        mock_file.__enter__.return_value = mock_file
        mock_open.return_value = mock_file

        # Mock upload_blob
        mock_blob_result = MagicMock()
        mock_blob_result.blob = MagicMock()
        mock_client.upload_blob.return_value = mock_blob_result

        # Mock models
        mock_image = MagicMock()
        mock_models.AppBskyEmbedImages.Image.return_value = mock_image
        mock_embed = MagicMock()
        mock_models.AppBskyEmbedImages.Main.return_value = mock_embed

        # Mock send_post result
        mock_result = MagicMock()
        mock_result.uri = "at://did:plc:abc123/app.bsky.feed.post/xyz789"
        mock_result.cid = "bafyreiabc123"
        mock_client.send_post.return_value = mock_result

        # Create client
        client = BlueskyClient(
            instance_url="https://bsky.social",
            handle="user.bsky.social",
            app_password="test_password"
        )

        # Mock _download_image to return a valid path
        with patch.object(client, '_download_image', return_value='/tmp/test.jpg'):
            result = client.post(
                "Large image post",
                media_urls=["https://example.com/large.jpg"],
                media_descriptions=["A large image"]
            )

        # Verify upload_blob was called with compressed data (not the original)
        mock_client.upload_blob.assert_called_once()
        uploaded_data = mock_client.upload_blob.call_args[0][0]

        if len(large_image_data) > 1_000_000:
            # If the original was over the limit, the uploaded data should be smaller
            self.assertLessEqual(len(uploaded_data), 1_000_000)
            self.assertNotEqual(uploaded_data, large_image_data)

        self.assertIsNotNone(result)


if __name__ == "__main__":
    unittest.main()
