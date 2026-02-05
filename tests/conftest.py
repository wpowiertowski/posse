"""
Pytest configuration and shared fixtures for all tests.

This module provides shared fixtures and configuration for the test suite,
including:
- Event processor thread management
- Queue cleanup between tests
- Discovery cooldown cache cleanup
- Common test utilities
"""

import pytest
import threading
import time


@pytest.fixture(scope="session", autouse=True)
def start_event_processor():
    """Start the event processor thread for the entire test session.

    This fixture automatically starts a daemon thread running process_events
    at the beginning of the test session. The thread will consume events from
    the module-level events_queue throughout all tests.

    The thread is a daemon so it will automatically terminate when the test
    session ends.
    """
    from posse.posse import process_events

    # Start processor thread with no clients (tests don't need actual posting)
    processor_thread = threading.Thread(
        target=process_events,
        args=([], []),  # Empty client lists
        daemon=True
    )
    processor_thread.start()

    # Give thread minimal time to start
    time.sleep(0.01)

    yield

    # Thread will be cleaned up automatically (daemon)


@pytest.fixture(autouse=True)
def clear_events_queue():
    """Clear the events queue before and after each test.

    This fixture ensures that tests don't interfere with each other by
    leaving items in the queue. It clears the queue before each test starts
    and after it completes.

    This is especially important for tests that put items in the queue but
    don't consume them all, or tests that check queue state.
    """
    from posse.posse import events_queue

    # Clear queue before test
    while not events_queue.empty():
        try:
            events_queue.get_nowait()
        except:
            break

    yield

    # Clear queue after test
    # Only wait if queue has items that need processing
    if not events_queue.empty():
        time.sleep(0.05)  # Minimal wait for queue processing

    while not events_queue.empty():
        try:
            events_queue.get_nowait()
        except:
            break


@pytest.fixture(autouse=True)
def clear_rate_limiting_caches():
    """Clear all rate limiting caches before each test.

    This fixture ensures that tests don't interfere with each other due to
    rate limiting caches. These caches are module-level in ghost.py
    and persist across test runs, so we need to clear them before each test.

    Clears:
    - Discovery cooldown cache (per-ID cooldown)
    - Global discovery timestamps (global rate limit)
    - Request rate cache (per-IP rate limit)
    """
    # Clear before test
    try:
        from ghost.ghost import clear_rate_limit_caches
        clear_rate_limit_caches()
    except Exception:
        # Module not available or other import issues - skip silently
        # Fallback to legacy behavior
        try:
            from ghost.ghost import _discovery_cooldown_cache
            _discovery_cooldown_cache.clear()
        except Exception:
            pass

    yield

    # Clear after test for good measure
    try:
        from ghost.ghost import clear_rate_limit_caches
        clear_rate_limit_caches()
    except Exception:
        try:
            from ghost.ghost import _discovery_cooldown_cache
            _discovery_cooldown_cache.clear()
        except Exception:
            pass
