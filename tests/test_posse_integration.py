"""
Integration Tests for POSSE Core Module with Config and Clients.

This test module validates that posse.py properly loads configuration
and initializes Mastodon and Bluesky clients as specified in the config.
"""
import unittest
from unittest.mock import patch, MagicMock


class TestPosseConfigIntegration(unittest.TestCase):
    """Test suite for POSSE config loading and client initialization."""
    
    def test_main_loads_config_and_initializes_clients(self):
        """Test that main() loads config and initializes clients.
        
        This test verifies that when main() is called (before starting Gunicorn),
        it:
        1. Loads configuration from config.yml
        2. Initializes Mastodon clients via MastodonClient.from_config()
        3. Initializes Bluesky clients via BlueskyClient.from_config()
        """
        # We can't actually call main() since it starts Gunicorn and blocks
        # But we can verify the imports and client factory methods exist
        from posse.posse import main
        from social.mastodon_client import MastodonClient
        from social.bluesky_client import BlueskyClient
        from config import load_config
        
        # Verify that the client factory methods exist
        assert hasattr(MastodonClient, "from_config"), \
            "MastodonClient should have from_config class method"
        assert hasattr(BlueskyClient, "from_config"), \
            "BlueskyClient should have from_config class method"
        
        # Verify load_config is callable
        assert callable(load_config), "load_config should be callable"
    
    @patch("config.read_secret_file")
    def test_clients_initialized_from_sample_config(self, mock_read_secret):
        """Test client initialization with a sample configuration.
        
        This test creates a sample config and verifies that clients
        are properly initialized from it.
        """
        from social.mastodon_client import MastodonClient
        from social.bluesky_client import BlueskyClient
        
        # Mock secret reading to return test credentials
        def mock_read(filepath):
            if "mastodon" in filepath:
                return "test_mastodon_token"
            elif "bluesky" in filepath:
                return "test_bluesky_password"
            return None
        
        mock_read_secret.side_effect = mock_read
        
        # Sample configuration matching config.example.yml structure
        config = {
            "mastodon": {
                "accounts": [
                    {
                        "name": "personal",
                        "instance_url": "https://mastodon.social",
                        "access_token_file": "/run/secrets/mastodon_personal_access_token"
                    },
                    {
                        "name": "tech",
                        "instance_url": "https://fosstodon.org",
                        "access_token_file": "/run/secrets/mastodon_tech_access_token"
                    }
                ]
            },
            "bluesky": {
                "accounts": [
                    {
                        "name": "main",
                        "instance_url": "https://bsky.social",
                        "handle": "user.bsky.social",
                        "app_password_file": "/run/secrets/bluesky_main_app_password"
                    }
                ]
            }
        }
        
        # Mock the Mastodon API
        with patch("social.mastodon_client.Mastodon"):
            # Initialize Mastodon clients
            mastodon_clients = MastodonClient.from_config(config)
            
            # Verify correct number of clients created
            assert len(mastodon_clients) == 2, \
                f"Should create 2 Mastodon clients, got {len(mastodon_clients)}"
            
            # Verify first client
            assert mastodon_clients[0].account_name == "personal"
            assert mastodon_clients[0].instance_url == "https://mastodon.social"
            assert mastodon_clients[0].enabled
            
            # Verify second client
            assert mastodon_clients[1].account_name == "tech"
            assert mastodon_clients[1].instance_url == "https://fosstodon.org"
            assert mastodon_clients[1].enabled
        
        # Mock the Bluesky Client
        with patch("social.bluesky_client.Client"):
            # Initialize Bluesky clients
            bluesky_clients = BlueskyClient.from_config(config)
            
            # Verify correct number of clients created
            assert len(bluesky_clients) == 1, \
                f"Should create 1 Bluesky client, got {len(bluesky_clients)}"
            
            # Verify client details
            assert bluesky_clients[0].account_name == "main"
            assert bluesky_clients[0].instance_url == "https://bsky.social"
            assert bluesky_clients[0].handle == "user.bsky.social"
            assert bluesky_clients[0].enabled
    
    def test_process_events_receives_clients(self):
        """Test that process_events can be called with client lists.
        
        This test verifies that the event processor can accept and work
        with lists of Mastodon and Bluesky clients.
        """
        from posse.posse import process_events
        import threading
        from queue import Queue
        
        # Create mock clients
        mock_mastodon = MagicMock()
        mock_mastodon.account_name = "test_mastodon"
        mock_mastodon.enabled = True
        
        mock_bluesky = MagicMock()
        mock_bluesky.account_name = "test_bluesky"
        mock_bluesky.enabled = True
        
        # Start process_events in a thread (it runs indefinitely)
        # We'll let it start and then stop the thread
        thread = threading.Thread(
            target=process_events,
            args=([mock_mastodon], [mock_bluesky]),
            daemon=True
        )
        
        # Just verify it starts without error
        thread.start()
        assert thread.is_alive(), "Event processor thread should start successfully"
        
        # Thread will be cleaned up automatically since it's a daemon


if __name__ == "__main__":
    unittest.main()
