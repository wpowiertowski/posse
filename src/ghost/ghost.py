"""
Ghost Webhook Receiver - Flask Application.

This module implements a Flask-based webhook receiver that accepts POST requests
containing Ghost blog post data, validates them against a JSON schema, logs them,
and queues them for syndication to social media platforms.

Architecture:
    The webhook receiver follows a request-validation-logging-queuing pattern:
    1. Receive JSON payload via POST request
    2. Validate Content-Type header (must be application/json)
    3. Parse JSON body
    4. Validate against Ghost post schema (JSON Schema Draft 7)
    5. Log successful reception at INFO level
    6. Log full payload at DEBUG level
    7. Push validated post to events queue for syndication
    8. Return appropriate HTTP status code

Schema Validation:
    Uses jsonschema library with Draft7Validator to validate incoming posts
    against the Ghost post schema. The schema defines:
    - Required fields: id, title, slug, content, url, created_at, updated_at
    - Optional fields: tags, authors, featured, meta fields, etc.
    - Type constraints and format validation (e.g., date-time, URIs)

Events Queue:
    Valid posts are pushed to an events_queue instance passed via the app factory.
    This queue will be consumed by Mastodon and Bluesky agents (to be implemented)
    for cross-posting to social media platforms.

    The queue is injected through create_app(events_queue) and stored in app.config.

Logging Strategy:
    - Handler: FileHandler (ghost_posts.log) + StreamHandler (console)
    - Format: timestamp - logger_name - level - message
    - Levels:
        * INFO: Post reception notifications (id, title, timestamp)
        * DEBUG: Full JSON payload dumps (can be large)
        * ERROR: Validation failures, malformed requests, exceptions

Error Handling:
    Returns appropriate HTTP status codes:
    - 200: Success (post validated, logged, and queued)
    - 400: Bad request (non-JSON, schema validation failure)
    - 500: Internal server error (unexpected exceptions)

    All errors include JSON response with:
    - status: "error" or "success"
    - message: Human-readable description
    - details: Specific error information (for validation errors)

Security Considerations:
    - Input validation: Ghost post IDs are validated against strict format
    - Path traversal protection: File paths are validated to prevent directory escape
    - Discovery rate limiting: Cooldown mechanism prevents resource exhaustion
    - No authentication implemented (add API key validation in production)
    - All inputs validated against strict schema
    - No direct database writes (only logging)
    - Consider rate limiting for production deployments

Example Webhook Payload:
    POST /webhook/ghost HTTP/1.1
    Host: localhost:5000
    Content-Type: application/json
    
    {
      "id": "507f1f77bcf86cd799439011",
      "title": "Welcome to Ghost",
      "slug": "welcome-to-ghost",
      "content": "<p>Post content...</p>",
      "url": "https://blog.example.com/welcome/",
      "created_at": "2024-01-15T10:00:00.000Z",
      "updated_at": "2024-01-15T10:00:00.000Z"
    }

Functions:
    validate_ghost_post(payload): Validates post against schema
    receive_ghost_post(): Flask endpoint handler for POST /webhook/ghost
    health_check(): Flask endpoint handler for GET /health
    main(): Starts the Flask development server

Classes:
    GhostPostValidationError: Custom exception for schema validation failures
"""
import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, Optional
from queue import Queue

from flask import Flask, request, jsonify, current_app
from flask_cors import CORS
from jsonschema import validate, ValidationError, Draft7Validator

from schema import GHOST_POST_SCHEMA
from notifications.pushover import PushoverNotifier
from config import load_config

# Logging is configured in posse.py main() - this module uses the configured logger
logger = logging.getLogger(__name__)

# =============================================================================
# Security: Input Validation and Rate Limiting
# =============================================================================

# Ghost post ID validation pattern (24 hex characters - MongoDB ObjectID format)
GHOST_POST_ID_PATTERN = re.compile(r'^[a-f0-9]{24}$')

# Discovery cooldown cache to prevent resource exhaustion attacks
# Structure: {post_id: timestamp_of_last_discovery_attempt}
# Uses OrderedDict for LRU-style eviction
from collections import OrderedDict
_discovery_cooldown_cache: OrderedDict[str, float] = OrderedDict()
DISCOVERY_COOLDOWN_SECONDS = 300  # 5 minutes between discovery attempts for same ID
MAX_COOLDOWN_CACHE_SIZE = 1000  # Reduced from 10000 for better memory management

# Global discovery rate limiting to prevent resource exhaustion
# Limits total discovery attempts across all post IDs
_global_discovery_timestamps: list = []
GLOBAL_DISCOVERY_LIMIT = 50  # Max discovery attempts per window
GLOBAL_DISCOVERY_WINDOW_SECONDS = 60  # 1 minute window

# Request rate limiting per IP (in-memory, consider Redis for production)
from collections import defaultdict
_request_rate_cache: Dict[str, list] = defaultdict(list)
REQUEST_RATE_LIMIT = 60  # Max requests per IP per window
REQUEST_RATE_WINDOW_SECONDS = 60  # 1 minute window

# Allowed referrers for interactions endpoint (populated from config)
_allowed_referrers: list = []


