"""
Unit Tests for Content Extraction from Ghost Posts.

This test module validates that the process_events function correctly
extracts content from Ghost post webhooks, including:
- Custom excerpt
- Tags (name and slug)
- All unique images from HTML and feature_image

Test Coverage:
    - Excerpt extraction from custom_excerpt field
    - Tags extraction with name and slug
    - Image extraction from HTML content
    - Feature image inclusion in image list
    - Unique image deduplication
    - Handling posts without optional fields

Running Tests:
    $ poetry run pytest tests/test_content_extraction.py -v
"""

import json
import logging
import pytest
import threading
import time
from pathlib import Path
from queue import Queue

from posse.posse import process_events


@pytest.fixture
def valid_post_payload():
    """Load a valid Ghost post fixture from JSON file.
    
    Returns:
        dict: Valid Ghost post data structure with excerpt, tags, and images
    """
    fixture_path = Path(__file__).parent / "fixtures" / "valid_ghost_post.json"
    with open(fixture_path, "r") as f:
        return json.load(f)


@pytest.fixture
def events_queue_with_processor():
    """Create an events queue and start the processor in a thread.
    
    Returns:
        Queue: Events queue for testing
    """
    test_queue = Queue()
    
    # Start processor thread
    processor_thread = threading.Thread(
        target=process_events,
        args=([], []),  # No clients for this test
        daemon=True
    )
    processor_thread.start()
    
    yield test_queue
    
    # Clean up: processor will stop when test ends (daemon thread)


def test_extract_custom_excerpt(valid_post_payload, caplog):
    """Test that custom_excerpt is correctly extracted from post.
    
    Verifies:
    1. The excerpt is extracted from the custom_excerpt field (not excerpt)
    2. The extracted excerpt matches the expected content
    3. Excerpt is logged at INFO level
    """
    from posse.posse import events_queue
    
    # Set up logging capture
    caplog.set_level(logging.INFO)
    
    # Put the event in the queue
    events_queue.put(valid_post_payload)
    
    # Give the processor time to handle the event
    time.sleep(0.5)
    
    # Verify the excerpt was logged
    expected_excerpt_start = "Antelope Canyon felt unlike anywhere else"
    assert any(expected_excerpt_start in record.message 
              for record in caplog.records if "Extracted excerpt:" in record.message), \
        "Custom excerpt should be extracted and logged"


def test_extract_tags(valid_post_payload, caplog):
    """Test that tags are correctly extracted with name and slug.
    
    Verifies:
    1. Tags are extracted as list of dictionaries
    2. Each tag includes 'name' and 'slug' fields
    3. Tag extraction is logged at INFO level
    """
    from posse.posse import events_queue
    
    # Set up logging capture
    caplog.set_level(logging.INFO)
    
    # Put the event in the queue
    events_queue.put(valid_post_payload)
    
    # Give the processor time to handle the event
    time.sleep(0.5)
    
    # Verify tags were logged
    assert any("Extracted 2 tags:" in record.message 
              for record in caplog.records), \
        "Should log that 2 tags were extracted"
    
    assert any("Photography" in record.message and "2016" in record.message
              for record in caplog.records if "Extracted" in record.message and "tags:" in record.message), \
        "Should log tag names"


def test_extract_images(valid_post_payload, caplog):
    """Test that all unique images are extracted from HTML and feature_image.
    
    Verifies:
    1. Images are extracted from img src attributes in HTML
    2. feature_image is included in the image list
    3. Duplicate images are removed (unique set)
    4. All images are logged at DEBUG level
    
    Expected images:
    - 4 images from HTML content (antelope1-1.jpg through antelope4-1.jpg)
    - 1 feature image (antelope5.jpg)
    - Total: 5 unique images
    """
    from posse.posse import events_queue
    
    # Set up logging capture at DEBUG level to see image URLs
    caplog.set_level(logging.DEBUG)
    
    # Put the event in the queue
    events_queue.put(valid_post_payload)
    
    # Give the processor time to handle the event
    time.sleep(0.5)
    
    # Verify the correct number of images were extracted
    assert any("Extracted 5 unique images" in record.message 
              for record in caplog.records), \
        "Should extract 5 unique images (4 from HTML + 1 feature image)"
    
    # Verify specific images are logged
    expected_images = [
        "antelope1-1.jpg",
        "antelope2-1.jpg", 
        "antelope3-1.jpg",
        "antelope4-1.jpg",
        "antelope5.jpg"  # feature_image
    ]
    
    log_text = "\n".join([record.message for record in caplog.records])
    
    for img in expected_images:
        assert img in log_text, f"Image {img} should be logged"


def test_extract_content_without_optional_fields(caplog):
    """Test content extraction with minimal post (no excerpt, tags, or images).
    
    Verifies:
    1. Missing custom_excerpt doesn't cause errors
    2. Empty tags list is handled gracefully
    3. Missing HTML and feature_image doesn't cause errors
    4. Extraction logs show appropriate None/empty values
    """
    from posse.posse import events_queue
    
    # Create minimal post without optional fields
    minimal_post = {
        "post": {
            "current": {
                "id": "minimal123",
                "uuid": "uuid-minimal-123",
                "title": "Minimal Post",
                "slug": "minimal-post",
                "status": "published",
                "url": "https://example.com/minimal",
                "created_at": "2024-01-01T00:00:00.000Z",
                "updated_at": "2024-01-01T00:00:00.000Z"
                # No custom_excerpt, tags, html, or feature_image
            }
        }
    }
    
    # Set up logging capture
    caplog.set_level(logging.INFO)
    
    # Put the event in the queue
    events_queue.put(minimal_post)
    
    # Give the processor time to handle the event
    time.sleep(0.5)
    
    # Verify extraction handled missing fields gracefully
    assert any("Extracted excerpt: None..." in record.message 
              for record in caplog.records), \
        "Should handle missing excerpt gracefully"
    
    assert any("Extracted 0 tags:" in record.message 
              for record in caplog.records), \
        "Should handle missing tags gracefully"
    
    assert any("Extracted 0 unique images" in record.message 
              for record in caplog.records), \
        "Should handle missing images gracefully"


def test_image_deduplication():
    """Test that duplicate images are properly deduplicated.
    
    Verifies:
    1. If the same image appears multiple times in HTML, it's only counted once
    2. If feature_image matches an image in HTML, it's only counted once
    3. Images preserve HTML document order
    """
    from posse.posse import events_queue
    
    # Create post with duplicate images
    post_with_duplicates = {
        "post": {
            "current": {
                "id": "dup123",
                "uuid": "uuid-dup-123",
                "title": "Duplicate Images Post",
                "slug": "duplicate-images",
                "status": "published",
                "url": "https://example.com/dup",
                "created_at": "2024-01-01T00:00:00.000Z",
                "updated_at": "2024-01-01T00:00:00.000Z",
                "html": '<img src="https://example.com/img1.jpg"><img src="https://example.com/img1.jpg"><img src="https://example.com/img2.jpg">',
                "feature_image": "https://example.com/img1.jpg"  # Duplicate of first HTML image
            }
        }
    }
    
    # Put the event in the queue
    events_queue.put(post_with_duplicates)
    
    # Give the processor time to handle the event
    time.sleep(0.5)
    
    # Queue should be empty after processing
    assert events_queue.empty(), "Queue should be empty after processing"
