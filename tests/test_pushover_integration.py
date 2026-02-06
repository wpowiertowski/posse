"""Integration test for Pushover notification delivery."""

import os
from pathlib import Path

import pytest

from config import load_config, read_secret_file
from notifications.pushover import PushoverNotifier


def _read_credentials():
    """Read credentials from configured secret files or env vars for local runs."""
    config = load_config()
    pushover_config = config.get("pushover", {})

    if not pushover_config.get("enabled", False):
        return None, None, False

    app_token_file = pushover_config.get("app_token_file", "/run/secrets/pushover_app_token")
    user_key_file = pushover_config.get("user_key_file", "/run/secrets/pushover_user_key")

    app_token = read_secret_file(app_token_file)
    user_key = read_secret_file(user_key_file)

    if not app_token and Path("secrets/pushover_app_token.txt").exists():
        app_token = read_secret_file("secrets/pushover_app_token.txt")
    if not user_key and Path("secrets/pushover_user_key.txt").exists():
        user_key = read_secret_file("secrets/pushover_user_key.txt")

    app_token = app_token or os.environ.get("PUSHOVER_APP_TOKEN")
    user_key = user_key or os.environ.get("PUSHOVER_USER_KEY")

    return app_token, user_key, True


def test_send_dummy_test_notification():
    """Send one real dummy test notification when credentials are available."""
    app_token, user_key, enabled = _read_credentials()

    if not enabled:
        pytest.skip("Pushover notifications are disabled in config.yml")

    if not app_token or not user_key:
        pytest.skip(
            "Pushover secrets unavailable. Configure secrets or env vars to run integration test."
        )

    notifier = PushoverNotifier(app_token=app_token, user_key=user_key, config_enabled=True)

    assert notifier.send_test_notification() is True
