"""
Configuration Module for POSSE.

This module provides configuration loading and management for the POSSE application.
Configuration is loaded from config.yml and supports Docker secrets.

Usage:
    >>> from config import load_config
    >>> config = load_config()
    >>> if config.get("pushover", {}).get("enabled"):
    ...     # Use Pushover notifications
"""
import os
import yaml
import logging
from pathlib import Path
from typing import Dict, Any, Optional


logger = logging.getLogger(__name__)


def load_config(config_path: Optional[str] = None) -> Dict[str, Any]:
    """Load configuration from config.yml file.
    
    Args:
        config_path: Path to config.yml file. If None, looks in current directory
                    and parent directories.
                    
    Returns:
        Dictionary containing configuration settings
        
    Raises:
        FileNotFoundError: If config.yml is not found
        yaml.YAMLError: If config.yml is not valid YAML
        
    Example:
        >>> config = load_config()
        >>> pushover_enabled = config.get("pushover", {}).get("enabled", False)
    """
    if config_path is None:
        # Try to find config.yml in current directory or parent directories
        current = Path.cwd()
        for parent in [current] + list(current.parents):
            candidate = parent / "config.yml"
            if candidate.exists():
                config_path = str(candidate)
                break
        
        # If still not found, check the project root (where this file is located)
        if config_path is None:
            project_root = Path(__file__).parent.parent.parent
            candidate = project_root / "config.yml"
            if candidate.exists():
                config_path = str(candidate)
    
    if config_path is None:
        logger.warning("config.yml not found, using default configuration")
        return get_default_config()
    
    try:
        with open(config_path, "r") as f:
            config = yaml.safe_load(f)
            logger.info(f"Loaded configuration from {config_path}")
            return config or {}
    except FileNotFoundError:
        logger.warning(f"Configuration file not found: {config_path}")
        return get_default_config()
    except yaml.YAMLError as e:
        logger.error(f"Error parsing configuration file: {e}")
        return get_default_config()


def get_default_config() -> Dict[str, Any]:
    """Return default configuration when config.yml is not available.

    Returns:
        Dictionary with default configuration values
    """
    return {
        "cors": {
            "enabled": False,
            "origins": []
        },
        "pushover": {
            "enabled": False,
            "app_token_file": "/run/secrets/pushover_app_token",
            "user_key_file": "/run/secrets/pushover_user_key"
        }
    }


def read_secret_file(filepath: str) -> Optional[str]:
    """Read a Docker secret from a file.
    
    Docker secrets are mounted as files in /run/secrets/ directory.
    This function reads the content of the secret file.
    
    Args:
        filepath: Path to the secret file
        
    Returns:
        Content of the secret file (stripped of whitespace), or None if file doesn't exist
        
    Example:
        >>> token = read_secret_file("/run/secrets/pushover_app_token")
    """
    try:
        with open(filepath, "r") as f:
            return f.read().strip()
    except FileNotFoundError:
        logger.debug(f"Secret file not found: {filepath}")
        return None
    except Exception as e:
        logger.error(f"Error reading secret file {filepath}: {e}")
        return None
