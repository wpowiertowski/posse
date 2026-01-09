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
import threading
import logging
from logging.handlers import RotatingFileHandler
from typing import List

# Create a thread-safe events queue for validated Ghost posts
# This queue will receive posts from the Ghost webhook receiver (ghost.py)
# and will be consumed by Mastodon and Bluesky agents (to be implemented)
events_queue: Queue = Queue()

# Configure logging
logger = logging.getLogger(__name__)


def process_events(mastodon_clients: List = None, bluesky_clients: List = None):
    """Process events from the events queue.
    
    This function runs in a separate daemon thread and continuously monitors
    the events_queue for new posts. When a post is added to the queue, it:
    1. Pops the event from the queue (blocking until available)
    2. Logs the event details
    3. Syndicates to configured Mastodon and Bluesky accounts
    
    Args:
        mastodon_clients: List of initialized MastodonClient instances
        bluesky_clients: List of initialized BlueskyClient instances
    
    The thread runs as a daemon so it will automatically terminate when
    the main program exits.
    """
    mastodon_clients = mastodon_clients or []
    bluesky_clients = bluesky_clients or []
    
    logger.info(f"Event processor thread started with {len(mastodon_clients)} Mastodon clients and {len(bluesky_clients)} Bluesky clients")
    
    while True:
        try:
            # Block until an event is available in the queue
            event = events_queue.get(block=True)
            
            # Log the popped event
            logger.info(f"Popped event from queue: {event}")
            
            # Extract post details if available with safe defaults
            post = None 
            if isinstance(event, dict) and "post" in event:
                post = event.get("post", None)
                if isinstance(post, dict) and "current" in post:
                    post = post.get("current", {})
                    post_id = post.get("id", None)
                    post_title = post.get("title", None)
                    post_status = post.get("status", None)
                    logger.info(f"Post ID: {post_id}, Title: {post_title}, Status: {post_status}")

            content = None
            if post:
                excerpt = post.get("excerpt", None) 
                published_at = post.get("published_at", None)
                tags = post.get("tags", None)
                revisions = [x for x in post.get("post_revisions", [])]
                if revisions:
                    # get most up to date revision
                    content = revisions[-1]

            if content:
                # main part of the post is now in content["lexical"] encoded as a JSON which can be decoded with json.loads(content["lexical"])
                pass
            
            # Syndicate to configured social media accounts
            # For now, we'll just log that we have the clients registered
            if mastodon_clients:
                logger.info(f"Mastodon clients available: {[c.account_name for c in mastodon_clients if c.enabled]}")
            if bluesky_clients:
                logger.info(f"Bluesky clients available: {[c.account_name for c in bluesky_clients if c.enabled]}")
            
            # Mark task as done
            events_queue.task_done()
            
        except Exception as e:
            logger.error(f"Error processing event: {e}", exc_info=True)


def main(debug: bool = False) -> None:
    """Main entry point for the POSSE console command.
    
    This function is called when running 'poetry run posse' from
    the command line. It embeds and starts Gunicorn with the Ghost
    webhook receiver Flask app.
    
    Args:
        debug: Enable debug mode with infinite timeout for breakpoint debugging.
               Can be set via --debug flag or POSSE_DEBUG environment variable.
    
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
    
    # Parse debug flag from environment or command line args
    if not debug:
        debug = os.environ.get("POSSE_DEBUG", "").lower() in ("true", "1", "yes")
        if len(sys.argv) > 1 and "--debug" in sys.argv:
            debug = True
    
    # Configure global logging with 10MB limit
    # Set logging level based on debug flag
    log_level = logging.DEBUG if debug else logging.INFO
    
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    
    # Create rotating file handler with 10MB limit and 3 backup files
    log_handler = RotatingFileHandler(
        "posse.log",
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=3
    )
    log_handler.setLevel(log_level)
    
    # Create formatter and add to handler
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    log_handler.setFormatter(formatter)
    
    # Add handler to root logger
    root_logger.addHandler(log_handler)
    
    # Also add console handler for stdout
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)
    
    if debug:
        logger.info("Debug mode enabled: verbose logging and worker timeout disabled for breakpoint debugging")
    
    # Load configuration
    from config import load_config
    logger.info("Loading configuration from config.yml")
    config = load_config()
    
    # Initialize Mastodon clients from config
    from mastodon_client.mastodon_client import MastodonClient
    logger.info("Initializing Mastodon clients from configuration")
    mastodon_clients = MastodonClient.from_config(config)
    logger.info(f"Initialized {len(mastodon_clients)} Mastodon client(s)")
    for client in mastodon_clients:
        if client.enabled:
            logger.info(f"  - Mastodon account '{client.account_name}' enabled for {client.instance_url}")
        else:
            logger.warning(f"  - Mastodon account '{client.account_name}' disabled (missing credentials or config)")
    
    # Initialize Bluesky clients from config
    from social.bluesky_client import BlueskyClient
    logger.info("Initializing Bluesky clients from configuration")
    bluesky_clients = BlueskyClient.from_config(config)
    logger.info(f"Initialized {len(bluesky_clients)} Bluesky client(s)")
    for client in bluesky_clients:
        if client.enabled:
            logger.info(f"  - Bluesky account '{client.account_name}' enabled for {client.instance_url}")
        else:
            logger.warning(f"  - Bluesky account '{client.account_name}' disabled (missing credentials or config)")
    
    # Create Flask app with events_queue passed as dependency
    app = create_app(events_queue)
    
    # Load Gunicorn configuration from ghost package
    config_path = os.path.join(os.path.dirname(__file__), "..", "ghost", "gunicorn_config.py")
    
    class StandaloneApplication(BaseApplication):
        """Custom Gunicorn application for embedding within posse entry point."""
        
        def __init__(self, app, options=None):
            self.options = options or {}
            self.application = app
            super().__init__()
        
        def load_config(self):
            # Load configuration from file
            config_file = self.options.get("config")
            if config_file:
                self.cfg.set("config", config_file)
                # Execute the config file to load settings
                with open(config_file, "r") as f:
                    config_code = f.read()
                config_namespace = {}
                exec(config_code, config_namespace)
                for key, value in config_namespace.items():
                    if key in self.cfg.settings and value is not None:
                        self.cfg.set(key.lower(), value)
                
                # Add post_worker_init hook to start event processor in each worker
                def post_worker_init_hook(worker):
                    """Start event processor thread after worker initialization."""
                    worker.log.info(f"Starting event processor thread in worker {worker.pid}")
                    # Get clients from options
                    mastodon_clients = self.options.get("mastodon_clients", [])
                    bluesky_clients = self.options.get("bluesky_clients", [])
                    event_thread = threading.Thread(
                        target=process_events, 
                        args=(mastodon_clients, bluesky_clients),
                        daemon=True
                    )
                    event_thread.start()
                    worker.log.info(f"Event processor thread started in worker {worker.pid}")
                
                self.cfg.set("post_worker_init", post_worker_init_hook)
                
                # Set timeout based on debug flag
                if self.options.get("debug"):
                    self.cfg.set("timeout", 0)
        
        def load(self):
            return self.application
    
    # Start Gunicorn with the Flask app
    options = {
        "config": config_path,
        "debug": debug,
        "mastodon_clients": mastodon_clients,
        "bluesky_clients": bluesky_clients
    }
    StandaloneApplication(app, options).run()


# Allow running as a script for development/testing
if __name__ == "__main__":
    main()