def validate_ghost_post_id(post_id: str) -> bool:
    """
    Validate that a Ghost post ID matches the expected format.

    Ghost uses MongoDB ObjectIDs which are 24-character hexadecimal strings.
    This validation prevents path traversal attacks and other injection attempts.

    Args:
        post_id: The post ID string to validate

    Returns:
        True if valid, False otherwise

    Examples:
        >>> validate_ghost_post_id("507f1f77bcf86cd799439011")
        True
        >>> validate_ghost_post_id("../../../etc/passwd")
        False
        >>> validate_ghost_post_id("abc")
        False
    """
    if not post_id or not isinstance(post_id, str):
        return False
    return bool(GHOST_POST_ID_PATTERN.match(post_id))


def is_safe_path(base_path: str, file_path: str) -> bool:
    """
    Verify that a file path is safely contained within a base directory.

    This prevents path traversal attacks by ensuring the resolved path
    is still within the expected base directory.

    Args:
        base_path: The base directory that should contain the file
        file_path: The full file path to validate

    Returns:
        True if the path is safe, False if it escapes the base directory
    """
    try:
        base = Path(base_path).resolve()
        target = Path(file_path).resolve()
        return target.is_relative_to(base)
    except (ValueError, RuntimeError):
        return False


def check_discovery_cooldown(post_id: str) -> bool:
    """
    Check if a post ID is in discovery cooldown period.

    This prevents resource exhaustion attacks where an attacker floods
    the endpoint with requests for non-existent posts, triggering
    expensive discovery operations (external API calls).

    Args:
        post_id: The Ghost post ID to check

    Returns:
        True if cooldown is active (should skip discovery), False otherwise
    """
    if post_id not in _discovery_cooldown_cache:
        return False

    last_attempt = _discovery_cooldown_cache[post_id]
    return (time.time() - last_attempt) < DISCOVERY_COOLDOWN_SECONDS


def record_discovery_attempt(post_id: str) -> None:
    """
    Record a discovery attempt for rate limiting purposes.

    Uses LRU-style eviction when cache is full - removes oldest entries first.
    This provides bounded memory growth while maintaining rate limiting effectiveness.

    Args:
        post_id: The Ghost post ID that was attempted
    """
    current_time = time.time()

    # If post_id already exists, move it to the end (most recently used)
    if post_id in _discovery_cooldown_cache:
        _discovery_cooldown_cache.move_to_end(post_id)
        _discovery_cooldown_cache[post_id] = current_time
        return

    # If cache is at max size, evict oldest entries (LRU eviction)
    while len(_discovery_cooldown_cache) >= MAX_COOLDOWN_CACHE_SIZE:
        # Remove the oldest entry (first item in OrderedDict)
        _discovery_cooldown_cache.popitem(last=False)

    _discovery_cooldown_cache[post_id] = current_time


def check_global_discovery_limit() -> bool:
    """
    Check if global discovery rate limit has been exceeded.

    This prevents resource exhaustion attacks where an attacker floods
    the endpoint with many different post IDs, each triggering expensive
    discovery operations (external API calls to Ghost, Mastodon, Bluesky).

    Returns:
        True if limit exceeded (should reject), False if allowed
    """
    current_time = time.time()
    cutoff_time = current_time - GLOBAL_DISCOVERY_WINDOW_SECONDS

    # Remove old timestamps outside the window (modify in-place to preserve references)
    _global_discovery_timestamps[:] = [
        ts for ts in _global_discovery_timestamps if ts > cutoff_time
    ]

    return len(_global_discovery_timestamps) >= GLOBAL_DISCOVERY_LIMIT


def record_global_discovery() -> None:
    """Record a global discovery attempt for rate limiting."""
    _global_discovery_timestamps.append(time.time())


def clear_rate_limit_caches() -> None:
    """
    Clear all rate limiting caches.

    This is primarily useful for testing to ensure clean state between tests.
    Should not be called in production code.
    """
    _discovery_cooldown_cache.clear()
    _global_discovery_timestamps.clear()
    _request_rate_cache.clear()


def check_request_rate_limit(client_ip: str) -> bool:
    """
    Check if request rate limit has been exceeded for a client IP.

    Args:
        client_ip: The client's IP address

    Returns:
        True if limit exceeded (should reject), False if allowed
    """
    current_time = time.time()
    cutoff_time = current_time - REQUEST_RATE_WINDOW_SECONDS

    # Clean up old timestamps
    _request_rate_cache[client_ip] = [
        ts for ts in _request_rate_cache[client_ip] if ts > cutoff_time
    ]

    return len(_request_rate_cache[client_ip]) >= REQUEST_RATE_LIMIT


def record_request(client_ip: str) -> None:
    """Record a request for rate limiting."""
    _request_rate_cache[client_ip].append(time.time())

    # Periodic cleanup of stale IPs to prevent memory growth
    if len(_request_rate_cache) > 10000:
        current_time = time.time()
        cutoff_time = current_time - REQUEST_RATE_WINDOW_SECONDS
        stale_ips = [
            ip for ip, timestamps in _request_rate_cache.items()
            if not timestamps or max(timestamps) < cutoff_time
        ]
        for ip in stale_ips:
            del _request_rate_cache[ip]


