"""
Unit Tests for /api/interactions Endpoint with Discovery.

This test suite validates the /api/interactions/<ghost_post_id> endpoint,
including the automatic discovery feature that searches social media posts
for syndication mappings.

Test Coverage:
    - GET /api/interactions/<ghost_post_id> with existing interaction data
    - GET /api/interactions/<ghost_post_id> with existing syndication mapping
    - GET /api/interactions/<ghost_post_id> with automatic discovery (success)
    - GET /api/interactions/<ghost_post_id> with automatic discovery (failure)
    - Discovery preserves existing mappings

Testing Strategy:
    Uses Flask's test client with mocked social media clients and Ghost API
    to test the endpoint behavior without making actual API calls.

Running Tests:
    $ PYTHONPATH=src python -m pytest tests/test_interactions_endpoint.py -v
"""
import json
import pytest
import tempfile
import shutil
import os
from pathlib import Path
from queue import Queue
from unittest.mock import MagicMock, patch

from ghost.ghost import create_app, clear_rate_limit_caches


@pytest.fixture
def test_dirs():
    """Create temporary directories for test data."""
    test_dir = tempfile.mkdtemp()
    storage_path = os.path.join(test_dir, "interactions")
    mappings_path = os.path.join(test_dir, "syndication_mappings")
    os.makedirs(storage_path, exist_ok=True)
    os.makedirs(mappings_path, exist_ok=True)

    yield {
        "test_dir": test_dir,
        "storage_path": storage_path,
        "mappings_path": mappings_path
    }

    # Cleanup
    shutil.rmtree(test_dir)


@pytest.fixture
def app_with_discovery(test_dirs):
    """Create Flask app with mocked clients for discovery testing."""
    # Clear rate limiting caches to ensure clean state
    clear_rate_limit_caches()

    test_queue = Queue()

    # Mock Ghost API client
    mock_ghost_api = MagicMock()
    mock_ghost_api.enabled = True
    mock_ghost_api.get_post_by_id.return_value = {
        "id": "507f1f77bcf86cd799439008",
        "url": "https://blog.example.com/test-post/"
    }

    # Mock Mastodon client
    mock_mastodon = MagicMock()
    mock_mastodon.enabled = True
    mock_mastodon.account_name = "personal"
    mock_mastodon.get_recent_posts.return_value = []

    # Mock Bluesky client
    mock_bluesky = MagicMock()
    mock_bluesky.enabled = True
    mock_bluesky.account_name = "main"
    mock_bluesky.get_recent_posts.return_value = []

    # Create config with security disabled for these tests
    config = {
        "security": {
            "rate_limit_enabled": False,
            "discovery_rate_limit_enabled": False,
            "allowed_referrers": []  # Disable referrer validation
        }
    }

    # Create app with mocked clients
    app = create_app(
        test_queue,
        config=config,
        mastodon_clients=[mock_mastodon],
        bluesky_clients=[mock_bluesky],
        ghost_api_client=mock_ghost_api
    )

    app.config["TESTING"] = True
    app.config["INTERACTIONS_STORAGE_PATH"] = test_dirs["storage_path"]
    app.config["SYNDICATION_MAPPINGS_PATH"] = test_dirs["mappings_path"]

    return app, mock_mastodon, mock_bluesky, mock_ghost_api, test_dirs


def test_get_interactions_with_existing_data(app_with_discovery):
    """Test GET /api/interactions/<id> returns existing interaction data."""
    app, _, _, _, test_dirs = app_with_discovery

    # Create existing interaction data
    interaction_data = {
        "ghost_post_id": "507f1f77bcf86cd799439001",
        "updated_at": "2026-02-01T10:00:00Z",
        "syndication_links": {
            "mastodon": {
                "personal": {"post_url": "https://mastodon.social/@user/111"}
            },
            "bluesky": {}
        },
        "platforms": {
            "mastodon": {
                "personal": {
                    "status_id": "111",
                    "post_url": "https://mastodon.social/@user/111",
                    "favorites": 5,
                    "reblogs": 2,
                    "replies": 1
                }
            },
            "bluesky": {}
        }
    }

    interaction_file = os.path.join(test_dirs["storage_path"], "507f1f77bcf86cd799439001.json")
    with open(interaction_file, 'w') as f:
        json.dump(interaction_data, f)

    # Test endpoint
    with app.test_client() as client:
        response = client.get("/api/interactions/507f1f77bcf86cd799439001")

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["ghost_post_id"] == "507f1f77bcf86cd799439001"
        assert data["platforms"]["mastodon"]["personal"]["favorites"] == 5


