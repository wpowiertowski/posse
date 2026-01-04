"""Gunicorn configuration for Ghost webhook receiver.

This configuration ensures comprehensive logging for debugging POST requests
and production deployment. All logs are sent to stdout/stderr for Docker
visibility via `docker compose logs`.
"""

import logging
import sys

# Bind to all interfaces on port 5000
bind = "0.0.0.0:5000"

# Worker configuration
# Single worker is sufficient for webhook receiver (not high concurrency)
workers = 1
worker_class = "sync"  # Use sync workers for I/O bound Flask app
worker_connections = 1000
timeout = 30
keepalive = 2

# Logging configuration - extensive for debugging
# All logs go to stdout/stderr for Docker container visibility
accesslog = "-"  # Log all HTTP requests to stdout
errorlog = "-"   # Log all errors to stderr
loglevel = "debug"  # Capture DEBUG, INFO, WARNING, ERROR, CRITICAL

# Access log format - comprehensive request details
access_log_format = (
    '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s '
    '"%(f)s" "%(a)s" %(D)s %(p)s'
)
# Format explanation:
# %(h)s - Remote IP address
# %(l)s - Remote log name (usually '-')
# %(u)s - Username (usually '-')
# %(t)s - Timestamp [DD/Mon/YYYY:HH:MM:SS +ZZZZ]
# %(r)s - Request line (e.g., "POST /webhook/ghost HTTP/1.1")
# %(s)s - HTTP status code
# %(b)s - Response size in bytes
# %(f)s - Referer header
# %(a)s - User-Agent header
# %(D)s - Request time in microseconds
# %(p)s - Process ID

# Enable detailed error tracebacks
capture_output = True  # Capture stdout/stderr from application
enable_stdio_inheritance = True  # Inherit stdio from parent process

# Logging configuration that integrates with application logger
def on_starting(server):
    """Called just before the master process is initialized."""
    server.log.info("Starting Gunicorn with extensive logging for debugging")

def on_reload(server):
    """Called when a worker has been reloaded."""
    server.log.info("Gunicorn worker reloaded")

def when_ready(server):
    """Called just after the server is started."""
    server.log.info("Gunicorn server is ready to accept connections")

def on_exit(server):
    """Called just before exiting Gunicorn."""
    server.log.info("Shutting down Gunicorn")

def worker_int(worker):
    """Called when a worker receives an INT or QUIT signal."""
    worker.log.info("Worker received INT or QUIT signal")

def worker_abort(worker):
    """Called when a worker receives a SIGABRT signal."""
    worker.log.error("Worker received SIGABRT signal - likely timeout")

# Pre-fork configuration for better debugging
preload_app = False  # Disable preload to see per-worker logs
reload = False  # Disable auto-reload in production

# Server mechanics
daemon = False  # Run in foreground for Docker
pidfile = None  # No PID file needed in containers
umask = 0  # Default file permissions
user = None  # Run as current user (container user)
group = None  # Run as current group
tmp_upload_dir = None  # Use system default

# SSL (disabled for development, enable in production)
# keyfile = "/path/to/keyfile"
# certfile = "/path/to/certfile"

# Request limits
limit_request_line = 4096  # Max size of HTTP request line
limit_request_fields = 100  # Max number of HTTP headers
limit_request_field_size = 8190  # Max size of HTTP header field

# Configure Python logger to match Gunicorn's level
logconfig_dict = {
    'version': 1,
    'disable_existing_loggers': False,
    'root': {
        'level': 'DEBUG',
        'handlers': ['console']
    },
    'loggers': {
        'gunicorn.error': {
            'level': 'DEBUG',
            'handlers': ['error_console'],
            'propagate': False,
            'qualname': 'gunicorn.error'
        },
        'gunicorn.access': {
            'level': 'DEBUG',
            'handlers': ['console'],
            'propagate': False,
            'qualname': 'gunicorn.access'
        },
        'ghost.ghost': {
            'level': 'DEBUG',
            'handlers': ['console'],
            'propagate': True,
            'qualname': 'ghost.ghost'
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'generic',
            'stream': sys.stdout
        },
        'error_console': {
            'class': 'logging.StreamHandler',
            'formatter': 'generic',
            'stream': sys.stderr
        },
    },
    'formatters': {
        'generic': {
            'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            'datefmt': '%Y-%m-%d %H:%M:%S',
            'class': 'logging.Formatter'
        }
    }
}
