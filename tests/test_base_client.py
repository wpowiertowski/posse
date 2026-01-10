"""
Tests for Base Social Media Client Module.

This test suite validates the common functionality in the base client,
particularly the image download and caching functionality.

Test Coverage:
    - Image download with predictable paths
    - Image caching (reuse of previously downloaded images)
    - Image removal functionality
    - Cache path generation
"""
import unittest
import os
import tempfile
import hashlib
from unittest.mock import patch, MagicMock, mock_open

from social.base_client import SocialMediaClient


class ConcreteClient(SocialMediaClient):
    """Concrete implementation of SocialMediaClient for testing."""
    
    def _initialize_api(self):
        """Mock API initialization."""
        self.api = MagicMock()
    
    def post(self, content, **kwargs):
        """Mock post method."""
        return {"status": "posted"}
    
    def verify_credentials(self):
        """Mock verify credentials."""
        return {"username": "test_user"}


class TestBaseClient(unittest.TestCase):
    """Test suite for SocialMediaClient base class."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.client = ConcreteClient(
            instance_url="https://example.com",
            access_token="test_token"
        )
    
    def test_get_image_cache_path_consistency(self):
        """Test that cache paths are consistent for the same URL."""
        url = "https://example.com/image.jpg"
        
        path1 = self.client._get_image_cache_path(url)
        path2 = self.client._get_image_cache_path(url)
        
        # Same URL should always generate same path
        self.assertEqual(path1, path2)
    
    def test_get_image_cache_path_format(self):
        """Test that cache path has expected format."""
        url = "https://example.com/image.jpg"
        path = self.client._get_image_cache_path(url)
        
        # Should contain the hash
        url_hash = hashlib.md5(url.encode()).hexdigest()
        self.assertIn(url_hash, path)
        
        # Should have .jpg extension
        self.assertTrue(path.endswith('.jpg'))
        
        # Should be in posse_image_cache directory
        self.assertIn('posse_image_cache', path)
    
    def test_get_image_cache_path_default_extension(self):
        """Test that default extension is used when URL has no extension."""
        url = "https://example.com/image"
        path = self.client._get_image_cache_path(url)
        
        # Should use default .jpg extension
        self.assertTrue(path.endswith('.jpg'))
    
    def test_get_image_cache_path_preserves_extension(self):
        """Test that original file extension is preserved."""
        url = "https://example.com/image.png"
        path = self.client._get_image_cache_path(url)
        
        # Should preserve .png extension
        self.assertTrue(path.endswith('.png'))
    
    @patch("social.base_client.os.path.exists")
    @patch("social.base_client.requests.get")
    @patch("social.base_client.os.makedirs")
    @patch("builtins.open", new_callable=mock_open)
    def test_download_image_new(self, mock_file, mock_makedirs, mock_requests_get, mock_exists):
        """Test downloading a new image."""
        # Mock that file doesn't exist
        mock_exists.return_value = False
        
        # Mock successful download
        mock_response = MagicMock()
        mock_response.content = b"fake_image_data"
        mock_response.raise_for_status = MagicMock()
        mock_requests_get.return_value = mock_response
        
        url = "https://example.com/image.jpg"
        result = self.client._download_image(url)
        
        # Verify download was attempted
        mock_requests_get.assert_called_once_with(url, timeout=30)
        
        # Verify cache directory was created
        mock_makedirs.assert_called_once()
        
        # Verify file was written
        mock_file.assert_called_once()
        mock_file().write.assert_called_once_with(b"fake_image_data")
        
        # Verify result is the cache path
        self.assertIsNotNone(result)
        self.assertIn(hashlib.md5(url.encode()).hexdigest(), result)
    
    @patch("social.base_client.os.path.exists")
    def test_download_image_cached(self, mock_exists):
        """Test that cached images are reused without re-downloading."""
        # Mock that file already exists
        mock_exists.return_value = True
        
        url = "https://example.com/image.jpg"
        
        with patch("social.base_client.requests.get") as mock_requests_get:
            result = self.client._download_image(url)
            
            # Verify download was NOT attempted
            mock_requests_get.assert_not_called()
            
            # Verify result is the cache path
            self.assertIsNotNone(result)
            self.assertIn(hashlib.md5(url.encode()).hexdigest(), result)
    
    @patch("social.base_client.requests.get")
    def test_download_image_failure(self, mock_requests_get):
        """Test handling of download failures."""
        # Mock failed download
        mock_requests_get.side_effect = Exception("Network error")
        
        url = "https://example.com/broken.jpg"
        result = self.client._download_image(url)
        
        # Verify result is None on failure
        self.assertIsNone(result)
    
    @patch("social.base_client.os.path.exists")
    @patch("social.base_client.os.unlink")
    def test_remove_images_single(self, mock_unlink, mock_exists):
        """Test removing a single cached image."""
        # Mock that file exists
        mock_exists.return_value = True
        
        url = "https://example.com/image.jpg"
        self.client._remove_images([url])
        
        # Verify file was deleted
        mock_unlink.assert_called_once()
        call_path = mock_unlink.call_args[0][0]
        self.assertIn(hashlib.md5(url.encode()).hexdigest(), call_path)
    
    @patch("social.base_client.os.path.exists")
    @patch("social.base_client.os.unlink")
    def test_remove_images_multiple(self, mock_unlink, mock_exists):
        """Test removing multiple cached images."""
        # Mock that files exist
        mock_exists.return_value = True
        
        urls = [
            "https://example.com/image1.jpg",
            "https://example.com/image2.jpg",
            "https://example.com/image3.jpg"
        ]
        self.client._remove_images(urls)
        
        # Verify all files were deleted
        self.assertEqual(mock_unlink.call_count, 3)
    
    @patch("social.base_client.os.path.exists")
    @patch("social.base_client.os.unlink")
    def test_remove_images_non_existent(self, mock_unlink, mock_exists):
        """Test removing images that don't exist (should not error)."""
        # Mock that file doesn't exist
        mock_exists.return_value = False
        
        url = "https://example.com/nonexistent.jpg"
        self.client._remove_images([url])
        
        # Verify unlink was NOT called
        mock_unlink.assert_not_called()
    
    @patch("social.base_client.os.path.exists")
    @patch("social.base_client.os.unlink")
    def test_remove_images_failure_continues(self, mock_unlink, mock_exists):
        """Test that removal continues even if one file fails."""
        # Mock that files exist
        mock_exists.return_value = True
        
        # Mock that first deletion fails
        mock_unlink.side_effect = [Exception("Permission denied"), None, None]
        
        urls = [
            "https://example.com/image1.jpg",
            "https://example.com/image2.jpg",
            "https://example.com/image3.jpg"
        ]
        
        # Should not raise exception
        self.client._remove_images(urls)
        
        # Verify all deletions were attempted
        self.assertEqual(mock_unlink.call_count, 3)
    
    def test_image_constants(self):
        """Test that image-related constants are defined."""
        self.assertEqual(self.client.IMAGE_DOWNLOAD_TIMEOUT, 30)
        self.assertEqual(self.client.DEFAULT_IMAGE_EXTENSION, ".jpg")


if __name__ == "__main__":
    unittest.main()
