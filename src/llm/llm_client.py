"""
LLM Client for Vision-based Alt Text Generation.

This module provides a client for interacting with vision-capable LLM services
(like Llama 3.2 Vision) to generate descriptive alt text for images.
"""

import logging
import base64
import requests
from typing import Optional, Dict, Any
from pathlib import Path

logger = logging.getLogger(__name__)


class LLMClient:
    """Client for interacting with vision-capable LLM services.
    
    This client sends images to an LLM service and receives descriptive
    text that can be used as alt text for accessibility.
    
    Attributes:
        base_url: Base URL of the LLM service (e.g., http://llama-vision:5000)
        enabled: Whether the LLM service is enabled
        timeout: Request timeout in seconds
    """
    
    DEFAULT_TIMEOUT = 60  # seconds - vision inference can be slow
    DEFAULT_PROMPT = "Describe this image concisely in one sentence for use as alt text for accessibility."
    DEFAULT_MAX_TOKENS = 256
    DEFAULT_TEMPERATURE = 0.7
    DEFAULT_TOP_P = 0.95
    
    def __init__(
        self,
        url: str,
        port: int = 5000,
        enabled: bool = True,
        timeout: Optional[int] = None
    ):
        """Initialize LLM client.
        
        Args:
            url: URL or hostname of the LLM service (without port)
            port: Port number for the LLM service (default: 5000)
            enabled: Whether LLM processing is enabled (default: True)
            timeout: Request timeout in seconds (default: 60)
        """
        self.enabled = enabled and bool(url)
        
        if not self.enabled:
            logger.info("LLM client disabled")
            self.base_url = None
            self.timeout = None
            return
        
        # Construct base URL
        # Remove any trailing slashes and protocol if present in url
        url = url.rstrip('/')
        if '://' in url:
            self.base_url = f"{url}:{port}"
        else:
            self.base_url = f"http://{url}:{port}"
        
        self.timeout = timeout or self.DEFAULT_TIMEOUT
        
        logger.info(f"LLM client initialized for {self.base_url} (timeout: {self.timeout}s)")
    
    def _encode_image_to_base64(self, image_path: str) -> Optional[str]:
        """Encode an image file to base64.
        
        Args:
            image_path: Path to the image file
            
        Returns:
            Base64-encoded image string, or None if encoding fails
        """
        try:
            with open(image_path, 'rb') as image_file:
                image_data = image_file.read()
                base64_encoded = base64.b64encode(image_data).decode('utf-8')
                return base64_encoded
        except Exception as e:
            logger.error(f"Failed to encode image {image_path}: {e}")
            return None
    
    def _check_health(self) -> bool:
        """Check if the LLM service is healthy and ready.
        
        Returns:
            True if service is healthy, False otherwise
        """
        if not self.enabled:
            return False
        
        try:
            health_url = f"{self.base_url}/health"
            response = requests.get(health_url, timeout=5)  # Short timeout for health check
            
            if response.status_code == 200:
                data = response.json()
                is_healthy = data.get('status') == 'healthy' and data.get('model_loaded', False)
                if is_healthy:
                    logger.debug(f"LLM service healthy: {data.get('model_name', 'unknown model')}")
                else:
                    logger.warning(f"LLM service unhealthy: {data}")
                return is_healthy
            else:
                logger.warning(f"LLM health check failed with status {response.status_code}")
                return False
        except Exception as e:
            logger.warning(f"LLM health check failed: {e}")
            return False
    
    def generate_alt_text(
        self,
        image_path: str,
        prompt: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        top_p: Optional[float] = None
    ) -> Optional[str]:
        """Generate alt text for an image using the LLM service.
        
        Args:
            image_path: Path to the image file
            prompt: Custom prompt for the LLM (uses default if None)
            max_tokens: Maximum tokens to generate (uses default if None)
            temperature: Sampling temperature (uses default if None)
            top_p: Nucleus sampling parameter (uses default if None)
            
        Returns:
            Generated alt text string, or None if generation fails
        """
        if not self.enabled:
            logger.debug("LLM client disabled, skipping alt text generation")
            return None
        
        # Check if image file exists
        if not Path(image_path).exists():
            logger.error(f"Image file not found: {image_path}")
            return None
        
        try:
            # Check health first (with caching to avoid excessive checks)
            if not self._check_health():
                logger.warning("LLM service not healthy, skipping alt text generation")
                return None
            
            # Encode image to base64
            base64_image = self._encode_image_to_base64(image_path)
            if not base64_image:
                return None
            
            # Prepare request payload
            payload = {
                "prompt": prompt or self.DEFAULT_PROMPT,
                "image": base64_image,
                "max_tokens": max_tokens or self.DEFAULT_MAX_TOKENS,
                "temperature": temperature or self.DEFAULT_TEMPERATURE,
                "top_p": top_p or self.DEFAULT_TOP_P
            }
            
            # Make inference request
            infer_url = f"{self.base_url}/infer"
            logger.debug(f"Sending inference request to {infer_url}")
            
            response = requests.post(
                infer_url,
                json=payload,
                timeout=self.timeout
            )
            
            # Check response
            if response.status_code != 200:
                logger.error(f"LLM inference failed with status {response.status_code}: {response.text}")
                return None
            
            # Parse response
            data = response.json()
            
            if not data.get('success', False):
                error_msg = data.get('error', 'Unknown error')
                logger.error(f"LLM inference returned error: {error_msg}")
                return None
            
            # Extract generated text
            alt_text = data.get('response_text', '').strip()
            
            if not alt_text:
                logger.warning("LLM returned empty response")
                return None
            
            logger.info(f"Generated alt text: {alt_text[:100]}...")
            return alt_text
            
        except requests.Timeout:
            logger.error(f"LLM request timed out after {self.timeout}s")
            return None
        except Exception as e:
            logger.error(f"Failed to generate alt text: {e}", exc_info=True)
            return None
    
    @classmethod
    def from_config(cls, config: Dict[str, Any]) -> "LLMClient":
        """Create LLM client from configuration dictionary.
        
        Configuration Format:
            llm:
              enabled: true
              url: "http://llama-vision"  # or just "llama-vision"
              port: 5000
              timeout: 60  # optional
        
        Args:
            config: Configuration dictionary from load_config()
            
        Returns:
            LLMClient instance configured from config
            
        Example:
            >>> from config import load_config
            >>> config = load_config()
            >>> llm_client = LLMClient.from_config(config)
            >>> if llm_client.enabled:
            ...     alt_text = llm_client.generate_alt_text("/path/to/image.jpg")
        """
        llm_config = config.get("llm", {})
        
        enabled = llm_config.get("enabled", False)
        url = llm_config.get("url", "")
        port = llm_config.get("port", 5000)
        timeout = llm_config.get("timeout")
        
        return cls(
            url=url,
            port=port,
            enabled=enabled,
            timeout=timeout
        )
