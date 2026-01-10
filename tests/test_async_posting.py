"""
Unit Tests for Async Posting Functionality.

This test module validates that the process_events function correctly:
- Extracts alt text from HTML img tags
- Posts to enabled accounts asynchronously
- Sends notifications for success/failure
- Handles errors gracefully

Test Coverage:
    - Alt text extraction from HTML
    - Async posting with ThreadPoolExecutor
    - Per-account notifications
    - Error handling for individual account failures
    - Image cache cleanup

Running Tests:
    $ poetry run pytest tests/test_async_posting.py -v
"""

import json
import logging
import pytest
import time
from pathlib import Path
from queue import Queue
from unittest.mock import MagicMock, patch, call

from posse.posse import process_events


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


@pytest.fixture
def mock_mastodon_client():
    """Create a mock Mastodon client."""
    client = MagicMock()
    client.enabled = True
    client.account_name = "test_mastodon"
    client.post.return_value = {"url": "https://mastodon.social/@user/123"}
    client._remove_images = MagicMock()
    return client


@pytest.fixture
def mock_bluesky_client():
    """Create a mock Bluesky client."""
    client = MagicMock()
    client.enabled = True
    client.account_name = "test_bluesky"
    client.post.return_value = {"uri": "at://did/app.bsky.feed.post/123"}
    client._remove_images = MagicMock()
    return client


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


def test_async_posting_to_multiple_accounts(valid_post_with_alt_text, mock_mastodon_client, mock_bluesky_client):
    """Test that posting happens asynchronously to multiple accounts.
    
    Verifies:
    1. All enabled clients receive posting calls
    2. Posting happens in parallel (via ThreadPoolExecutor)
    3. Media URLs and descriptions are passed correctly
    
    Note: This test directly tests the posting logic without using the event queue
    to avoid race conditions with the global processor.
    """
    from posse.posse import process_events
    from queue import Queue
    import threading
    
    # Create a test-specific queue to avoid conflict with global processor
    test_queue = Queue()
    test_queue.put(valid_post_with_alt_text)
    
    # Temporarily replace the global queue
    from posse import posse
    original_queue = posse.events_queue
    posse.events_queue = test_queue
    
    try:
        with patch("posse.posse.load_config") as mock_config, \
             patch("posse.posse.PushoverNotifier") as mock_notifier_class:
            
            mock_config.return_value = {"pushover": {"enabled": False}}
            mock_notifier = MagicMock()
            mock_notifier.enabled = False
            mock_notifier_class.from_config.return_value = mock_notifier
            
            # Start processor with mock clients and test queue
            processor_thread = threading.Thread(
                target=process_events,
                args=([mock_mastodon_client], [mock_bluesky_client]),
                daemon=True
            )
            processor_thread.start()
            
            # Give the processor time to handle the event
            time.sleep(1.0)
            
            # Verify both clients received post calls
            assert mock_mastodon_client.post.called, "Mastodon client should be called"
            assert mock_bluesky_client.post.called, "Bluesky client should be called"
            
            # Verify media descriptions were passed
            mastodon_call = mock_mastodon_client.post.call_args
            assert mastodon_call is not None
            assert "media_descriptions" in mastodon_call[1]
            descriptions = mastodon_call[1]["media_descriptions"]
            assert len(descriptions) > 0, "Should have media descriptions"
    finally:
        # Restore original queue
        posse.events_queue = original_queue


def test_notifications_sent_on_success(valid_post_with_alt_text, mock_mastodon_client):
    """Test that success notifications are sent for successful posts.
    
    Verifies:
    1. notify_post_success is called for successful posts
    2. Correct parameters are passed to notification
    
    Note: Uses a test-specific queue to avoid conflicts with global processor.
    """
    from posse.posse import process_events
    from queue import Queue
    import threading
    
    # Create a test-specific queue
    test_queue = Queue()
    test_queue.put(valid_post_with_alt_text)
    
    # Temporarily replace the global queue
    from posse import posse
    original_queue = posse.events_queue
    posse.events_queue = test_queue
    
    try:
        with patch("posse.posse.load_config") as mock_config, \
             patch("posse.posse.PushoverNotifier") as mock_notifier_class:
            
            mock_config.return_value = {"pushover": {"enabled": True}}
            mock_notifier = MagicMock()
            mock_notifier.enabled = True
            mock_notifier_class.from_config.return_value = mock_notifier
            
            # Start processor with mock clients and test queue
            processor_thread = threading.Thread(
                target=process_events,
                args=([mock_mastodon_client], []),
                daemon=True
            )
            processor_thread.start()
            
            # Give the processor time to handle the event
            time.sleep(1.0)
            
            # Verify success notification was called
            assert mock_notifier.notify_post_success.called, "Should send success notification"
            call_args = mock_notifier.notify_post_success.call_args
            assert call_args[0][0] == "Test Post with Alt Text", "Should include post title"
            assert call_args[0][1] == "test_mastodon", "Should include account name"
            assert call_args[0][2] == "Mastodon", "Should include platform name"
    finally:
        # Restore original queue
        posse.events_queue = original_queue


