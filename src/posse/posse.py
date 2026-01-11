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
import re
from html.parser import HTMLParser
from logging.handlers import RotatingFileHandler
from typing import List, TYPE_CHECKING, Dict, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

if TYPE_CHECKING:
    from social.mastodon_client import MastodonClient
    from social.bluesky_client import BlueskyClient

from notifications.pushover import PushoverNotifier

# Create a thread-safe events queue for validated Ghost posts
# This queue will receive posts from the Ghost webhook receiver (ghost.py)
# and will be consumed by Mastodon and Bluesky agents (to be implemented)
events_queue: Queue = Queue()

# Configure logging
logger = logging.getLogger(__name__)


class ImageExtractor(HTMLParser):
    """HTML parser to extract image URLs and alt text from HTML content.
    
    This parser extracts img tags with src attributes and optional alt attributes,
    handling both single and double quotes, and various attribute orderings.
    """
    
    def __init__(self):
        super().__init__()
        self.images = []  # List of (url, alt_text) tuples
    
    def handle_starttag(self, tag, attrs):
        """Handle HTML start tags, extracting img src and alt attributes."""
        if tag == 'img':
            attrs_dict = dict(attrs)
            src = attrs_dict.get('src')
            if src:
                alt = attrs_dict.get('alt', '')
                self.images.append((src, alt))


def trim_to_words(text: str, max_length: int) -> str:
    """Trim text to max_length, cutting at word boundaries and adding ellipsis.
    
    Args:
        text: Text to trim
        max_length: Maximum length for the trimmed text
        
    Returns:
        Trimmed text with ellipsis if needed
    """
    if len(text) <= max_length:
        return text
    
    # Reserve 3 characters for ellipsis
    max_length -= 3
    
    # Find the last space before max_length
    trimmed = text[:max_length]
    last_space = trimmed.rfind(' ')
    
    if last_space > 0:
        # Trim at the last space
        return trimmed[:last_space] + "..."
    else:
        # No space found, just trim and add ellipsis
        return trimmed + "..."


