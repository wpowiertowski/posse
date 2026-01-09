"""
Unit Tests for Configuration Module.

This test suite validates the configuration loading functionality.
"""
import os
import pytest
import tempfile
from pathlib import Path
from unittest.mock import patch

from config import load_config, get_default_config, read_secret_file


def test_get_default_config():
    """Test default configuration values."""
    config = get_default_config()
    
    assert "pushover" in config
    assert config["pushover"]["enabled"] is False
    assert config["pushover"]["app_token_file"] == "/run/secrets/pushover_app_token"
    assert config["pushover"]["user_key_file"] == "/run/secrets/pushover_user_key"


def test_load_config_from_project_root():
    """Test loading config.yml from project root."""
    config = load_config()
    
    # Should load the actual config.yml from project root
    assert "pushover" in config
    assert "enabled" in config["pushover"]


def test_load_config_with_explicit_path():
    """Test loading config from explicit path."""
    # Create a temporary config file
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False) as f:
        f.write("""
pushover:
  enabled: true
  app_token_file: /custom/path/token
  user_key_file: /custom/path/key
""")
        temp_path = f.name
    
    try:
        config = load_config(temp_path)
        assert config["pushover"]["enabled"] is True
        assert config["pushover"]["app_token_file"] == "/custom/path/token"
    finally:
        os.unlink(temp_path)


def test_load_config_file_not_found():
    """Test loading config when file doesn't exist."""
    config = load_config("/nonexistent/path/config.yml")
    
    # Should return default config
    assert config == get_default_config()


def test_read_secret_file_success():
    """Test reading a Docker secret file."""
    # Create a temporary secret file
    with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
        f.write("test_secret_value\n")
        temp_path = f.name
    
    try:
        secret = read_secret_file(temp_path)
        assert secret == "test_secret_value"  # Should be stripped
    finally:
        os.unlink(temp_path)


def test_read_secret_file_not_found():
    """Test reading a secret file that doesn't exist."""
    secret = read_secret_file("/nonexistent/secret/file")
    assert secret is None


def test_read_secret_file_with_whitespace():
    """Test that secret content is stripped of whitespace."""
    # Create a temporary secret file with extra whitespace
    with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
        f.write("  test_secret  \n\n")
        temp_path = f.name
    
    try:
        secret = read_secret_file(temp_path)
        assert secret == "test_secret"
    finally:
        os.unlink(temp_path)
