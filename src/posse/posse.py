"""
POSSE Core Module.

This module provides the main entry point and core functionality
for the POSSE (Publish Own Site, Syndicate Elsewhere) system.

Currently implements the Ghost webhook receiver as the entry point,
which listens for Ghost post notifications and will eventually:
1. Receive posts from Ghost via webhooks
2. Process and format posts for different platforms
3. Publish to Mastodon and Bluesky accounts
4. Track syndication status and handle errors

Functions:
    main() -> None:
        Entry point for the console script. Starts the Ghost webhook
        receiver on port 5000 to listen for incoming post notifications.

Example:
    Run via console script:
        $ poetry run posse
        Starting Ghost webhook receiver on port 5000
        * Running on http://0.0.0.0:5000/
    
    Or import directly:
        >>> from posse import hello
        >>> hello()
        'Hello world!'
"""

# Import the Ghost webhook server
from ghost.ghost import main as ghost_main


def main() -> None:
    """Main entry point for the POSSE console command.
    
    This function is called when running 'poetry run posse' from
    the command line. It starts the Ghost webhook receiver which
    listens for incoming Ghost post notifications on port 5000.
    
    Current behavior:
        Starts the Flask-based Ghost webhook server that:
        - Listens on http://0.0.0.0:5000
        - Accepts POST /webhook/ghost with Ghost post payloads
        - Validates incoming posts against JSON schema
        - Logs post reception and payload details
        - Returns appropriate HTTP responses
        
    Future enhancements will:
        1. Process received posts according to tags and rules
        2. Queue posts for syndication to social platforms
        3. Implement Mastodon and Bluesky publishing
        4. Track syndication status and handle retries
        5. Add authentication and rate limiting
        
    The webhook receiver is production-ready with:
        - Schema validation for data integrity
        - Structured logging (INFO, DEBUG, ERROR levels)
        - Health check endpoint for monitoring
        - Appropriate error handling and HTTP status codes
        
    Returns:
        None
        
    Example:
        $ poetry run posse
        2026-01-04 10:00:00,000 - ghost.ghost - INFO - Starting Ghost webhook receiver on port 5000
        * Running on http://0.0.0.0:5000/ (Press CTRL+C to quit)
    """
    # Start the Ghost webhook receiver
    # This is a blocking call that runs the Flask server
    ghost_main()


# Allow running as a script for development/testing
if __name__ == "__main__":
    main()