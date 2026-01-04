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
        
    The webhook receiver runs with Gunicorn for production deployment:
        - Schema validation for data integrity
        - Structured logging (INFO, DEBUG, ERROR levels)
        - Health check endpoint for monitoring
        - Appropriate error handling and HTTP status codes
        - Single worker (concurrent workers not needed for webhook receiver)
        
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
    from ghost.ghost import app
    import sys
    import os
    
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