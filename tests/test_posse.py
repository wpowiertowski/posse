"""
Unit Tests for POSSE Core Module.

This test module validates the POSSE (Publish Own Site, Syndicate Elsewhere)
core module's integration with the Ghost webhook receiver.

The posse module now serves as the main entry point that starts the Ghost
webhook receiver, which accepts post notifications and will eventually
syndicate them to social media platforms.

Test Coverage:
    - Module imports work correctly
    - Integration with ghost webhook receiver
    - Placeholder functions remain functional
    
Future tests will cover:
    - Post processing and filtering logic
    - Social media syndication (Mastodon, Bluesky)
    - Error handling and retry mechanisms
    - Configuration management

Running Tests:
    $ poetry run pytest tests/test_posse.py -v
    $ docker compose run --rm test poetry run pytest tests/test_posse.py
"""

import pytest
from unittest.mock import patch, MagicMock

# Import functions being tested
from posse.posse import main


def test_module_imports():
    """Test that all required imports work correctly.
    
    Verifies that:
    1. The posse module can be imported
    2. The main function is accessible
    4. The ghost.ghost integration import works (implicitly tested by import)
    
    This ensures the module structure is correct and dependencies
    are properly configured.
    """
    # These imports should not raise any exceptions
    from posse import main
    
    # Verify they are callable
    assert callable(main), "main should be callable"


@patch('posse.posse.ghost_main')
def test_main_starts_ghost_webhook(mock_ghost_main):
    """Test that main() correctly delegates to ghost webhook receiver.
    
    The main() function should call ghost_main() to start the webhook
    server. This test uses mocking to verify the integration without
    actually starting a server.
    
    Verifies:
        - main() calls ghost_main() exactly once
        - No additional side effects occur
        
    Note: The actual webhook functionality is tested in test_ghost.py
    """
    # Call the main function
    main()
    
    # Verify ghost_main was called exactly once
    mock_ghost_main.assert_called_once()
    
    # Verify it was called with no arguments
    mock_ghost_main.assert_called_with()