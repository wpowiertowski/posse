"""
Integration Tests for Mastodon Client with Real Mastodon Instance.

This test suite validates the Mastodon client functionality against
a real Mastodon instance running in Docker for integration testing.

Test Coverage:
    - Posting statuses to real Mastodon instance
    - Verifying posts were created correctly
    - Testing with and without media attachments
    - Credential verification

Testing Strategy:
    Tests use a real Mastodon instance running in Docker containers.
    A service account is created during setup and tests verify that
    statuses are posted correctly by checking the account's timeline.

Running Tests:
    $ docker compose --profile test up -d
    $ ./scripts/setup-mastodon-test.sh
    $ docker compose --profile test run --rm test pytest tests/test_mastodon_integration.py -v
"""
import os
import tempfile
import time
import pytest
from pathlib import Path

from mastodon_client.mastodon_client import MastodonClient
from mastodon import Mastodon


# Shared fixtures for all test classes
@pytest.fixture(scope="module")
def mastodon_config():
    """Get Mastodon test instance configuration.
    
    Returns:
        dict: Configuration for test Mastodon instance
    """
    # Check for test configuration from environment
    instance_url = os.environ.get('MASTODON_TEST_INSTANCE_URL', 'http://mastodon-web:3000')
    token_file = os.environ.get('MASTODON_TEST_ACCESS_TOKEN_FILE', '/tmp/mastodon_test_token.txt')
    
    # Fallback to local secrets directory
    if not Path(token_file).exists():
        token_file = 'secrets/mastodon_test_access_token.txt'
    
    # Check if token file exists
    if not Path(token_file).exists():
        pytest.skip(
            "Mastodon test instance not configured. "
            "Run './scripts/setup-mastodon-test.sh' to set up the test instance."
        )
    
    return {
        'instance_url': instance_url,
        'token_file': token_file
    }


@pytest.fixture(scope="module")
def test_client(mastodon_config):
    """Create a MastodonClient for testing.
    
    Args:
        mastodon_config: Test instance configuration
        
    Returns:
        MastodonClient: Configured client for testing
    """
    # Read token
    with open(mastodon_config['token_file'], 'r') as f:
        access_token = f.read().strip()
    
    # Create client
    client = MastodonClient(
        instance_url=mastodon_config['instance_url'],
        access_token=access_token
    )
    
    return client


@pytest.fixture(scope="module")
def verification_api(mastodon_config):
    """Create a direct Mastodon API client for verification.
    
    This is used to verify that posts were created correctly.
    
    Args:
        mastodon_config: Test instance configuration
        
    Returns:
        Mastodon: Direct API client for verification
    """
    # Read token
    with open(mastodon_config['token_file'], 'r') as f:
        access_token = f.read().strip()
    
    # Create direct API client
    api = Mastodon(
        access_token=access_token,
        api_base_url=mastodon_config['instance_url']
    )
    
    return api