def validate_referrer(referrer: Optional[str], allowed_referrers: list) -> bool:
    """
    Validate that the request referrer is from an allowed domain.

    Args:
        referrer: The Referer header value (may be None)
        allowed_referrers: List of allowed referrer patterns/domains

    Returns:
        True if referrer is valid or validation is disabled, False otherwise
    """
    # If no allowed referrers configured, skip validation (disabled)
    if not allowed_referrers:
        return True

    # If no referrer provided, reject (when validation is enabled)
    if not referrer:
        return False

    # Check if referrer matches any allowed pattern
    from urllib.parse import urlparse
    try:
        parsed = urlparse(referrer)
        referrer_host = parsed.netloc.lower()

        for allowed in allowed_referrers:
            allowed_lower = allowed.lower()
            # Support exact match or wildcard subdomain match
            if referrer_host == allowed_lower:
                return True
            if allowed_lower.startswith("*.") and referrer_host.endswith(allowed_lower[1:]):
                return True
            # Also check if the full referrer URL starts with the allowed pattern
            if referrer.lower().startswith(allowed_lower):
                return True
    except Exception:
        return False

    return False


def sanitize_error_message(error: Exception) -> str:
    """
    Sanitize an error message to prevent information leakage.

    Removes potentially sensitive information like file paths, credentials,
    tokens, and internal implementation details.

    Args:
        error: The exception to sanitize

    Returns:
        A safe, generic error message
    """
    error_str = str(error).lower()

    # Map known error patterns to safe messages
    if "token" in error_str or "credential" in error_str or "auth" in error_str:
        return "Authentication failed"
    if "timeout" in error_str:
        return "Request timed out"
    if "connection" in error_str or "network" in error_str:
        return "Connection error"
    if "rate limit" in error_str or "too many" in error_str:
        return "Rate limit exceeded"
    if "not found" in error_str or "404" in error_str:
        return "Resource not found"
    if "permission" in error_str or "forbidden" in error_str or "403" in error_str:
        return "Permission denied"

    # Default generic message
    return "Service temporarily unavailable"

# Create validator for better error messages
# Draft7Validator provides detailed validation error context including
# the path to the failing field and the specific constraint violated
validator = Draft7Validator(GHOST_POST_SCHEMA)


