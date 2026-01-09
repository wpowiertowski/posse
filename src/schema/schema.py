"""
Centralized JSON Schema Loading Module.

This module is responsible for loading JSON schema files from disk and
exposing them as module-level constants for use throughout the application.

Design Principles:
    1. Load Once: Schemas are loaded at module import time, not on every use
    2. Fail Fast: Missing or invalid schemas cause immediate import failure
    3. Clear Errors: File location and parse errors are clearly reported
    4. Single Source: All schema access goes through this module
    
The loading strategy ensures:
    - No repeated file I/O during runtime
    - Schemas are validated (parseable JSON) at startup
    - Import errors are caught during development, not production
    - Easy to update schema versions (just replace the JSON file)

File Location:
    Schemas are expected to be in the same directory as this module
    (src/schema/). The path is resolved using __file__ to ensure
    it works regardless of the current working directory.

Error Handling:
    - FileNotFoundError: Schema file doesn't exist at expected path
    - json.JSONDecodeError: Schema file contains invalid JSON syntax
    
    Both errors include the full path and helpful diagnostic messages.
"""
import json
from pathlib import Path
from typing import Dict, Any

# Locate schema directory
# Use Path(__file__).parent to get the directory containing this file
# This makes the code location-independent (works from any working directory)
SCHEMA_DIR = Path(__file__).parent

def _load_schema(schema_filename: str) -> Dict[str, Any]:
    """
    Load a JSON schema file from the schema directory.
    
    This is a private helper function (note the leading underscore) used
    internally by this module to load schema files. It handles file I/O
    and JSON parsing with comprehensive error handling.
    
    The function performs these steps:
    1. Construct full path to schema file
    2. Check if file exists (fail fast if missing)
    3. Open and parse JSON file
    4. Return parsed schema as dictionary
    
    Path Resolution:
        SCHEMA_DIR / schema_filename
        Example: /app/src/schema/ghost_post_schema.json
        
    Args:
        schema_filename: Name of the JSON schema file (e.g., "ghost_post_schema.json")
        
    Returns:
        Parsed JSON schema as a dictionary, ready for use with jsonschema library
        
    Raises:
        FileNotFoundError: If the schema file doesn't exist at the expected location.
            The error message includes the full path that was checked and the
            schema directory for debugging.
            
        json.JSONDecodeError: If the schema file exists but contains invalid JSON.
            The error message includes the filename, line number, and character
            position of the JSON syntax error.
            
    Example:
        >>> schema = _load_schema("ghost_post_schema.json")
        >>> schema["$schema"]
        "http://json-schema.org/draft-07/schema#"
        
        >>> _load_schema("missing.json")
        FileNotFoundError: Schema file not found: /app/src/schema/missing.json
    """
    # Construct full path to schema file
    schema_path = SCHEMA_DIR / schema_filename
    
    # Check if file exists before attempting to open
    # This provides a more helpful error message than letting open() fail
    if not schema_path.exists():
        raise FileNotFoundError(
            f"Schema file not found: {schema_path}. "
            f"Expected location: {SCHEMA_DIR}"
        )
    
    # Load and parse JSON file
    try:
        with open(schema_path, "r") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        # Re-raise with more context about which file failed
        # Include the original error details (message, position)
        raise json.JSONDecodeError(
            f"Invalid JSON in schema file {schema_filename}: {e.msg}",
            e.doc,
            e.pos
        ) from e


# Load schemas at module import time
# This executes when "import schema" or "from schema import X" is called
# The schema is loaded once and cached in memory as a module-level constant

# Ghost Post Schema
# JSON Schema (Draft 7) for validating Ghost blog post objects
# Contains required fields (id, title, slug, content, url, timestamps)
# and optional fields (tags, authors, featured status, meta fields)
GHOST_POST_SCHEMA = _load_schema("ghost_post_schema.json")


def get_ghost_post_schema() -> Dict[str, Any]:
    """
    Get the Ghost post JSON schema.
    
    This function provides an alternative way to access the Ghost post schema.
    Most code should use the direct import:
        from schema import GHOST_POST_SCHEMA
        
    But this function is useful for:
    - Dynamic schema selection
    - Mocking in tests
    - Explicit function calls when preferred for readability
    
    The returned schema is the same object as GHOST_POST_SCHEMA constant,
    so there's no performance difference or additional I/O.
    
    Returns:
        Ghost post JSON schema as a dictionary containing:
        - $schema: Version identifier (JSON Schema Draft 7)
        - $id: Schema identifier URL
        - title: Human-readable schema name
        - description: Schema purpose
        - type: Root type (always "object")
        - properties: Field definitions with types and constraints
        - required: List of mandatory field names
        
    Example:
        >>> schema = get_ghost_post_schema()
        >>> schema["title"]
        "Ghost Post"
        >>> "id" in schema["required"]
        True
        >>> schema["properties"]["title"]["type"]
        "string"
    """
    return GHOST_POST_SCHEMA
