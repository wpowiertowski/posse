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
    
Note: The main() function starts a blocking Gunicorn server, so unit testing
      its execution is not practical. Integration testing is done via:
      - Manual testing: poetry run posse
      - Docker testing: docker compose up app
      - End-to-end testing: curl POST to /webhook/ghost endpoint
      
      The webhook receiver itself is thoroughly tested in test_ghost.py with
      8 tests covering valid posts, invalid payloads, schema validation, etc.

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

# Import functions being tested
from posse.posse import main


def test_module_imports():
    """Test that all required imports work correctly.
    
    Verifies that:
    1. The posse module can be imported
    2. The main function is accessible and callable
    3. Dependencies (ghost.ghost, gunicorn) are available
    
    This ensures the module structure is correct and dependencies
    are properly configured in pyproject.toml.
    
    Note: This test doesn't execute main() because it's a blocking
          call that starts a Gunicorn server. The actual webhook
          functionality is tested via:
          - test_ghost.py (8 tests for webhook receiver)
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

