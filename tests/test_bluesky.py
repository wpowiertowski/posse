"""
Integration Tests for Bluesky Client Module.

This test suite validates the Bluesky authentication functionality
by testing login with provided credentials from Docker secrets.

Test Coverage:
    - Login with credentials from secrets
    - Posting to Bluesky
    - Credential verification

Testing Strategy:
    Tests use mocked credentials from Docker secrets to verify
    authentication initialization works correctly.

Running Tests:
    $ PYTHONPATH=src python -m unittest tests.test_bluesky -v
"""
import unittest
from unittest.mock import patch, MagicMock, call

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
    
    @patch("social.base_client.os.path.exists")
    @patch("social.base_client.os.makedirs")
    @patch("builtins.open", create=True)
    @patch("social.base_client.requests.get")
    @patch("social.bluesky_client.Client")
    def test_post_with_single_image(self, mock_client_class, mock_requests_get, mock_open, mock_makedirs, mock_exists):
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
        
        # Mock get_embed_images
        mock_embed = MagicMock()
        mock_client.get_embed_images.return_value = mock_embed
        
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
        
        # Verify get_embed_images was called with correct structure
        mock_client.get_embed_images.assert_called_once()
        embed_args = mock_client.get_embed_images.call_args[0][0]
        self.assertEqual(len(embed_args), 1)
        self.assertEqual(embed_args[0]['alt'], "A beautiful sunset")
        self.assertEqual(embed_args[0]['blob'], mock_blob_result.blob)
        
        # Verify send_post was called with embed
        mock_client.send_post.assert_called_once()
        send_post_call = mock_client.send_post.call_args
        self.assertEqual(send_post_call[1]['embed'], mock_embed)
        
        # Verify result
        self.assertIsNotNone(result)
        self.assertEqual(result["uri"], "at://did:plc:abc123/app.bsky.feed.post/xyz789")
        self.assertEqual(result["cid"], "bafyreiabc123")
    
    @patch("social.base_client.os.path.exists")
    @patch("social.base_client.os.makedirs")
    @patch("builtins.open", create=True)
    @patch("social.base_client.requests.get")
    @patch("social.bluesky_client.Client")
    def test_post_with_multiple_images(self, mock_client_class, mock_requests_get, mock_open, mock_makedirs, mock_exists):
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
        
        # Mock get_embed_images
        mock_embed = MagicMock()
        mock_client.get_embed_images.return_value = mock_embed
        
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
        
        # Verify get_embed_images was called with correct structure
        mock_client.get_embed_images.assert_called_once()
        embed_args = mock_client.get_embed_images.call_args[0][0]
        self.assertEqual(len(embed_args), 3)
        self.assertEqual(embed_args[0]['alt'], "First image")
        self.assertEqual(embed_args[1]['alt'], "Second image")
        self.assertEqual(embed_args[2]['alt'], "Third image")
        
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
        
        # Verify get_embed_images was NOT called (no images)
        mock_client.get_embed_images.assert_not_called()
        
        # Verify send_post was still called without embed
        mock_client.send_post.assert_called_once()
        send_post_call = mock_client.send_post.call_args
        self.assertEqual(send_post_call[1]['embed'], None)
        
        # Verify result
        self.assertIsNotNone(result)
    
    @patch("social.base_client.os.path.exists")
    @patch("social.base_client.os.makedirs")
    @patch("builtins.open", create=True)
    @patch("social.base_client.requests.get")
    @patch("social.bluesky_client.Client")
    def test_post_without_image_descriptions(self, mock_client_class, mock_requests_get, mock_open, mock_makedirs, mock_exists):
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
        
        # Mock get_embed_images
        mock_embed = MagicMock()
        mock_client.get_embed_images.return_value = mock_embed
        
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
        
        # Verify get_embed_images was called with empty alt text
        mock_client.get_embed_images.assert_called_once()
        embed_args = mock_client.get_embed_images.call_args[0][0]
        self.assertEqual(len(embed_args), 1)
        self.assertEqual(embed_args[0]['alt'], "")
        
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
        
        # Verify get_embed_images was NOT called (no successful uploads)
        mock_client.get_embed_images.assert_not_called()
        
        # Verify send_post was still called without embed
        mock_client.send_post.assert_called_once()
        send_post_call = mock_client.send_post.call_args
        self.assertEqual(send_post_call[1]['embed'], None)
        
        # Verify result
        self.assertIsNotNone(result)


if __name__ == "__main__":
    unittest.main()