def create_app(events_queue: Queue, notifier: Optional[PushoverNotifier] = None, config: Optional[Dict[str, Any]] = None,
               mastodon_clients: Optional[list] = None, bluesky_clients: Optional[list] = None,
               llm_client: Optional[Any] = None, ghost_api_client: Optional[Any] = None) -> Flask:
    """Factory function to create and configure the Flask application.

    This factory pattern allows dependency injection of the events_queue, notifier,
    and config, avoiding circular imports and making the app easier to test.

    Args:
        events_queue: Thread-safe Queue instance for validated Ghost posts
        notifier: Optional PushoverNotifier instance (if None, will be created from config)
        config: Optional configuration dictionary (if None, will be loaded from config.yml)
        mastodon_clients: Optional list of MastodonClient instances
        bluesky_clients: Optional list of BlueskyClient instances
        llm_client: Optional LLMClient instance
        ghost_api_client: Optional Ghost Content API client instance

    Returns:
        Configured Flask application instance with webhook and health endpoints

    Example:
        >>> from queue import Queue
        >>> queue = Queue()
        >>> app = create_app(queue)
        >>> # Use app with test client or run with Gunicorn
    """
    app = Flask(__name__)

    # Load configuration and initialize Pushover notifier if not provided
    # Reads from config.yml and Docker secrets
    if config is None:
        config = load_config()

    # Configure CORS to allow requests from the blog domain(s)
    # Read origins from config.yml
    cors_config = config.get("cors", {})
    if cors_config.get("enabled", False):
        cors_origins = cors_config.get("origins", [])
        if cors_origins:
            CORS(app, origins=cors_origins)
            logger.info(f"CORS enabled for origins: {cors_origins}")
        else:
            logger.warning("CORS enabled but no origins configured")
    else:
        logger.info("CORS is disabled in configuration")

    # Store events_queue in app config for access in route handlers
    app.config["EVENTS_QUEUE"] = events_queue
    if notifier is None:
        notifier = PushoverNotifier.from_config(config)
    app.config["PUSHOVER_NOTIFIER"] = notifier

    # Store service clients for healthcheck endpoint and interaction discovery
    app.config["MASTODON_CLIENTS"] = mastodon_clients or []
    app.config["BLUESKY_CLIENTS"] = bluesky_clients or []
    app.config["LLM_CLIENT"] = llm_client
    app.config["GHOST_API_CLIENT"] = ghost_api_client

    # =================================================================
    # Security Configuration
    # =================================================================
    security_config = config.get("security", {})

    # Allowed referrers for interactions endpoint
    # If empty, referrer validation is disabled (backward compatible)
    app.config["ALLOWED_REFERRERS"] = security_config.get("allowed_referrers", [])
    if app.config["ALLOWED_REFERRERS"]:
        logger.info(f"Referrer validation enabled for: {app.config['ALLOWED_REFERRERS']}")
    else:
        logger.info("Referrer validation disabled (no allowed_referrers configured)")

    # Rate limiting configuration
    app.config["RATE_LIMIT_ENABLED"] = security_config.get("rate_limit_enabled", True)
    app.config["RATE_LIMIT_REQUESTS"] = security_config.get("rate_limit_requests", REQUEST_RATE_LIMIT)
    app.config["RATE_LIMIT_WINDOW"] = security_config.get("rate_limit_window_seconds", REQUEST_RATE_WINDOW_SECONDS)

    # Discovery rate limiting
    app.config["DISCOVERY_RATE_LIMIT_ENABLED"] = security_config.get("discovery_rate_limit_enabled", True)
    app.config["DISCOVERY_RATE_LIMIT"] = security_config.get("discovery_rate_limit", GLOBAL_DISCOVERY_LIMIT)
    app.config["DISCOVERY_RATE_WINDOW"] = security_config.get("discovery_rate_window_seconds", GLOBAL_DISCOVERY_WINDOW_SECONDS)

    # Internal API token for protected endpoints
    # Priority: config value > config file > environment variable
    from config import read_secret_file
    internal_token = security_config.get("internal_api_token")
    if not internal_token:
        token_file = security_config.get("internal_api_token_file")
        if token_file:
            internal_token = read_secret_file(token_file)
    if not internal_token:
        internal_token = os.environ.get("INTERNAL_API_TOKEN")
    app.config["INTERNAL_API_TOKEN"] = internal_token
    if internal_token:
        logger.info("Internal API token configured for protected endpoints")
    
    @app.route("/webhook/ghost", methods=["POST"])
    def receive_ghost_post():
        """Webhook endpoint to receive Ghost post notifications.
        
        This is the main webhook endpoint that Ghost will POST to whenever
        a post event occurs (published, updated, deleted). The handler:
        
        1. Validates Content-Type is application/json
        2. Parses the JSON payload
        3. Validates against Ghost post schema
        4. Logs the post reception (INFO level)
        5. Logs full payload (DEBUG level)
        6. Pushes validated post to events queue for syndication
        7. Returns success response with post ID
        
        Request Format:
            POST /webhook/ghost
            Content-Type: application/json
            
            {
              "id": "string",
              "title": "string",
              "slug": "string",
              "content": "string",
              "url": "string",
              "created_at": "ISO-8601 datetime",
              "updated_at": "ISO-8601 datetime",
              ... (additional optional fields)
            }
        
        Success Response (200):
            {
              "status": "success",
              "message": "Post received and validated",
              "post_id": "507f1f77bcf86cd799439011"
            }
        
        Error Response (400 - Validation Failed):
            {
              "status": "error",
              "message": "Invalid Ghost post payload",
              "details": "Schema validation failed: ..."
            }
        
        Error Response (400 - Non-JSON):
            {
              "error": "Content-Type must be application/json"
            }
        
        Error Response (500 - Internal Error):
            {
              "status": "error",
              "message": "Internal server error"
            }
        
        Returns:
            tuple: (JSON response dict, HTTP status code)
                - 200 on success
                - 400 on validation error or bad request
                - 500 on unexpected server error
                
        Side Effects:
            - Logs INFO message with post id and title
            - Logs DEBUG message with full payload JSON
            - Pushes validated post to events_queue for syndication
            - Logs ERROR message on validation failure
            
        Example:
            $ curl -X POST http://localhost:5000/webhook/ghost \\
                   -H "Content-Type: application/json" \\
                   -d "{"id":"123","title":"Test",...}"
        """
        # Get notifier and events queue from app config at function start
        # This ensures they're accessible in exception handlers
        notifier = current_app.config["PUSHOVER_NOTIFIER"]
        events_queue = current_app.config["EVENTS_QUEUE"]
        
        try:
            # Step 1: Validate Content-Type header
            # Ghost should send application/json, but verify to prevent errors
            if not request.is_json:
                logger.error("Received non-JSON payload")
                return jsonify({"error": "Content-Type must be application/json"}), 400
            
            # Step 2: Parse JSON body from request
            # Flask's get_json() handles parsing and returns None if invalid
            payload = request.get_json()
            
            # Step 3: Validate payload against Ghost post schema
            # This will raise GhostPostValidationError if validation fails
            validate_ghost_post(payload)
            
            # Step 4: Extract key fields for logging and notifications
            # Navigate nested structure: payload.post.current contains the post data
            post_data = payload.get("post", {}).get("current", {})
            post_id = post_data.get("id", "unknown")
            post_title = post_data.get("title", "untitled")
            post_url = post_data.get("url", "")
            
            # Step 5: Log successful reception at INFO level
            # This provides a concise audit trail of received posts
            logger.info(f"Received Ghost post: id={post_id}, title='{post_title}'")
            
            # Step 6: Send Pushover notification for post reception
            notifier.notify_post_received(post_title, post_id)
            
            # Step 7: Log full payload at DEBUG level
            # Pretty-print JSON for readability (indent=2)
            # This is verbose but crucial for debugging processing issues
            logger.debug(f"Ghost post payload: {json.dumps(payload, indent=2)}")
            
            # Step 8: Push validated post to events queue
            # The queue will be consumed by Mastodon and Bluesky agents
            events_queue.put(payload)
            logger.debug(f"Post queued for syndication: id={post_id}")
            
            # Step 9: Send Pushover notification for post queued
            notifier.notify_post_queued(post_title, post_url)
            
            # Step 10: Return success response with post metadata
            return jsonify({
                "status": "success",
                "message": "Post received and validated",
                "post_id": post_id
            }), 200
            
        except GhostPostValidationError as e:
            # Schema validation failed - log at ERROR level
            # The error message includes which field failed and why
            logger.error(f"Payload validation failed: {str(e)}")
            
            # Send Pushover notification for validation error
            notifier.notify_validation_error(str(e))
            
            return jsonify({
                "status": "error",
                "message": "Invalid Ghost post payload",
                "details": str(e)
            }), 400
            
        except Exception as e:
            # Unexpected error (parsing, I/O, etc.)
            # Log with full traceback for debugging (exc_info=True)
            logger.error(f"Unexpected error processing Ghost post: {str(e)}", exc_info=True)
            return jsonify({
                "status": "error",
                "message": "Internal server error"
            }), 500
    
    @app.route("/health", methods=["GET"])
    def health_check():
        """Health check endpoint for monitoring and load balancers.
        
        Simple endpoint that returns 200 OK if the service is running.
        Used by:
        - Container orchestration (Kubernetes, Docker Swarm)
        - Load balancers (HAProxy, nginx)
        - Monitoring systems (Prometheus, Nagios)
        
        Returns:
            tuple: (JSON response, 200 status code)
            
        Example:
            $ curl http://localhost:5000/health
            {"status": "healthy"}
        """
        return jsonify({"status": "healthy"}), 200
    
    @app.route("/healthcheck", methods=["POST"])
    def comprehensive_healthcheck():
        """Comprehensive health check endpoint that verifies all enabled services.
        
        This endpoint checks the status of all configured services:
        - Mastodon accounts (verify credentials)
        - Bluesky accounts (verify credentials)
        - LLM service (health check)
        - Pushover notification service (test notification)
        
        Request:
            POST /healthcheck
            Content-Type: application/json
            
        Success Response (200):
            {
              "status": "healthy",  // or "unhealthy" if any service fails
              "timestamp": "2026-01-16T17:30:00.000Z",
              "services": {
                "mastodon": {
                  "enabled": true,
                  "accounts": {
                    "personal": {"status": "healthy", "username": "@user"},
                    "tech": {"status": "unhealthy", "error": "Invalid token"}
                  }
                },
                "bluesky": {
                  "enabled": true,
                  "accounts": {
                    "main": {"status": "healthy", "handle": "user.bsky.social"}
                  }
                },
                "llm": {"enabled": true, "status": "healthy"},
                "pushover": {"enabled": true, "status": "healthy"}
              }
            }
        
        Returns:
            tuple: (JSON response, 200 status code)
            
        Example:
            $ curl -X POST http://localhost:5000/healthcheck
        """
        from datetime import datetime
        from zoneinfo import ZoneInfo

        # Get service clients from app config
        mastodon_clients = current_app.config.get("MASTODON_CLIENTS", [])
        bluesky_clients = current_app.config.get("BLUESKY_CLIENTS", [])
        llm_client = current_app.config.get("LLM_CLIENT")
        notifier = current_app.config.get("PUSHOVER_NOTIFIER")

        # Initialize response structure
        response = {
            "status": "healthy",
            "timestamp": datetime.now(ZoneInfo("America/Los_Angeles")).isoformat(),
            "services": {}
        }
        
        overall_healthy = True
        
        # Check Mastodon clients
        mastodon_status = {
            "enabled": len(mastodon_clients) > 0,
            "accounts": {}
        }
        
        for client in mastodon_clients:
            if not client.enabled:
                continue
            
            account_name = client.account_name
            try:
                account_info = client.verify_credentials()
                if account_info:
                    mastodon_status["accounts"][account_name] = {
                        "status": "healthy",
                        "username": f"@{account_info.get('username', 'unknown')}"
                    }
                    logger.info(f"Healthcheck: Mastodon account '{account_name}' is healthy")
                else:
                    mastodon_status["accounts"][account_name] = {
                        "status": "unhealthy",
                        "error": "Failed to verify credentials"
                    }
                    overall_healthy = False
                    logger.warning(f"Healthcheck: Mastodon account '{account_name}' failed credential verification")
            except Exception as e:
                mastodon_status["accounts"][account_name] = {
                    "status": "unhealthy",
                    "error": sanitize_error_message(e)
                }
                overall_healthy = False
                logger.error(f"Healthcheck: Mastodon account '{account_name}' error: {e}")
        
        response["services"]["mastodon"] = mastodon_status
        
        # Check Bluesky clients
        bluesky_status = {
            "enabled": len(bluesky_clients) > 0,
            "accounts": {}
        }
        
        for client in bluesky_clients:
            if not client.enabled:
                continue
            
            account_name = client.account_name
            try:
                account_info = client.verify_credentials()
                if account_info:
                    bluesky_status["accounts"][account_name] = {
                        "status": "healthy",
                        "handle": account_info.get('handle', 'unknown')
                    }
                    logger.info(f"Healthcheck: Bluesky account '{account_name}' is healthy")
                else:
                    bluesky_status["accounts"][account_name] = {
                        "status": "unhealthy",
                        "error": "Failed to verify credentials"
                    }
                    overall_healthy = False
                    logger.warning(f"Healthcheck: Bluesky account '{account_name}' failed credential verification")
            except Exception as e:
                bluesky_status["accounts"][account_name] = {
                    "status": "unhealthy",
                    "error": sanitize_error_message(e)
                }
                overall_healthy = False
                logger.error(f"Healthcheck: Bluesky account '{account_name}' error: {e}")
        
        response["services"]["bluesky"] = bluesky_status
        
        # Check LLM service
        llm_status = {
            "enabled": llm_client is not None and llm_client.enabled
        }
        
        if llm_status["enabled"]:
            try:
                is_healthy = llm_client._check_health()
                if is_healthy:
                    llm_status["status"] = "healthy"
                    logger.info("Healthcheck: LLM service is healthy")
                else:
                    llm_status["status"] = "unhealthy"
                    llm_status["error"] = "LLM service health check failed"
                    overall_healthy = False
                    logger.warning("Healthcheck: LLM service health check failed")
            except Exception as e:
                llm_status["status"] = "unhealthy"
                llm_status["error"] = sanitize_error_message(e)
                overall_healthy = False
                logger.error(f"Healthcheck: LLM service error: {e}")
        
        response["services"]["llm"] = llm_status
        
        # Check Pushover service
        pushover_status = {
            "enabled": notifier is not None and notifier.enabled
        }
        
        if pushover_status["enabled"]:
            try:
                test_result = notifier.send_test_notification()
                if test_result:
                    pushover_status["status"] = "healthy"
                    logger.info("Healthcheck: Pushover service is healthy")
                else:
                    pushover_status["status"] = "unhealthy"
                    pushover_status["error"] = "Failed to send test notification"
                    overall_healthy = False
                    logger.warning("Healthcheck: Pushover service failed to send test notification")
            except Exception as e:
                pushover_status["status"] = "unhealthy"
                pushover_status["error"] = sanitize_error_message(e)
                overall_healthy = False
                logger.error(f"Healthcheck: Pushover service error: {e}")
        
        response["services"]["pushover"] = pushover_status

        # Set overall status
        response["status"] = "healthy" if overall_healthy else "unhealthy"

        return jsonify(response), 200

    @app.route("/api/interactions/<ghost_post_id>", methods=["GET"])
    def get_interactions(ghost_post_id: str):
        """
        Retrieve interactions for a specific Ghost post.

        This endpoint returns the cached interaction data for a Ghost post,
        including comments, likes, and reposts from Mastodon and Bluesky.

        If no syndication mapping exists, the endpoint will attempt to discover
        the mapping by searching recent social media posts for links to the Ghost post.

        Security:
            - Input validation: ghost_post_id must be a valid 24-char hex string
            - Path traversal protection: file paths are validated
            - IP-based rate limiting: prevents request flooding
            - Referrer validation: only allows requests from configured domains
            - Discovery rate limiting: cooldown prevents resource exhaustion
            - Global discovery limit: prevents mass enumeration attacks
            - Timing normalization: prevents timing-based information leakage

        Args:
            ghost_post_id: Ghost post ID (24 character hex string)

        Returns:
            JSON response with interaction data

        Example:
            GET /api/interactions/507f1f77bcf86cd799439011

            Response:
            {
              "ghost_post_id": "507f1f77bcf86cd799439011",
              "updated_at": "2026-01-27T10:00:00Z",
              "syndication_links": {
                "mastodon": {
                  "personal": {"post_url": "https://mastodon.social/@user/123"}
                },
                "bluesky": {
                  "main": {"post_url": "https://bsky.app/profile/user/post/abc"}
                }
              },
              "platforms": {
                "mastodon": {...},
                "bluesky": {...}
              }
            }
        """
        import random
        from interactions.interaction_sync import InteractionSyncService

        # =================================================================
        # Security: Rate Limiting (per IP)
        # =================================================================
        client_ip = request.headers.get("X-Real-IP") or request.headers.get("X-Forwarded-For", "").split(",")[0].strip() or request.remote_addr

        if current_app.config.get("RATE_LIMIT_ENABLED", True):
            if check_request_rate_limit(client_ip):
                logger.warning(f"Rate limit exceeded for IP: {client_ip}")
                return jsonify({
                    "status": "error",
                    "message": "Rate limit exceeded. Please try again later."
                }), 429

            record_request(client_ip)

        # =================================================================
        # Security: Referrer Validation
        # =================================================================
        allowed_referrers = current_app.config.get("ALLOWED_REFERRERS", [])
        if allowed_referrers:
            referrer = request.headers.get("Referer")
            if not validate_referrer(referrer, allowed_referrers):
                logger.warning(f"Invalid referrer rejected: {referrer!r} from IP {client_ip}")
                return jsonify({
                    "status": "error",
                    "message": "Forbidden"
                }), 403

        # =================================================================
        # Security: Input Validation
        # =================================================================
        # Validate ghost_post_id format to prevent path traversal and injection
        if not validate_ghost_post_id(ghost_post_id):
            logger.warning(f"Invalid post ID format rejected: {ghost_post_id[:50]!r}")
            # Add small random delay to prevent timing attacks
            time.sleep(random.uniform(0.01, 0.05))
            return jsonify({
                "status": "error",
                "message": "Invalid post ID format"
            }), 400

        # Get storage paths from config or use defaults
        storage_path = current_app.config.get("INTERACTIONS_STORAGE_PATH", "./data/interactions")
        mappings_path = current_app.config.get("SYNDICATION_MAPPINGS_PATH", "./data/syndication_mappings")

        # Construct file paths with validated post ID
        interaction_file = os.path.join(storage_path, f"{ghost_post_id}.json")
        mapping_file = os.path.join(mappings_path, f"{ghost_post_id}.json")

        # =================================================================
        # Security: Path Traversal Protection (defense in depth)
        # =================================================================
        if not is_safe_path(storage_path, interaction_file):
            logger.warning(f"Path traversal attempt blocked for interaction file: {ghost_post_id}")
            return jsonify({
                "status": "error",
                "message": "Invalid post ID format"
            }), 400

        if not is_safe_path(mappings_path, mapping_file):
            logger.warning(f"Path traversal attempt blocked for mapping file: {ghost_post_id}")
            return jsonify({
                "status": "error",
                "message": "Invalid post ID format"
            }), 400

        # Check for existing interaction data
        if os.path.exists(interaction_file):
            try:
                with open(interaction_file, 'r') as f:
                    interactions = json.load(f)

                logger.debug(f"Retrieved interactions for post: {ghost_post_id}")
                return jsonify(interactions), 200

            except json.JSONDecodeError as e:
                logger.error(f"Malformed JSON in interaction file for {ghost_post_id}: {e}")
                return jsonify({
                    "status": "error",
                    "message": "Failed to load interaction data"
                }), 500
            except Exception as e:
                logger.error(f"Failed to load interactions for {ghost_post_id}: {e}")
                return jsonify({
                    "status": "error",
                    "message": "Failed to load interaction data"
                }), 500

        # Check for syndication mapping without interaction data
        if os.path.exists(mapping_file):
            try:
                with open(mapping_file, 'r') as f:
                    mapping = json.load(f)

                # Build syndication_links from mapping
                syndication_links = {"mastodon": {}, "bluesky": {}}

                # Extract links for each platform
                for platform in ["mastodon", "bluesky"]:
                    if platform in mapping.get("platforms", {}):
                        for account_name, account_data in mapping["platforms"][platform].items():
                            if isinstance(account_data, list):
                                # Split posts
                                syndication_links[platform][account_name] = [
                                    {"post_url": entry.get("post_url"), "split_index": entry.get("split_index")}
                                    for entry in account_data
                                ]
                            else:
                                # Single post
                                syndication_links[platform][account_name] = {"post_url": account_data.get("post_url")}

                logger.debug(f"Retrieved syndication links for post: {ghost_post_id}")
                return jsonify({
                    "ghost_post_id": ghost_post_id,
                    "updated_at": None,
                    "syndication_links": syndication_links,
                    "platforms": {
                        "mastodon": {},
                        "bluesky": {}
                    },
                    "message": "Syndication links available, no interaction data yet"
                }), 200

            except json.JSONDecodeError as e:
                logger.error(f"Malformed JSON in mapping file for {ghost_post_id}: {e}")
                return jsonify({
                    "status": "error",
                    "message": "Failed to load syndication mapping"
                }), 500
            except Exception as e:
                logger.error(f"Failed to load syndication mapping for {ghost_post_id}: {e}")
                return jsonify({
                    "status": "error",
                    "message": "Failed to load syndication mapping"
                }), 500

        # =================================================================
        # Security: Discovery Rate Limiting
        # =================================================================
        # Check per-ID cooldown before attempting expensive discovery operations
        if check_discovery_cooldown(ghost_post_id):
            logger.debug(f"Discovery cooldown active for post: {ghost_post_id}")
            return jsonify({
                "ghost_post_id": ghost_post_id,
                "updated_at": None,
                "syndication_links": {
                    "mastodon": {},
                    "bluesky": {}
                },
                "platforms": {
                    "mastodon": {},
                    "bluesky": {}
                },
                "message": "No syndication or interaction data available"
            }), 404

        # Check global discovery rate limit (prevents mass enumeration attacks)
        if current_app.config.get("DISCOVERY_RATE_LIMIT_ENABLED", True):
            if check_global_discovery_limit():
                logger.warning(f"Global discovery rate limit exceeded, rejecting discovery for: {ghost_post_id}")
                # Still record this attempt for per-ID cooldown
                record_discovery_attempt(ghost_post_id)
                return jsonify({
                    "ghost_post_id": ghost_post_id,
                    "updated_at": None,
                    "syndication_links": {
                        "mastodon": {},
                        "bluesky": {}
                    },
                    "platforms": {
                        "mastodon": {},
                        "bluesky": {}
                    },
                    "message": "No syndication or interaction data available"
                }), 404

        # Neither interaction file nor mapping file exists - try to discover mapping
        logger.info(f"No interaction data or syndication mapping found for post: {ghost_post_id}, attempting discovery")

        # Get Ghost API client and social media clients
        ghost_api_client = current_app.config.get("GHOST_API_CLIENT")
        mastodon_clients = current_app.config.get("MASTODON_CLIENTS", [])
        bluesky_clients = current_app.config.get("BLUESKY_CLIENTS", [])

        # Record this discovery attempt for rate limiting (both per-ID and global)
        record_discovery_attempt(ghost_post_id)
        record_global_discovery()

        # Try to get the Ghost post URL
        ghost_post_url = None
        if ghost_api_client and ghost_api_client.enabled:
            try:
                post = ghost_api_client.get_post_by_id(ghost_post_id)
                if post:
                    ghost_post_url = post.get("url")
                    logger.debug(f"Retrieved Ghost post URL from API: {ghost_post_url}")
            except Exception as e:
                logger.error(f"Failed to retrieve Ghost post from API: {e}")

        # If we have the Ghost post URL, try to discover the mapping
        if ghost_post_url and (mastodon_clients or bluesky_clients):
            try:
                # Create a temporary InteractionSyncService for discovery
                sync_service = InteractionSyncService(
                    mastodon_clients=mastodon_clients,
                    bluesky_clients=bluesky_clients,
                    storage_path=storage_path,
                    mappings_path=mappings_path
                )

                # Attempt to discover syndication mapping
                mapping_discovered = sync_service.discover_syndication_mapping(
                    ghost_post_id=ghost_post_id,
                    ghost_post_url=ghost_post_url,
                    max_posts_to_search=50
                )

                if mapping_discovered:
                    # Mapping was discovered! Now try to sync interactions
                    logger.info(f"Syndication mapping discovered for post {ghost_post_id}, syncing interactions")
                    try:
                        interactions = sync_service.sync_post_interactions(ghost_post_id)
                        logger.debug(f"Successfully synced interactions after discovery for post: {ghost_post_id}")
                        return jsonify(interactions), 200
                    except Exception as e:
                        logger.error(f"Failed to sync interactions after discovery for {ghost_post_id}: {e}")
                        # Fall through to 404 response

            except Exception as e:
                logger.error(f"Error during syndication mapping discovery for {ghost_post_id}: {e}", exc_info=True)

        # No mapping found or discovered
        logger.warning(f"No syndication mapping found or discovered for post: {ghost_post_id}")
        return jsonify({
            "ghost_post_id": ghost_post_id,
            "updated_at": None,
            "syndication_links": {
                "mastodon": {},
                "bluesky": {}
            },
            "platforms": {
                "mastodon": {},
                "bluesky": {}
            },
            "message": "No syndication or interaction data available"
        }), 404

    @app.route("/api/interactions/<ghost_post_id>/sync", methods=["POST"])
    def trigger_interaction_sync(ghost_post_id: str):
        """
        Manually trigger a sync for a specific post.

        This endpoint immediately syncs interactions for the specified post,
        bypassing the normal scheduler. Useful for testing or immediate updates.

        Security:
            - Authentication: requires X-Internal-Token header (if configured)
            - Input validation: ghost_post_id must be a valid 24-char hex string

        Args:
            ghost_post_id: Ghost post ID (24 character hex string)

        Returns:
            JSON response with sync result

        Example:
            POST /api/interactions/507f1f77bcf86cd799439011/sync
            X-Internal-Token: your-secret-token

            Response:
            {
              "status": "success",
              "message": "Interactions synced successfully",
              "ghost_post_id": "507f1f77bcf86cd799439011"
            }
        """
        # =================================================================
        # Security: Authentication (for internal/admin endpoints)
        # =================================================================
        internal_token = current_app.config.get("INTERNAL_API_TOKEN")
        if internal_token:
            provided_token = request.headers.get("X-Internal-Token")
            if not provided_token or provided_token != internal_token:
                logger.warning(f"Unauthorized sync attempt for post: {ghost_post_id[:50]}")
                return jsonify({
                    "status": "error",
                    "message": "Unauthorized"
                }), 401

        # Security: Input validation
        if not validate_ghost_post_id(ghost_post_id):
            logger.warning(f"Invalid post ID format rejected for sync: {ghost_post_id[:50]!r}")
            return jsonify({
                "status": "error",
                "message": "Invalid post ID format"
            }), 400

        scheduler = current_app.config.get("INTERACTION_SCHEDULER")

        if not scheduler:
            logger.error("InteractionScheduler not configured")
            return jsonify({
                "status": "error",
                "message": "Interaction sync not enabled"
            }), 503

        try:
            # Trigger manual sync
            scheduler.trigger_manual_sync(ghost_post_id)

            logger.info(f"Manual sync triggered for post: {ghost_post_id}")
            return jsonify({
                "status": "success",
                "message": "Interactions synced successfully",
                "ghost_post_id": ghost_post_id
            }), 200

        except Exception as e:
            logger.error(f"Failed to sync interactions for {ghost_post_id}: {e}")
            return jsonify({
                "status": "error",
                "message": "Failed to sync interactions"
            }), 500

    return app


