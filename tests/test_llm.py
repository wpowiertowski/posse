"""
Tests for LLM Client functionality.

This module tests the LLM client for generating alt text for images
using vision-capable language models.
"""

import pytest
import json
import base64
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path
import tempfile
import os

from llm.llm_client import LLMClient


@pytest.fixture
def mock_config():
    """Provide a mock configuration dictionary."""
    return {
        "llm": {
            "enabled": True,
            "url": "llama-vision",
            "port": 5000,
            "timeout": 30
        }
    }


@pytest.fixture
def mock_config_disabled():
    """Provide a mock configuration with LLM disabled."""
    return {
        "llm": {
            "enabled": False,
            "url": "llama-vision",
            "port": 5000
        }
    }


@pytest.fixture
def mock_image_file(tmp_path):
    """Create a temporary image file for testing."""
    image_path = tmp_path / "test_image.jpg"
    # Create a minimal valid image file (1x1 pixel)
    image_data = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
    )
    image_path.write_bytes(image_data)
    return str(image_path)


class TestLLMClientInitialization:
    """Test LLM client initialization."""
    
    def test_init_with_url_and_port(self):
        """Test initialization with URL and port."""
        client = LLMClient(url="llama-vision", port=5000, enabled=True)
        assert client.enabled is True
        assert client.base_url == "http://llama-vision:5000"
        assert client.timeout == LLMClient.DEFAULT_TIMEOUT
    
    def test_init_with_http_url(self):
        """Test initialization with full HTTP URL."""
        client = LLMClient(url="http://llama-vision", port=5000, enabled=True)
        assert client.base_url == "http://llama-vision:5000"
    
    def test_init_with_https_url(self):
        """Test initialization with full HTTPS URL."""
        client = LLMClient(url="https://llama-vision.example.com", port=443, enabled=True)
        assert client.base_url == "https://llama-vision.example.com:443"
    
    def test_init_disabled(self):
        """Test initialization when disabled."""
        client = LLMClient(url="llama-vision", port=5000, enabled=False)
        assert client.enabled is False
        assert client.base_url is None
    
    def test_init_empty_url(self):
        """Test initialization with empty URL disables client."""
        client = LLMClient(url="", port=5000, enabled=True)
        assert client.enabled is False
    
    def test_init_custom_timeout(self):
        """Test initialization with custom timeout."""
        client = LLMClient(url="llama-vision", port=5000, enabled=True, timeout=120)
        assert client.timeout == 120
    
    def test_from_config(self, mock_config):
        """Test creating client from config dictionary."""
        client = LLMClient.from_config(mock_config)
        assert client.enabled is True
        assert client.base_url == "http://llama-vision:5000"
        assert client.timeout == 30
    
    def test_from_config_disabled(self, mock_config_disabled):
        """Test creating disabled client from config."""
        client = LLMClient.from_config(mock_config_disabled)
        assert client.enabled is False
    
    def test_from_config_missing_llm_section(self):
        """Test creating client when config has no LLM section."""
        client = LLMClient.from_config({})
        assert client.enabled is False


class TestLLMClientImageEncoding:
    """Test image encoding functionality."""
    
    def test_encode_image_to_base64(self, mock_image_file):
        """Test encoding an image file to base64."""
        client = LLMClient(url="llama-vision", port=5000, enabled=True)
        result = client._encode_image_to_base64(mock_image_file)
        
        assert result is not None
        assert isinstance(result, str)
        # Should be valid base64
        try:
            base64.b64decode(result)
        except Exception:
            pytest.fail("Result is not valid base64")
    
    def test_encode_nonexistent_file(self):
        """Test encoding a non-existent file returns None."""
        client = LLMClient(url="llama-vision", port=5000, enabled=True)
        result = client._encode_image_to_base64("/nonexistent/file.jpg")
        assert result is None


class TestLLMClientHealthCheck:
    """Test health check functionality."""
    
    @patch('requests.get')
    def test_health_check_healthy(self, mock_get):
        """Test health check when service is healthy."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "healthy",
            "model_loaded": True,
            "model_name": "test-model"
        }
        mock_get.return_value = mock_response
        
        client = LLMClient(url="llama-vision", port=5000, enabled=True)
        result = client._check_health()
        
        assert result is True
        mock_get.assert_called_once()
        assert "health" in mock_get.call_args[0][0]
    
    @patch('requests.get')
    def test_health_check_unhealthy(self, mock_get):
        """Test health check when service is unhealthy."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "unhealthy",
            "model_loaded": False
        }
        mock_get.return_value = mock_response
        
        client = LLMClient(url="llama-vision", port=5000, enabled=True)
        result = client._check_health()
        
        assert result is False
    
    @patch('requests.get')
    def test_health_check_error(self, mock_get):
        """Test health check when request fails."""
        mock_get.side_effect = Exception("Connection error")
        
        client = LLMClient(url="llama-vision", port=5000, enabled=True)
        result = client._check_health()
        
        assert result is False
    
    def test_health_check_disabled(self):
        """Test health check when client is disabled."""
        client = LLMClient(url="", enabled=False)
        result = client._check_health()
        assert result is False


