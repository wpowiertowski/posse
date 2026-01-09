"""
Unit Tests for POSSE Core Module.

This test module validates the POSSE (Publish Own Site, Syndicate Elsewhere)
core module's entry point functionality.

The posse module serves as the main orchestration layer that embeds Gunicorn
to run the Ghost webhook receiver. The main() function starts a production-ready
WSGI server that accepts Ghost post notifications.

Test Coverage:
    - Module imports work correctly
    - main function is callable (actual execution tested via integration/manual tests)
    - Events queue is available and functional
    
Note: The main() function starts a blocking Gunicorn server, so unit testing
      its execution is not practical. Integration testing is done via:
      - Manual testing: poetry run posse
      - Docker testing: docker compose up app
      - End-to-end testing: curl POST to /webhook/ghost endpoint
      
      The webhook receiver itself is thoroughly tested in test_ghost.py with
      tests covering valid posts, invalid payloads, schema validation, etc.

Future tests will cover:
    - Post processing and filtering logic (when implemented)
    - Social media syndication (Mastodon, Bluesky)
    - Error handling and retry mechanisms
    - Configuration management

Running Tests:
    $ poetry run pytest tests/test_posse.py -v
    $ docker compose run --rm test poetry run pytest tests/test_posse.py
"""

import pytest
from queue import Queue

# Import functions being tested
from posse.posse import main, events_queue


def test_module_imports():
    """Test that all required imports work correctly.
    
    Verifies that:
    1. The posse module can be imported
    2. The main function is accessible and callable
    3. Dependencies (ghost.ghost, gunicorn) are available
    
    This ensures the module structure is correct and dependencies
    are properly configured in pyproject.toml.
    
    Note: This test doesn"t execute main() because it"s a blocking
          call that starts a Gunicorn server. The actual webhook
          functionality is tested via:
          - test_ghost.py (tests for webhook receiver)
          - Integration tests (docker compose up + curl)
    """
    # These imports should not raise any exceptions
    from posse import main
    
    # Verify main is callable
    assert callable(main), "main should be callable"
    
    # Verify main has proper docstring
    assert main.__doc__ is not None, "main should have docstring"
    assert "Gunicorn" in main.__doc__, "main docstring should mention Gunicorn"
    
    # Verify required dependencies can be imported (used by main())
    try:
        from gunicorn.app.base import BaseApplication
        from ghost.ghost import app
    except ImportError as e:
        pytest.fail(f"Required dependency not available: {e}")


def test_events_queue_exists():
    """Test that events_queue is available and is a Queue instance.
    
    The events_queue is the core data structure for passing validated Ghost
    posts from the webhook receiver to the Mastodon and Bluesky agents.
    
    Verifies:
    1. events_queue can be imported from posse.posse
    2. events_queue is an instance of Queue
    3. events_queue is ready to accept items
    """
    # Verify events_queue can be imported
    from posse.posse import events_queue
    
    # Verify it's a Queue instance
    assert isinstance(events_queue, Queue), "events_queue should be a Queue instance"
    
    # Verify queue is functional (can accept items)
    # We test this by putting an item and immediately getting it back
    test_item = {"test": "data"}
    events_queue.put(test_item)
    retrieved_item = events_queue.get(timeout=1)
    assert retrieved_item == test_item, "Queue should preserve items"


def test_events_queue_is_thread_safe():
    """Test that events_queue is thread-safe (Queue class property).
    
    The Queue class from Python's queue module is inherently thread-safe,
    which is important because the webhook receiver (Flask) may handle
    multiple requests concurrently, and the Mastodon/Bluesky agents will
    consume from the queue in separate threads.
    
    This test verifies that the events_queue is an instance of the
    thread-safe Queue class, not a simple list or other non-thread-safe
    data structure.
    """
    # Verify events_queue is a Queue (which is thread-safe by design)
    assert isinstance(events_queue, Queue), \
        "events_queue must be a Queue for thread-safety"
    
    # Verify it has Queue's thread-safe methods
    assert hasattr(events_queue, "put"), "Queue should have put method"
    assert hasattr(events_queue, "get"), "Queue should have get method"
    assert hasattr(events_queue, "empty"), "Queue should have empty method"
    assert hasattr(events_queue, "qsize"), "Queue should have qsize method"


def test_process_events_with_clients():
    """Test that process_events accepts client parameters.
    
    This verifies that the process_events function signature has been updated
    to accept mastodon_clients and bluesky_clients parameters, which is
    required for the event processor to syndicate posts to social platforms.
    """
    from posse.posse import process_events
    import inspect
    
    # Verify process_events signature includes client parameters
    sig = inspect.signature(process_events)
    params = list(sig.parameters.keys())
    
    assert "mastodon_clients" in params, "process_events should accept mastodon_clients parameter"
    assert "bluesky_clients" in params, "process_events should accept bluesky_clients parameter"
    
    # Verify function is still callable
    assert callable(process_events), "process_events should be callable"


