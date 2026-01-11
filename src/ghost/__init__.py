"""Ghost Webhook Receiver Package.

This package provides a Flask-based webhook receiver that accepts
POST requests containing Ghost blog post data, validates them against
the Ghost post JSON schema, and logs them for processing.

The webhook receiver is designed to be triggered by Ghost's webhook
feature whenever a post is published, updated, or deleted, enabling
real-time syndication to social media platforms.

Key Components:
    create_app: Factory function to create Flask application with dependency injection

Endpoints:
    POST /webhook/ghost: Receives and validates Ghost post webhooks
    GET /health: Health check endpoint for monitoring

Usage:
    Always use the create_app factory function with dependency injection:
        >>> from queue import Queue
        >>> from ghost.ghost import create_app
        >>> events_queue = Queue()
        >>> app = create_app(events_queue)
        
    Or run via console script:
        $ poetry run posse

Validation:
    All incoming posts are validated against the Ghost post JSON schema
    (src/schema/ghost_post_schema.json) to ensure data integrity before
    processing.

Logging:
    The receiver logs all webhook activity to "ghost_posts.log" with:
    - INFO: Post reception events with timestamps
    - DEBUG: Full payload details
    - ERROR: Validation failures and exceptions
"""
from .ghost import create_app

__all__ = ["create_app"]