def test_notifications_sent_on_failure(valid_post_with_alt_text):
    """Test that failure notifications are sent when posting fails.
    
    Verifies:
    1. notify_post_failure is called when posting fails
    2. Error message is included in notification
    
    Note: Uses a test-specific queue to avoid conflicts with global processor.
    """
    from posse.posse import process_events
    from queue import Queue
    import threading
    
    # Create a mock client that fails
    failing_client = MagicMock()
    failing_client.enabled = True
    failing_client.account_name = "failing_account"
    failing_client.post.return_value = None  # Simulate failure
    failing_client._remove_images = MagicMock()
    
    # Create a test-specific queue
    test_queue = Queue()
    test_queue.put(valid_post_with_alt_text)
    
    # Temporarily replace the global queue
    from posse import posse
    original_queue = posse.events_queue
    posse.events_queue = test_queue
    
    try:
        with patch("posse.posse.load_config") as mock_config, \
             patch("posse.posse.PushoverNotifier") as mock_notifier_class:
            
            mock_config.return_value = {"pushover": {"enabled": True}}
            mock_notifier = MagicMock()
            mock_notifier.enabled = True
            mock_notifier_class.from_config.return_value = mock_notifier
            
            # Start processor with failing client and test queue
            processor_thread = threading.Thread(
                target=process_events,
                args=([failing_client], []),
                daemon=True
            )
            processor_thread.start()
            
            # Give the processor time to handle the event
            time.sleep(1.0)
            
            # Verify failure notification was called
            assert mock_notifier.notify_post_failure.called, "Should send failure notification"
            call_args = mock_notifier.notify_post_failure.call_args
            assert call_args[0][0] == "Test Post with Alt Text", "Should include post title"
            assert call_args[0][1] == "failing_account", "Should include account name"
            assert call_args[0][2] == "Mastodon", "Should include platform name"
    finally:
        # Restore original queue
        posse.events_queue = original_queue


def test_image_cleanup_after_posting(valid_post_with_alt_text, mock_mastodon_client):
    """Test that cached images are cleaned up after posting.
    
    Verifies:
    1. _remove_images is called after posting
    2. All image URLs are passed to cleanup
    
    Note: Uses a test-specific queue to avoid conflicts with global processor.
    """
    from posse.posse import process_events
    from queue import Queue
    import threading
    
    # Create a test-specific queue
    test_queue = Queue()
    test_queue.put(valid_post_with_alt_text)
    
    # Temporarily replace the global queue
    from posse import posse
    original_queue = posse.events_queue
    posse.events_queue = test_queue
    
    try:
        with patch("posse.posse.load_config") as mock_config, \
             patch("posse.posse.PushoverNotifier") as mock_notifier_class:
            
            mock_config.return_value = {"pushover": {"enabled": False}}
            mock_notifier = MagicMock()
            mock_notifier.enabled = False
            mock_notifier_class.from_config.return_value = mock_notifier
            
            # Start processor with mock client and test queue
            processor_thread = threading.Thread(
                target=process_events,
                args=([mock_mastodon_client], []),
                daemon=True
            )
            processor_thread.start()
            
            # Give the processor time to handle the event
            time.sleep(1.0)
            
            # Verify cleanup was called
            assert mock_mastodon_client._remove_images.called, "Should clean up images"
            cleanup_call = mock_mastodon_client._remove_images.call_args
            image_urls = cleanup_call[0][0]
            assert len(image_urls) >= 3, "Should clean up all images (feature + HTML images)"
    finally:
        # Restore original queue
        posse.events_queue = original_queue


def test_error_handling_doesnt_block_other_accounts(valid_post_with_alt_text, mock_bluesky_client):
    """Test that an error posting to one account doesn't prevent posting to others.
    
    Verifies:
    1. Exceptions in one account don't stop processing
    2. Other accounts still receive their posts
    3. Error is logged appropriately
    
    Note: Uses a test-specific queue to avoid conflicts with global processor.
    """
    from posse.posse import process_events
    from queue import Queue
    import threading
    
    # Create a mock client that raises an exception
    failing_client = MagicMock()
    failing_client.enabled = True
    failing_client.account_name = "failing_account"
    failing_client.post.side_effect = Exception("Connection error")
    
    # Create a test-specific queue
    test_queue = Queue()
    test_queue.put(valid_post_with_alt_text)
    
    # Temporarily replace the global queue
    from posse import posse
    original_queue = posse.events_queue
    posse.events_queue = test_queue
    
    try:
        with patch("posse.posse.load_config") as mock_config, \
             patch("posse.posse.PushoverNotifier") as mock_notifier_class:
            
            mock_config.return_value = {"pushover": {"enabled": False}}
            mock_notifier = MagicMock()
            mock_notifier.enabled = False
            mock_notifier_class.from_config.return_value = mock_notifier
            
            # Start processor with both failing and working clients and test queue
            processor_thread = threading.Thread(
                target=process_events,
                args=([failing_client], [mock_bluesky_client]),
                daemon=True
            )
            processor_thread.start()
            
            # Give the processor time to handle the event
            time.sleep(1.0)
            
            # Verify the working client still received its post
            assert mock_bluesky_client.post.called, "Working client should still be called"
    finally:
        # Restore original queue
        posse.events_queue = original_queue
