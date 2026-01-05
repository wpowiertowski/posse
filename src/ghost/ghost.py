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
from typing import Any, Dict
from queue import Queue

from flask import Flask, request, jsonify, current_app
from jsonschema import validate, ValidationError, Draft7Validator

from schema import GHOST_POST_SCHEMA
from notifications.pushover import PushoverNotifier

# Configure logging with both file and console output
# This ensures webhook activity is both saved to disk and visible in real-time
logging.basicConfig(
    level=logging.DEBUG,  # Capture all levels (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',  # Include timestamp
    handlers=[
        logging.FileHandler('ghost_posts.log'),  # Persist logs to file
        logging.StreamHandler()  # Also print to console for monitoring
    ]
)

logger = logging.getLogger(__name__)

# Create validator for better error messages
# Draft7Validator provides detailed validation error context including
# the path to the failing field and the specific constraint violated
validator = Draft7Validator(GHOST_POST_SCHEMA)


def create_app(events_queue: Queue) -> Flask:
    """Factory function to create and configure the Flask application.
    
    This factory pattern allows dependency injection of the events_queue,
    avoiding circular imports and making the app easier to test.
    
    Args:
        events_queue: Thread-safe Queue instance for validated Ghost posts
        
    Returns:
        Configured Flask application instance with webhook and health endpoints
        
    Example:
        >>> from queue import Queue
        >>> queue = Queue()
        >>> app = create_app(queue)
        >>> # Use app with test client or run with Gunicorn
    """
    app = Flask(__name__)
    
    # Store events_queue in app config for access in route handlers
    app.config['EVENTS_QUEUE'] = events_queue
    
    # Initialize Pushover notifier for push notifications
    # Will be disabled if PUSHOVER_APP_TOKEN or PUSHOVER_USER_KEY env vars are not set
    notifier = PushoverNotifier()
    app.config['PUSHOVER_NOTIFIER'] = notifier
    
    @app.route('/webhook/ghost', methods=['POST'])
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
                   -d '{"id":"123","title":"Test",...}'
        """
        # Get notifier and events queue from app config at function start
        # This ensures they're accessible in exception handlers
        notifier = current_app.config['PUSHOVER_NOTIFIER']
        events_queue = current_app.config['EVENTS_QUEUE']
        
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
            post_data = payload.get('post', {}).get('current', {})
            post_id = post_data.get('id', 'unknown')
            post_title = post_data.get('title', 'untitled')
            post_url = post_data.get('url', '')
            
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
    
    @app.route('/health', methods=['GET'])
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
    
    return app


# Create default app instance with a temporary queue
# This instance is used for module-level imports and fallback scenarios.
# In production, posse.py calls create_app(events_queue) with the real queue.
app = create_app(Queue())


class GhostPostValidationError(Exception):
    """Raised when Ghost post payload fails schema validation.
    
    This custom exception wraps jsonschema.ValidationError to provide
    more context about which field failed validation and why.
    
    Attributes:
        message: Human-readable error description including field path
        
    Example:
        >>> validate_ghost_post({"id": "123"})
        GhostPostValidationError: Schema validation failed: 'title' is required at path: 
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
        GhostPostValidationError: Schema validation failed: 'title' is required...
    """
    try:
        # Validate against the schema (raises ValidationError on failure)
        validate(instance=payload, schema=GHOST_POST_SCHEMA)
    except ValidationError as e:
        # Construct a more informative error message
        # e.path provides the JSON path to the failing field
        # e.message describes what constraint was violated
        error_msg = f"Schema validation failed: {e.message} at path: {'.'.join(str(p) for p in e.path)}"
        raise GhostPostValidationError(error_msg) from e