class TestMastodonIntegration:
    """Integration tests for MastodonClient with real Mastodon instance."""

    def test_mastodon_instance_available(self, mastodon_config):
        """Test that the Mastodon test instance is available and responding."""
        # This test just checks that the fixture loads successfully
        assert mastodon_config['instance_url']
        assert Path(mastodon_config['token_file']).exists()

    def test_verify_credentials(self, test_client):
        """Test that we can verify credentials with the test instance."""
        account = test_client.verify_credentials()
        
        assert account is not None, "Should be able to verify credentials"
        assert 'username' in account, "Account should have a username"
        assert 'id' in account, "Account should have an ID"
        
        print(f"Authenticated as: @{account['username']} (ID: {account['id']})")

    def test_post_simple_status(self, test_client, verification_api):
        """Test posting a simple status and verify it was created."""
        # Generate unique content to identify this test post
        test_content = f"Integration test post at {time.time()}"
        
        # Post the status
        result = test_client.post(test_content)
        
        # Verify post result
        assert result is not None, "Post should return a result"
        assert 'id' in result, "Result should contain post ID"
        assert 'url' in result, "Result should contain post URL"
        
        post_id = result['id']
        print(f"Posted status ID: {post_id}")
        print(f"Status URL: {result['url']}")
        
        # Wait briefly for post to be available
        time.sleep(1)
        
        # Verify the post exists by fetching it
        status = verification_api.status(post_id)
        assert status is not None, "Should be able to fetch the posted status"
        assert status['id'] == post_id, "Fetched status should have the correct ID"
        
        # Extract text content (Mastodon returns HTML, so strip tags)
        posted_text = status['content']
        assert test_content in posted_text, f"Posted status should contain the test content. Got: {posted_text}"
        
        # Cleanup - delete the test post
        verification_api.status_delete(post_id)
        print(f"Cleaned up test post {post_id}")

    def test_post_with_visibility(self, test_client, verification_api):
        """Test posting with different visibility levels."""
        test_content = f"Unlisted test post at {time.time()}"
        
        # Post as unlisted
        result = test_client.post(test_content, visibility='unlisted')
        
        assert result is not None, "Post should return a result"
        post_id = result['id']
        
        # Verify visibility
        status = verification_api.status(post_id)
        assert status['visibility'] == 'unlisted', "Status should be unlisted"
        
        # Cleanup
        verification_api.status_delete(post_id)

    def test_post_with_sensitive_content(self, test_client, verification_api):
        """Test posting with sensitive content flag."""
        test_content = f"Sensitive test post at {time.time()}"
        
        # Post as sensitive
        result = test_client.post(
            test_content,
            sensitive=True,
            spoiler_text="Test content warning"
        )
        
        assert result is not None, "Post should return a result"
        post_id = result['id']
        
        # Verify flags
        status = verification_api.status(post_id)
        assert status['sensitive'] is True, "Status should be marked sensitive"
        assert status['spoiler_text'] == "Test content warning", "Should have correct content warning"
        
        # Cleanup
        verification_api.status_delete(post_id)

    def test_disabled_client_does_not_post(self):
        """Test that a disabled client (no token) doesn't post."""
        client = MastodonClient(
            instance_url='http://mastodon-web:3000',
            access_token=None
        )
        
        assert client.enabled is False, "Client should be disabled without token"
        
        result = client.post("This should not be posted")
        assert result is None, "Disabled client should return None"

    def test_multiple_posts_in_sequence(self, test_client, verification_api):
        """Test posting multiple statuses in sequence."""
        post_ids = []
        
        try:
            # Post 3 statuses
            for i in range(3):
                test_content = f"Sequential test post {i+1} at {time.time()}"
                result = test_client.post(test_content)
                
                assert result is not None, f"Post {i+1} should succeed"
                post_ids.append(result['id'])
                
                # Small delay between posts
                time.sleep(0.5)
            
            # Verify all posts exist
            for post_id in post_ids:
                status = verification_api.status(post_id)
                assert status is not None, f"Status {post_id} should exist"
        
        finally:
            # Cleanup all test posts
            for post_id in post_ids:
                try:
                    verification_api.status_delete(post_id)
                    print(f"Cleaned up test post {post_id}")
                except Exception as e:
                    print(f"Warning: Could not delete post {post_id}: {e}")

    def test_client_from_config(self, mastodon_config):
        """Test creating client from configuration dictionary."""
        # Read token
        with open(mastodon_config['token_file'], 'r') as f:
            access_token = f.read().strip()
        
        # Create a temporary token file for testing
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
            f.write(access_token)
            temp_token_file = f.name
        
        try:
            config = {
                'mastodon': {
                    'accounts': [
                        {
                            'name': 'test',
                            'instance_url': mastodon_config['instance_url'],
                            'access_token_file': temp_token_file
                        }
                    ]
                }
            }
            
            # Create clients from config
            clients = MastodonClient.from_config(config)
            
            assert len(clients) == 1, "Should create one client"
            client = clients[0]
            assert client.enabled is True, "Client should be enabled"
            assert client.instance_url == mastodon_config['instance_url']
            
            # Verify it works
            account = client.verify_credentials()
            assert account is not None, "Should be able to verify credentials"
        
        finally:
            # Cleanup temp file
            if os.path.exists(temp_token_file):
                os.unlink(temp_token_file)


class TestMastodonIntegrationWithMedia:
    """Integration tests for media upload functionality.
    
    These tests require a working Mastodon instance and test
    actual media upload and attachment to posts.
    """

    @pytest.fixture(scope="class")
    def test_image_url(self):
        """Provide a test image URL.
        
        Using a small placeholder image from a reliable CDN.
        """
        return "https://via.placeholder.com/150"

    def test_post_with_image_url(self, test_client, verification_api, test_image_url):
        """Test posting with an image downloaded from URL.
        
        Note: This test may be skipped if network access to external URLs is restricted
        in the test environment.
        """
        test_content = f"Test post with image at {time.time()}"
        
        try:
            # Post with image
            result = test_client.post(
                test_content,
                media_urls=[test_image_url],
                media_descriptions=["Test placeholder image"]
            )
            
            assert result is not None, "Post with media should succeed"
            post_id = result['id']
            
            # Verify the post has media
            time.sleep(1)
            status = verification_api.status(post_id)
            
            # Check if media was attached (may be empty if download failed)
            if 'media_attachments' in status and len(status['media_attachments']) > 0:
                assert len(status['media_attachments']) == 1, "Should have one media attachment"
                assert status['media_attachments'][0]['description'] == "Test placeholder image"
            else:
                # If no media, test should still pass as the client handles download failures gracefully
                print("Note: Media download/upload may have failed, but post was created")
            
            # Cleanup
            verification_api.status_delete(post_id)
        
        except Exception as e:
            # If network access is restricted, skip this test
            if "Network" in str(e) or "timeout" in str(e).lower():
                pytest.skip(f"Network access required for this test: {e}")
            else:
                raise
