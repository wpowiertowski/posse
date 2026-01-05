"""Ghost Webhook Receiver Package.

This package provides a Flask-based webhook receiver that accepts
POST requests containing Ghost blog post data, validates them against
the Ghost post JSON schema, and logs them for processing.

The webhook receiver is designed to be triggered by Ghost's webhook
feature whenever a post is published, updated, or deleted, enabling
real-time syndication to social media platforms.

Key Components:
    app: Flask application instance configured with webhook endpoints
    main: Entry point function to start the Flask server

Endpoints:
    POST /webhook/ghost: Receives and validates Ghost post webhooks
    GET /health: Health check endpoint for monitoring

Usage:
    Start the webhook server:
        $ poetry run ghost-webhook
        
    Or use Flask directly:
        $ FLASK_APP=ghost.ghost flask run
        
    Test with curl:
        $ curl -X POST http://localhost:5000/webhook/ghost \
               -H "Content-Type: application/json" \
               -d @tests/fixtures/valid_ghost_post.json

Validation:
    All incoming posts are validated against the Ghost post JSON schema
    (src/schema/ghost_post_schema.json) to ensure data integrity before
    processing.

Logging:
    The receiver logs all webhook activity to 'ghost_posts.log' with:
    - INFO: Post reception events with timestamps
    - DEBUG: Full payload details
    - ERROR: Validation failures and exceptions
"""
from .ghost import app, create_app

__all__ = ["app", "create_app"]