def _extract_post(event: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Extract post data from Ghost webhook event.
    
    Args:
        event: Ghost webhook event dictionary
        
    Returns:
        Post data dictionary or None if not available
    """
    if not isinstance(event, dict) or "post" not in event:
        return None
    
    post = event.get("post", None)
    if not isinstance(post, dict) or "current" not in post:
        return None
    
    return post.get("current", {})


def _prepare_content(post: Dict[str, Any], max_length: int) -> tuple[str, List[str], List[str], List[Dict[str, str]]]:
    """Prepare content for posting from Ghost post data.
    
    Args:
        post: Ghost post data dictionary
        max_length: Maximum character length for the post content
        
    Returns:
        Tuple of (post_content, images, media_descriptions, tags)
    """
    post_id = post.get("id", None)
    post_title = post.get("title", None)
    post_url = post.get("url", None)
    
    # Extract excerpt (using correct field name)
    excerpt = post.get("custom_excerpt", None)
    
    # Extract tags with name and slug
    tags_raw = post.get("tags", [])
    tags = [{"name": tag.get("name"), "slug": tag.get("slug")} 
           for tag in tags_raw if isinstance(tag, dict)]
    
    # Extract all unique images from post and their alt text
    images = set()
    alt_text_map: Dict[str, str] = {}
    
    # Add feature_image if present
    feature_image = post.get("feature_image")
    if feature_image:
        images.add(feature_image)
        # Feature images typically don't have alt text in Ghost
        alt_text_map[feature_image] = post.get("feature_image_alt", "")
    
    # Extract images and alt text from HTML content
    html_content = post.get("html", "")
    if html_content:
        # Use HTML parser for robust image extraction
        parser = ImageExtractor()
        try:
            parser.feed(html_content)
            for img_url, alt_text in parser.images:
                images.add(img_url)
                # Store alt text if provided
                if alt_text:
                    alt_text_map[img_url] = alt_text
        except Exception as e:
            logger.warning(f"Failed to parse HTML for images: {e}")
    
    # Convert to sorted list for consistent ordering
    images = sorted(list(images))
    
    # Create media descriptions list matching images order
    media_descriptions = [alt_text_map.get(img, "") for img in images]
    
    # Log extracted content
    logger.info(f"Extracted excerpt: {excerpt[:100] if excerpt else 'None'}...")
    logger.info(f"Extracted {len(tags)} tags: {[tag['name'] for tag in tags]}")
    logger.info(f"Extracted {len(images)} unique images")
    for i, img in enumerate(images):
        alt = media_descriptions[i]
        logger.debug(f"  Image: {img} (alt: '{alt}')")
    
    # Prepare content for posting
    # Create hashtags string (use different variable to preserve tags list)
    hashtags = " ".join([f"#{x['name'].lower()}" for x in tags if not x['name'].isdigit()])
    hashtags += " #posse"
    
    # Calculate space needed for tags and URL (with newlines)
    fixed_content = f"\n{hashtags}\n{post_url}"
    max_text_length = max_length - len(fixed_content)
    
    if excerpt:
        text_content = trim_to_words(excerpt, max_text_length)
        post_content = f"{text_content}{fixed_content}"
    else:
        text_content = trim_to_words(post_title, max_text_length)
        post_content = f"{text_content}{fixed_content}"
    
    return post_content, images, media_descriptions, tags


def _filter_clients_by_tags(post_tags: List[Dict[str, str]], all_clients: List[tuple[str, Any]]) -> List[tuple[str, Any]]:
    """Filter clients based on post tags.
    
    Args:
        post_tags: List of tag dictionaries with 'name' and 'slug' fields
        all_clients: List of (platform_name, client) tuples
        
    Returns:
        Filtered list of (platform_name, client) tuples that should receive the post
    """
    # Extract post tag slugs for matching
    post_tag_slugs = [tag.get("slug", "").lower() for tag in post_tags]
    
    # Filter clients to only those matching post tags
    filtered_clients = []
    for platform, client in all_clients:
        # If client has no tags configured, it receives all posts
        if not client.tags:
            filtered_clients.append((platform, client))
            logger.debug(f"{platform} account '{client.account_name}' has no tag filter - will receive post")
        else:
            # Check if any client tag matches any post tag (case-insensitive)
            client_tags_lower = [t.lower() for t in client.tags]
            matching_tags = [tag for tag in post_tag_slugs if tag in client_tags_lower]
            
            if matching_tags:
                filtered_clients.append((platform, client))
                logger.info(f"{platform} account '{client.account_name}' matches tags {matching_tags} - will receive post")
            else:
                logger.info(f"{platform} account '{client.account_name}' with tags {client.tags} does not match post tags {post_tag_slugs} - skipping")
    
    return filtered_clients


def process_events(mastodon_clients: List["MastodonClient"] = None, bluesky_clients: List["BlueskyClient"] = None):
    """Process events from the events queue.
    
    This function runs in a separate daemon thread and continuously monitors
    the events_queue for new posts. When a post is added to the queue, it:
    1. Pops the event from the queue (blocking until available)
    2. Logs the event details
    3. Syndicates to configured Mastodon and Bluesky accounts
    
    Args:
        mastodon_clients: List of initialized MastodonClient instances (default: None)
        bluesky_clients: List of initialized BlueskyClient instances (default: None)
    
    Note:
        Uses None as default and converts to empty list to avoid mutable default argument pitfall.
    
    The thread runs as a daemon so it will automatically terminate when
    the main program exits.
    """
    # Convert None to empty list (avoids mutable default argument anti-pattern)
    mastodon_clients = mastodon_clients if mastodon_clients is not None else []
    bluesky_clients = bluesky_clients if bluesky_clients is not None else []
    
    # Import notifier here to avoid circular imports
    from config import load_config
    from notifications.pushover import PushoverNotifier
    
    # Load config and initialize notifier with error handling for test environments
    try:
        config = load_config()
        notifier = PushoverNotifier.from_config(config)
    except Exception as e:
        logger.warning(f"Failed to initialize notifier (this is expected in test environments): {e}")
        # Create a disabled notifier as fallback
        notifier = PushoverNotifier(config_enabled=False)
    
    logger.info(f"Event processor thread started with {len(mastodon_clients)} Mastodon clients and {len(bluesky_clients)} Bluesky clients")
    
    while True:
        try:
            # Block until an event is available in the queue
            event = events_queue.get(block=True)
            
            # Log the popped event
            logger.info(f"Popped event from queue: {event}")
            
            # Extract post data from event
            post = _extract_post(event)
            if not post:
                logger.warning("No valid post data found in event")
                events_queue.task_done()
                continue
            
            # Log post details
            post_id = post.get("id", None)
            post_title = post.get("title", None)
            post_status = post.get("status", None)
            post_url = post.get("url", None)
            logger.info(f"Post ID: {post_id}, Title: {post_title}, Status: {post_status}")
            
            # Prepare content for posting (use conservative 300 char limit for now)
            post_content, images, media_descriptions, tags = _prepare_content(post, 300)
            
            # Collect all enabled clients
            all_clients = []
            for client in mastodon_clients:
                if client.enabled:
                    all_clients.append(("Mastodon", client))
            for client in bluesky_clients:
                if client.enabled:
                    all_clients.append(("Bluesky", client))
            
            # Filter clients by tags
            filtered_clients = _filter_clients_by_tags(tags, all_clients)
            logger.info(f"Posting to {len(filtered_clients)} of {len(all_clients)} enabled accounts after tag filtering")
            
            # Post to all accounts in parallel using thread pool
            def post_to_account(platform: str, client, content: str, media_urls: List[str], media_descriptions: List[str]) -> Dict[str, any]:
                """Post to a single account and return result."""
                try:
                    logger.info(f"Posting to {platform} account '{client.account_name}'...")
                    result = client.post(
                        content=content,
                        media_urls=media_urls if media_urls else None,
                        media_descriptions=media_descriptions if media_descriptions else None
                    )
                    
                    if result:
                        # Extract post URL from result
                        result_url = None
                        if isinstance(result, dict):
                            result_url = result.get("url") or result.get("uri")
                        
                        logger.info(f"Successfully posted to {platform} account '{client.account_name}': {result_url}")
                        notifier.notify_post_success(post_title, client.account_name, platform, result_url)
                        return {"success": True, "platform": platform, "account": client.account_name, "url": result_url}
                    else:
                        error_msg = "Posting returned no result"
                        logger.error(f"Failed to post to {platform} account '{client.account_name}': {error_msg}")
                        notifier.notify_post_failure(post_title, client.account_name, platform, error_msg)
                        return {"success": False, "platform": platform, "account": client.account_name, "error": error_msg}
                
                except Exception as e:
                    error_msg = str(e)
                    logger.error(f"Error posting to {platform} account '{client.account_name}': {error_msg}", exc_info=True)
                    notifier.notify_post_failure(post_title, client.account_name, platform, error_msg)
                    return {"success": False, "platform": platform, "account": client.account_name, "error": error_msg}
            
            # Use ThreadPoolExecutor to post to accounts in parallel
            # Max 10 workers to prevent overwhelming the system
            with ThreadPoolExecutor(max_workers=10) as executor:
                # Submit all posting tasks
                futures = []
                for platform, client in filtered_clients:
                    future = executor.submit(
                        post_to_account,
                        platform,
                        client,
                        post_content,
                        images,
                        media_descriptions
                    )
                    futures.append(future)
                
                # Wait for all posts to complete (with timeout)
                results = []
                for future in as_completed(futures, timeout=60):
                    try:
                        result = future.result()
                        results.append(result)
                    except Exception as e:
                        logger.error(f"Future execution failed: {e}", exc_info=True)
                
                # Log summary
                success_count = sum(1 for r in results if r.get("success"))
                failure_count = len(results) - success_count
                logger.info(f"Posting complete: {success_count} succeeded, {failure_count} failed")
            
            # Clean up cached images after all posting attempts
            if images:
                logger.debug(f"Cleaning up {len(images)} cached images")
                # Use any client to clean up (they all share the same cache)
                if mastodon_clients:
                    mastodon_clients[0]._remove_images(images)
                elif bluesky_clients:
                    bluesky_clients[0]._remove_images(images)
            
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
    # Import dependencies
    from gunicorn.app.base import BaseApplication
    from ghost.ghost import create_app
    from config import load_config
    from social.mastodon_client import MastodonClient
    from social.bluesky_client import BlueskyClient
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
    
    # Clear any existing handlers to avoid duplicates (e.g., from gunicorn)
    root_logger.handlers.clear()
    
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
    logger.info("Loading configuration from config.yml")
    config = load_config()
    
    # Initialize Pushover notifier
    notifier = PushoverNotifier.from_config(config)
    
    # Initialize Mastodon clients from config
    logger.info("Initializing Mastodon clients from configuration")
    mastodon_clients = MastodonClient.from_config(config, notifier)
    logger.info(f"Initialized {len(mastodon_clients)} Mastodon client(s)")
    for client in mastodon_clients:
        if client.enabled:
            logger.info(f"  - Mastodon account '{client.account_name}' enabled for {client.instance_url}")
        else:
            logger.warning(f"  - Mastodon account '{client.account_name}' disabled (missing credentials or config)")
    
    # Initialize Bluesky clients from config
    logger.info("Initializing Bluesky clients from configuration")
    bluesky_clients = BlueskyClient.from_config(config, notifier)
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