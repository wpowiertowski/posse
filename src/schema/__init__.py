"""Schema Package - JSON Schema Loading and Validation.

This package provides centralized loading and access to JSON schemas
used throughout the POSSE system for validating data structures.

The primary purpose is to load schemas once at module import time and
expose them as module-level constants, avoiding repeated file I/O and
providing a single source of truth for schema definitions.

Architecture:
    - Schemas stored as JSON files in src/schema/
    - Loaded once when this package is imported
    - Exposed as constants for direct access
    - Also available via getter functions for flexibility
    
Available Schemas:
    GHOST_POST_SCHEMA: JSON Schema for Ghost blog post objects
        Validates posts received from Ghost webhooks or Content API.
        Based on JSON Schema Draft 7 specification.
        
Usage Patterns:
    # Direct import (most common):
    from schema import GHOST_POST_SCHEMA
    validate(instance=post_data, schema=GHOST_POST_SCHEMA)
    
    # Function-based access (for dynamic use):
    from schema import get_ghost_post_schema
    schema = get_ghost_post_schema()
    
Benefits:
    - Single source of truth for schema definitions
    - Loaded once at startup (performance)
    - Easy to mock in tests (import and patch)
    - Clear error messages if schema files missing
    - Type hints for better IDE support
    
Error Handling:
    If schema files are missing or contain invalid JSON, the import
    will fail with a clear error message pointing to the expected
    file location. This fail-fast behavior prevents runtime errors.
"""
from .schema import GHOST_POST_SCHEMA, get_ghost_post_schema

__all__ = ["GHOST_POST_SCHEMA", "get_ghost_post_schema"]
