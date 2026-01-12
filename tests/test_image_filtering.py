"""
Unit Tests for Image Filtering.

This test module validates that external images are properly filtered out
and only local images (from the Ghost server domain) are extracted.

Test Coverage:
    - Local images are included
    - External images are filtered out
    - Mixed local and external images
    - Edge cases (no domain, invalid URLs, etc.)

Running Tests:
    $ poetry run pytest tests/test_image_filtering.py -v
"""

import json
import logging
from pathlib import Path

from posse.posse import _extract_post_data, _get_domain_from_url, _is_local_image


def test_get_domain_from_url():
    """Test domain extraction from URLs."""
    # Standard HTTPS URLs
    assert _get_domain_from_url("https://example.com/path") == "example.com"
    assert _get_domain_from_url("https://blog.example.com/post") == "blog.example.com"
    assert _get_domain_from_url("https://example.com:8080/path") == "example.com:8080"
    
    # HTTP URLs
    assert _get_domain_from_url("http://example.com/path") == "example.com"
    
    # URLs without path
    assert _get_domain_from_url("https://example.com") == "example.com"
    assert _get_domain_from_url("https://example.com/") == "example.com"
    
    # Invalid/edge cases
    assert _get_domain_from_url("") is None
    assert _get_domain_from_url(None) is None
    assert _get_domain_from_url("not-a-url") is None


def test_is_local_image():
    """Test local image detection."""
    # Local images (same domain)
    assert _is_local_image(
        "https://example.com/content/images/photo.jpg",
        "example.com"
    ) is True
    
    assert _is_local_image(
        "https://example.com/images/photo.jpg",
        "example.com"
    ) is True
    
    # External images (different domain)
    assert _is_local_image(
        "https://external.com/photo.jpg",
        "example.com"
    ) is False
    
    assert _is_local_image(
        "https://wikipedia.org/image.png",
        "example.com"
    ) is False
    
    # Subdomain mismatch
    assert _is_local_image(
        "https://cdn.example.com/photo.jpg",
        "example.com"
    ) is False
    
    # Port number considerations
    assert _is_local_image(
        "https://example.com:8080/photo.jpg",
        "example.com:8080"
    ) is True
    
    assert _is_local_image(
        "https://example.com:8080/photo.jpg",
        "example.com"
    ) is False
    
    # Edge cases - backward compatibility
    assert _is_local_image(
        "https://example.com/photo.jpg",
        None
    ) is True  # No domain filter, include all
    
    assert _is_local_image(
        "not-a-valid-url",
        "example.com"
    ) is False  # Invalid image URL


def test_extract_post_data_filters_external_images():
    """Test that external images are filtered out during post extraction."""
    # Create a post with mixed local and external images
    post = {
        "id": "test123",
        "title": "Test Post",
        "url": "https://myblog.com/test-post",
        "custom_excerpt": "This is a test",
        "tags": [],
        "feature_image": "https://myblog.com/content/images/feature.jpg",
        "html": """
            <img src="https://myblog.com/content/images/local1.jpg" alt="Local image 1">
            <img src="https://wikipedia.org/external.jpg" alt="External image">
            <img src="https://myblog.com/content/images/local2.jpg" alt="Local image 2">
            <img src="https://cdn.example.com/external2.jpg" alt="Another external">
        """
    }
    
    title, url, excerpt, images, media_descriptions, tags = _extract_post_data(post)
    
    # Should extract only local images (feature + 2 local from HTML)
    assert len(images) == 3
    assert "https://myblog.com/content/images/feature.jpg" in images
    assert "https://myblog.com/content/images/local1.jpg" in images
    assert "https://myblog.com/content/images/local2.jpg" in images
    
    # External images should not be included
    assert "https://wikipedia.org/external.jpg" not in images
    assert "https://cdn.example.com/external2.jpg" not in images


def test_extract_post_data_all_local_images():
    """Test extraction when all images are local."""
    post = {
        "id": "test123",
        "title": "Test Post",
        "url": "https://myblog.com/test-post",
        "custom_excerpt": "This is a test",
        "tags": [],
        "feature_image": "https://myblog.com/content/images/feature.jpg",
        "html": """
            <img src="https://myblog.com/content/images/image1.jpg" alt="Image 1">
            <img src="https://myblog.com/content/images/image2.jpg" alt="Image 2">
        """
    }
    
    title, url, excerpt, images, media_descriptions, tags = _extract_post_data(post)
    
    # Should extract all images
    assert len(images) == 3
    assert all("myblog.com" in img for img in images)


def test_extract_post_data_all_external_images():
    """Test extraction when all images are external."""
    post = {
        "id": "test123",
        "title": "Test Post",
        "url": "https://myblog.com/test-post",
        "custom_excerpt": "This is a test",
        "tags": [],
        "feature_image": "https://wikipedia.org/feature.jpg",
        "html": """
            <img src="https://external1.com/image1.jpg" alt="External 1">
            <img src="https://external2.com/image2.jpg" alt="External 2">
        """
    }
    
    title, url, excerpt, images, media_descriptions, tags = _extract_post_data(post)
    
    # Should extract no images
    assert len(images) == 0


def test_extract_post_data_no_post_url():
    """Test extraction when post URL is missing (backward compatibility)."""
    post = {
        "id": "test123",
        "title": "Test Post",
        # No url field
        "custom_excerpt": "This is a test",
        "tags": [],
        "feature_image": "https://example.com/feature.jpg",
        "html": """
            <img src="https://external.com/image.jpg" alt="External">
        """
    }
    
    title, url, excerpt, images, media_descriptions, tags = _extract_post_data(post)
    
    # Without post URL, all images should be included (backward compatible)
    assert len(images) == 2
    assert "https://example.com/feature.jpg" in images
    assert "https://external.com/image.jpg" in images


def test_extract_post_data_with_real_fixture():
    """Test with the actual Ghost post fixture to ensure it still works."""
    fixture_path = Path(__file__).parent / "fixtures" / "valid_ghost_post.json"
    with open(fixture_path, "r") as f:
        data = json.load(f)
    
    post = data["post"]["current"]
    
    title, url, excerpt, images, media_descriptions, tags = _extract_post_data(post)
    
    # All images in the fixture are from behindtheviewfinder.com, so all should be included
    assert len(images) == 5
    assert all("behindtheviewfinder.com" in img for img in images)


def test_extract_post_data_preserves_alt_text():
    """Test that alt text is preserved for filtered images."""
    post = {
        "id": "test123",
        "title": "Test Post",
        "url": "https://myblog.com/test-post",
        "custom_excerpt": "This is a test",
        "tags": [],
        "html": """
            <img src="https://myblog.com/local.jpg" alt="Local alt text">
            <img src="https://external.com/external.jpg" alt="External alt text">
        """
    }
    
    title, url, excerpt, images, media_descriptions, tags = _extract_post_data(post)
    
    # Should have one image with its alt text
    assert len(images) == 1
    assert len(media_descriptions) == 1
    assert images[0] == "https://myblog.com/local.jpg"
    assert media_descriptions[0] == "Local alt text"
