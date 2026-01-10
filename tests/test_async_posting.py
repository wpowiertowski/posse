"""
Unit Tests for Async Posting Functionality.

This test module validates that the process_events function correctly:
- Extracts alt text from HTML img tags

Test Coverage:
    - Alt text extraction from HTML

Running Tests:
    $ poetry run pytest tests/test_async_posting.py -v
"""

import logging
import pytest
import time


@pytest.fixture
def valid_post_with_alt_text():
    """Create a valid Ghost post with images that have alt text."""
    return {
        "post": {
            "current": {
                "id": "test123",
                "uuid": "uuid-test-123",
                "title": "Test Post with Alt Text",
                "slug": "test-post",
                "status": "published",
                "url": "https://example.com/test-post",
                "custom_excerpt": "This is a test post with images that have alt text",
                "created_at": "2024-01-01T00:00:00.000Z",
                "updated_at": "2024-01-01T00:00:00.000Z",
                "html": '<p>Some content</p><img src="https://example.com/img1.jpg" alt="First image description"><p>More content</p><img src="https://example.com/img2.jpg" alt="Second image description">',
                "feature_image": "https://example.com/feature.jpg",
                "feature_image_alt": "Feature image alt text",
                "tags": [
                    {"name": "Test", "slug": "test"}
                ]
            }
        }
    }


def test_alt_text_extraction(valid_post_with_alt_text, caplog):
    """Test that alt text is correctly extracted from img tags.
    
    Verifies:
    1. Alt text is extracted from HTML img tags
    2. feature_image_alt is extracted
    3. Alt text is logged correctly
    
    Note: This test uses the global event processor started by conftest.py
    """
    from posse.posse import events_queue
    
    # Set up logging capture at DEBUG level
    caplog.set_level(logging.DEBUG)
    
    # Put the event in the queue (global processor will handle it)
    events_queue.put(valid_post_with_alt_text)
    
    # Give the processor time to handle the event
    time.sleep(0.5)
    
    # Verify alt text was logged
    log_text = "\n".join([record.message for record in caplog.records])
    
    assert "First image description" in log_text, "Should log first image alt text"
    assert "Second image description" in log_text, "Should log second image alt text"
    assert "Feature image alt text" in log_text, "Should log feature image alt text"