# Note: Do not create a module-level app instance.
# Always use create_app(events_queue) to create app instances with proper dependency injection.
# The module-level app has been removed to prevent orphaned Queue issues.


class GhostPostValidationError(Exception):
    """Raised when Ghost post payload fails schema validation.
    
    This custom exception wraps jsonschema.ValidationError to provide
    more context about which field failed validation and why.
    
    Attributes:
        message: Human-readable error description including field path
        
    Example:
        >>> validate_ghost_post({"id": "123"})
        GhostPostValidationError: Schema validation failed: "title" is required at path: 
    """
    pass


def validate_ghost_post(payload: Dict[str, Any]) -> None:
    """Validate a Ghost post payload against the JSON schema.
    
    Performs strict validation of the incoming payload against the
    Ghost post schema loaded from ghost_post_schema.json. This ensures
    all required fields are present and correctly formatted before
    further processing.
    
    The validation checks:
    - Required fields exist (id, title, slug, content, url, timestamps)
    - Field types match schema (strings, booleans, arrays, objects)
    - Format constraints (URIs, date-time strings)
    - Nested object structures (authors, tags)
    
    Args:
        payload: Dictionary containing Ghost post data from webhook
        
    Raises:
        GhostPostValidationError: If validation fails, includes details about
            which field caused the failure and the validation constraint violated
            
    Example:
        >>> payload = {"id": "123", "title": "Test", ...}
        >>> validate_ghost_post(payload)  # Passes if valid
        >>> 
        >>> invalid = {"id": "123"}  # Missing required fields
        >>> validate_ghost_post(invalid)
        GhostPostValidationError: Schema validation failed: "title" is required...
    """
    try:
        # Validate against the schema (raises ValidationError on failure)
        validate(instance=payload, schema=GHOST_POST_SCHEMA)
    except ValidationError as e:
        # Construct a more informative error message
        # e.path provides the JSON path to the failing field
        # e.message describes what constraint was violated
        path_str = ".".join(str(p) for p in e.path)
        error_msg = f"Schema validation failed: {e.message} at path: {path_str}"
        raise GhostPostValidationError(error_msg) from e

