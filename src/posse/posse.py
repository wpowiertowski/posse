"""
POSSE Core Module.

This module provides the main entry point and core functionality
for the POSSE (Publish Own Site, Syndicate Elsewhere) system.

The posse entry point embeds Gunicorn to run the Ghost webhook receiver
as a production-ready WSGI application, which:
1. Receives posts from Ghost via webhooks (POST /webhook/ghost)
2. Validates posts against JSON Schema (post.current and post.previous structure)
3. Logs post reception with full payload details
4. Queues valid posts to an events queue for syndication
5. Will eventually syndicate to Mastodon and Bluesky accounts

The events queue is a thread-safe Queue that receives validated Ghost posts
from the webhook receiver and will be consumed by Mastodon and Bluesky agents.

Functions:
    main() -> None:
        Entry point for the console script. Starts Gunicorn with the Ghost 
        webhook receiver Flask app on port 5000.

Attributes:
    events_queue: Thread-safe queue for validated Ghost posts

Example:
    Run via console script:
        $ poetry run posse
        Starting Gunicorn with extensive logging for debugging
        Gunicorn server is ready to accept connections
"""

from queue import Queue

# Create a thread-safe events queue for validated Ghost posts
# This queue will receive posts from the Ghost webhook receiver (ghost.py)
# and will be consumed by Mastodon and Bluesky agents (to be implemented)
events_queue: Queue = Queue()


def main() -> None:
    """Main entry point for the POSSE console command.
    
    This function is called when running 'poetry run posse' from
    the command line. It embeds and starts Gunicorn with the Ghost
    webhook receiver Flask app.
    
    Architecture:
        Docker → poetry run posse → posse.py main() → Gunicorn → Flask app
        
        This maintains posse.py as the orchestration layer that can
        later add pre-processing, routing, or post-processing logic
        before/after the webhook receiver.
    
    Current behavior:
        Starts Gunicorn server with Ghost webhook Flask app that:
        - Listens on http://0.0.0.0:5000
        - Accepts POST /webhook/ghost with Ghost webhook payloads
        - Validates against JSON schema (nested post.current/post.previous structure)
        - Logs post reception at INFO level with id and title
        - Logs full payload at DEBUG level for debugging
        - Returns appropriate HTTP responses (200/400/500)
        
    Webhook Payload Structure:
        {
          "post": {
            "current": {
              "id": "...",
              "uuid": "...",
              "title": "...",
              "slug": "...",
              "status": "published",
              "url": "...",
              "created_at": "...",
              "updated_at": "...",
              "authors": [...],
              "tags": [...]
            },
            "previous": {
              "status": "draft",
              "updated_at": "...",
              "published_at": null
            }
          }
        }
        
    Future enhancements will:
        1. Process received posts according to tags and rules
        2. Queue posts for syndication to social platforms
        3. Implement Mastodon and Bluesky publishing
        4. Track syndication status and handle retries
        5. Add authentication and rate limiting
        
    Gunicorn Configuration (src/ghost/gunicorn_config.py):
        - Single worker (sufficient for low-frequency webhooks)
        - DEBUG level logging with comprehensive access logs
        - All logs to stdout/stderr for Docker visibility
        - 30s worker timeout, 2s keepalive
        - Lifecycle hooks for monitoring
        
    Returns:
        None
        
    Example:
        $ poetry run posse
        Starting Gunicorn with extensive logging for debugging
        Gunicorn server is ready to accept connections
    """
    # Import Gunicorn application for production deployment
    # This replaces the Flask development server with a production-ready WSGI server
    from gunicorn.app.base import BaseApplication
    from ghost.ghost import create_app
    import sys
    import os
    
    # Create Flask app with events_queue passed as dependency
    app = create_app(events_queue)
    
    # Load Gunicorn configuration from ghost package
    config_path = os.path.join(os.path.dirname(__file__), '..', 'ghost', 'gunicorn_config.py')
    
    class StandaloneApplication(BaseApplication):
        """Custom Gunicorn application for embedding within posse entry point."""
        
        def __init__(self, app, options=None):
            self.options = options or {}
            self.application = app
            super().__init__()
        
        def load_config(self):
            # Load configuration from file
            config_file = self.options.get('config')
            if config_file:
                self.cfg.set("config", config_file)
                # Execute the config file to load settings
                with open(config_file, 'r') as f:
                    config_code = f.read()
                config_namespace = {}
                exec(config_code, config_namespace)
                for key, value in config_namespace.items():
                    if key in self.cfg.settings and value is not None:
                        self.cfg.set(key.lower(), value)
        
        def load(self):
            return self.application
    
    # Start Gunicorn with the Flask app
    options = {
        'config': config_path
    }
    StandaloneApplication(app, options).run()


# Allow running as a script for development/testing
if __name__ == "__main__":
    main()