class TestLLMClientAltTextGeneration:
    """Test alt text generation functionality."""
    
    @patch('requests.post')
    @patch('requests.get')
    def test_generate_alt_text_success(self, mock_get, mock_post, mock_image_file):
        """Test successful alt text generation."""
        # Mock health check
        mock_health_response = Mock()
        mock_health_response.status_code = 200
        mock_health_response.json.return_value = {
            "status": "healthy",
            "model_loaded": True
        }
        mock_get.return_value = mock_health_response
        
        # Mock inference request
        mock_infer_response = Mock()
        mock_infer_response.status_code = 200
        mock_infer_response.json.return_value = {
            "success": True,
            "response_text": "A test image showing example content",
            "model": "test-model",
            "timestamp": "2024-01-01T00:00:00Z"
        }
        mock_post.return_value = mock_infer_response
        
        client = LLMClient(url="llama-vision", port=5000, enabled=True)
        result = client.generate_alt_text(mock_image_file)
        
        assert result == "A test image showing example content"
        mock_post.assert_called_once()
        
        # Check request payload
        call_args = mock_post.call_args
        payload = call_args[1]['json']
        assert 'prompt' in payload
        assert 'image' in payload
        assert 'max_tokens' in payload
    
    @patch('requests.post')
    @patch('requests.get')
    def test_generate_alt_text_custom_prompt(self, mock_get, mock_post, mock_image_file):
        """Test alt text generation with custom prompt."""
        mock_health_response = Mock()
        mock_health_response.status_code = 200
        mock_health_response.json.return_value = {"status": "healthy", "model_loaded": True}
        mock_get.return_value = mock_health_response
        
        mock_infer_response = Mock()
        mock_infer_response.status_code = 200
        mock_infer_response.json.return_value = {
            "success": True,
            "response_text": "Custom description"
        }
        mock_post.return_value = mock_infer_response
        
        client = LLMClient(url="llama-vision", port=5000, enabled=True)
        result = client.generate_alt_text(
            mock_image_file,
            prompt="What's in this image?",
            max_tokens=100
        )
        
        assert result == "Custom description"
        payload = mock_post.call_args[1]['json']
        assert payload['prompt'] == "What's in this image?"
        assert payload['max_tokens'] == 100
    
    def test_generate_alt_text_disabled(self, mock_image_file):
        """Test that disabled client returns None."""
        client = LLMClient(url="", enabled=False)
        result = client.generate_alt_text(mock_image_file)
        assert result is None
    
    def test_generate_alt_text_nonexistent_file(self):
        """Test with non-existent image file."""
        client = LLMClient(url="llama-vision", port=5000, enabled=True)
        result = client.generate_alt_text("/nonexistent/file.jpg")
        assert result is None
    
    @patch('requests.post')
    @patch('requests.get')
    def test_generate_alt_text_unhealthy_service(self, mock_get, mock_post, mock_image_file):
        """Test when service is unhealthy."""
        mock_health_response = Mock()
        mock_health_response.status_code = 503
        mock_get.return_value = mock_health_response
        
        client = LLMClient(url="llama-vision", port=5000, enabled=True)
        result = client.generate_alt_text(mock_image_file)
        
        assert result is None
        mock_post.assert_not_called()
    
    @patch('requests.post')
    @patch('requests.get')
    def test_generate_alt_text_inference_error(self, mock_get, mock_post, mock_image_file):
        """Test when inference returns an error."""
        mock_health_response = Mock()
        mock_health_response.status_code = 200
        mock_health_response.json.return_value = {"status": "healthy", "model_loaded": True}
        mock_get.return_value = mock_health_response
        
        mock_infer_response = Mock()
        mock_infer_response.status_code = 200
        mock_infer_response.json.return_value = {
            "success": False,
            "error": "Model error"
        }
        mock_post.return_value = mock_infer_response
        
        client = LLMClient(url="llama-vision", port=5000, enabled=True)
        result = client.generate_alt_text(mock_image_file)
        
        assert result is None
    
    @patch('requests.post')
    @patch('requests.get')
    def test_generate_alt_text_timeout(self, mock_get, mock_post, mock_image_file):
        """Test when request times out."""
        mock_health_response = Mock()
        mock_health_response.status_code = 200
        mock_health_response.json.return_value = {"status": "healthy", "model_loaded": True}
        mock_get.return_value = mock_health_response
        
        import requests
        mock_post.side_effect = requests.Timeout("Request timed out")
        
        client = LLMClient(url="llama-vision", port=5000, enabled=True)
        result = client.generate_alt_text(mock_image_file)
        
        assert result is None
    
    @patch('requests.post')
    @patch('requests.get')
    def test_generate_alt_text_empty_response(self, mock_get, mock_post, mock_image_file):
        """Test when model returns empty response."""
        mock_health_response = Mock()
        mock_health_response.status_code = 200
        mock_health_response.json.return_value = {"status": "healthy", "model_loaded": True}
        mock_get.return_value = mock_health_response
        
        mock_infer_response = Mock()
        mock_infer_response.status_code = 200
        mock_infer_response.json.return_value = {
            "success": True,
            "response_text": ""
        }
        mock_post.return_value = mock_infer_response
        
        client = LLMClient(url="llama-vision", port=5000, enabled=True)
        result = client.generate_alt_text(mock_image_file)
        
        assert result is None