def test_get_interactions_with_mapping_only(app_with_discovery):
    """Test GET /api/interactions/<id> returns syndication links when no interaction data exists."""
    app, _, _, _, test_dirs = app_with_discovery

    # Create syndication mapping without interaction data
    mapping_data = {
        "ghost_post_id": "507f1f77bcf86cd799439002",
        "ghost_post_url": "https://blog.example.com/test/",
        "syndicated_at": "2026-01-01T00:00:00Z",
        "platforms": {
            "mastodon": {
                "personal": {
                    "status_id": "222",
                    "post_url": "https://mastodon.social/@user/222"
                }
            }
        }
    }

    mapping_file = os.path.join(test_dirs["mappings_path"], "507f1f77bcf86cd799439002.json")
    with open(mapping_file, 'w') as f:
        json.dump(mapping_data, f)

    # Test endpoint
    with app.test_client() as client:
        response = client.get("/api/interactions/507f1f77bcf86cd799439002")

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["ghost_post_id"] == "507f1f77bcf86cd799439002"
        assert "Syndication links available" in data["message"]
        assert data["syndication_links"]["mastodon"]["personal"]["post_url"] == "https://mastodon.social/@user/222"


def test_get_interactions_discovers_mastodon_mapping(app_with_discovery):
    """Test GET /api/interactions/<id> discovers mapping from Mastodon posts."""
    app, mock_mastodon, mock_bluesky, mock_ghost_api, test_dirs = app_with_discovery

    # Configure Ghost API mock to return post URL
    mock_ghost_api.get_post_by_id.return_value = {
        "id": "507f1f77bcf86cd799439003",
        "url": "https://blog.example.com/discovered-post/"
    }

    # Configure Mastodon mock to return post with Ghost URL
    mock_mastodon.get_recent_posts.return_value = [
        {
            'id': '333',
            'url': 'https://mastodon.social/@user/333',
            'content': '<p>New blog post: <a href="https://blog.example.com/discovered-post/">Check it out!</a></p>',
            'created_at': '2026-02-01T10:00:00.000Z'
        }
    ]

    # Mock the sync service to avoid actual API calls during sync
    with patch('interactions.interaction_sync.InteractionSyncService.sync_post_interactions') as mock_sync:
        mock_sync.return_value = {
            "ghost_post_id": "507f1f77bcf86cd799439003",
            "updated_at": "2026-02-01T12:00:00Z",
            "syndication_links": {
                "mastodon": {
                    "personal": {"post_url": "https://mastodon.social/@user/333"}
                },
                "bluesky": {}
            },
            "platforms": {
                "mastodon": {
                    "personal": {
                        "status_id": "333",
                        "post_url": "https://mastodon.social/@user/333",
                        "favorites": 0,
                        "reblogs": 0,
                        "replies": 0
                    }
                },
                "bluesky": {}
            }
        }

        # Test endpoint
        with app.test_client() as client:
            response = client.get("/api/interactions/507f1f77bcf86cd799439003")

            # Verify discovery succeeded
            assert response.status_code == 200
            data = json.loads(response.data)
            assert data["ghost_post_id"] == "507f1f77bcf86cd799439003"
            assert "personal" in data["platforms"]["mastodon"]

            # Verify mapping file was created
            mapping_file = os.path.join(test_dirs["mappings_path"], "507f1f77bcf86cd799439003.json")
            assert os.path.exists(mapping_file)

            with open(mapping_file, 'r') as f:
                mapping = json.load(f)
            assert mapping["platforms"]["mastodon"]["personal"]["status_id"] == "333"


def test_get_interactions_discovers_bluesky_mapping(app_with_discovery):
    """Test GET /api/interactions/<id> discovers mapping from Bluesky posts."""
    app, mock_mastodon, mock_bluesky, mock_ghost_api, test_dirs = app_with_discovery

    # Configure Ghost API mock
    mock_ghost_api.get_post_by_id.return_value = {
        "id": "507f1f77bcf86cd799439004",
        "url": "https://blog.example.com/bluesky-post/"
    }

    # Configure Bluesky mock to return post with Ghost URL
    mock_bluesky.get_recent_posts.return_value = [
        {
            'uri': 'at://did:plc:test/app.bsky.feed.post/xyz',
            'cid': 'cidxyz',
            'text': 'New blog post https://blog.example.com/bluesky-post/ check it out!',
            'created_at': '2026-02-01T10:00:00.000Z',
            'url': 'https://bsky.app/profile/user/post/xyz'
        }
    ]

    # Mock the sync service
    with patch('interactions.interaction_sync.InteractionSyncService.sync_post_interactions') as mock_sync:
        mock_sync.return_value = {
            "ghost_post_id": "507f1f77bcf86cd799439004",
            "updated_at": "2026-02-01T12:00:00Z",
            "syndication_links": {
                "mastodon": {},
                "bluesky": {
                    "main": {"post_url": "https://bsky.app/profile/user/post/xyz"}
                }
            },
            "platforms": {
                "mastodon": {},
                "bluesky": {
                    "main": {
                        "post_uri": "at://did:plc:test/app.bsky.feed.post/xyz",
                        "post_url": "https://bsky.app/profile/user/post/xyz",
                        "likes": 0,
                        "reposts": 0,
                        "replies": 0
                    }
                }
            }
        }

        # Test endpoint
        with app.test_client() as client:
            response = client.get("/api/interactions/507f1f77bcf86cd799439004")

            assert response.status_code == 200
            data = json.loads(response.data)
            assert data["ghost_post_id"] == "507f1f77bcf86cd799439004"
            assert "main" in data["platforms"]["bluesky"]


def test_get_interactions_discovery_not_found(app_with_discovery):
    """Test GET /api/interactions/<id> returns 404 when discovery finds nothing."""
    app, mock_mastodon, mock_bluesky, mock_ghost_api, test_dirs = app_with_discovery

    # Configure mocks to return post URL but no matching social posts
    mock_ghost_api.get_post_by_id.return_value = {
        "id": "507f1f77bcf86cd799439005",
        "url": "https://blog.example.com/not-found/"
    }

    mock_mastodon.get_recent_posts.return_value = [
        {
            'id': '999',
            'url': 'https://mastodon.social/@user/999',
            'content': '<p>Different post about something else</p>',
            'created_at': '2026-02-01T10:00:00.000Z'
        }
    ]

    mock_bluesky.get_recent_posts.return_value = [
        {
            'uri': 'at://did:plc:test/app.bsky.feed.post/abc',
            'text': 'Random post about other things',
            'url': 'https://bsky.app/profile/user/post/abc'
        }
    ]

    # Test endpoint
    with app.test_client() as client:
        response = client.get("/api/interactions/507f1f77bcf86cd799439005")

        # Verify 404 returned
        assert response.status_code == 404
        data = json.loads(response.data)
        assert data["ghost_post_id"] == "507f1f77bcf86cd799439005"
        assert "No syndication or interaction data available" in data["message"]


def test_get_interactions_with_existing_mapping_returns_links(app_with_discovery):
    """Test that endpoint returns syndication links when mapping exists without interactions."""
    app, mock_mastodon, mock_bluesky, mock_ghost_api, test_dirs = app_with_discovery

    # Create existing mapping with one Mastodon account (no interaction data)
    existing_mapping = {
        "ghost_post_id": "507f1f77bcf86cd799439006",
        "ghost_post_url": "https://blog.example.com/preserve/",
        "syndicated_at": "2026-01-01T00:00:00Z",
        "platforms": {
            "mastodon": {
                "personal": {
                    "status_id": "111",
                    "post_url": "https://mastodon.social/@user/111"
                }
            }
        }
    }

    mapping_file = os.path.join(test_dirs["mappings_path"], "507f1f77bcf86cd799439006.json")
    with open(mapping_file, 'w') as f:
        json.dump(existing_mapping, f)

    # Test endpoint - should return existing mapping without triggering discovery
    with app.test_client() as client:
        response = client.get("/api/interactions/507f1f77bcf86cd799439006")

        # Should return 200 with syndication links
        assert response.status_code == 200
        data = json.loads(response.data)

        # Verify it returns the existing Mastodon mapping
        assert "mastodon" in data["syndication_links"]
        assert "personal" in data["syndication_links"]["mastodon"]
        assert data["syndication_links"]["mastodon"]["personal"]["post_url"] == "https://mastodon.social/@user/111"

        # Should have message indicating syndication links available
        assert "Syndication links available" in data.get("message", "")


def test_get_interactions_no_ghost_api(app_with_discovery):
    """Test endpoint when Ghost API client is not available."""
    app, mock_mastodon, mock_bluesky, mock_ghost_api, test_dirs = app_with_discovery

    # Disable Ghost API
    mock_ghost_api.enabled = False

    # Test endpoint
    with app.test_client() as client:
        response = client.get("/api/interactions/507f1f77bcf86cd799439007")

        # Should return 404 since discovery can't run without Ghost API
        assert response.status_code == 404
        data = json.loads(response.data)
        assert "No syndication or interaction data available" in data["message"]


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
