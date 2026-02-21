"""
Unit Tests for Split Multi-Image Posts Feature and Service Tags Filtering.

This test suite validates the split_multi_image_posts configuration option
that allows accounts to split Ghost posts with multiple images into separate
syndicated posts, each containing one image.

It also tests the service tag filtering feature, including:
- #nosplit tag that allows bypassing the split behavior on a per-post basis
- #dont-duplicate-feature tag that is used internally in Ghost templates
  and should not be syndicated to social media

Test Coverage:
    - Configuration loading with split_multi_image_posts option
    - Default behavior (split_multi_image_posts=False)
    - Attribute initialization on client instances
    - Mastodon and Bluesky client support
    - #nosplit tag detection and filtering
    - Bypass split behavior when #nosplit tag is present
    - #dont-duplicate-feature tag exclusion from syndicated content
    - Both service tags excluded from formatted post content
    - Case-insensitive service tag matching
    - Partial tag name matching (similar but not exact tags are preserved)
"""
import unittest
from unittest.mock import patch, MagicMock

from posse.posse import (
    _has_nosplit_tag,
    _filter_nosplit_tag,
    _format_post_content,
    NOSPLIT_TAG,
    NOFEATURE_TAG
)
from social.mastodon_client import MastodonClient
from social.bluesky_client import BlueskyClient
from social.base_client import SocialMediaClient


class ConcreteClient(SocialMediaClient):
    """Concrete implementation of SocialMediaClient for testing."""

    def _initialize_api(self):
        """Mock API initialization."""
        self.api = MagicMock()

    def post(self, content, **kwargs):
        """Mock post method."""
        return {"status": "posted"}

    def verify_credentials(self):
        """Mock verify credentials."""
        return {"username": "test_user"}


class TestSplitMultiImagePostsConfig(unittest.TestCase):
    """Test suite for split_multi_image_posts configuration."""

    def test_base_client_default_split_disabled(self):
        """Test that split_multi_image_posts defaults to False."""
        client = ConcreteClient(
            instance_url="https://example.com",
            access_token="test_token"
        )

        self.assertFalse(client.split_multi_image_posts)

    def test_base_client_split_enabled(self):
        """Test that split_multi_image_posts can be enabled."""
        client = ConcreteClient(
            instance_url="https://example.com",
            access_token="test_token",
            split_multi_image_posts=True
        )

        self.assertTrue(client.split_multi_image_posts)

    @patch("config.read_secret_file")
    @patch("social.mastodon_client.Mastodon")
    def test_mastodon_split_enabled_from_config(self, mock_mastodon, mock_read_secret):
        """Test loading Mastodon config with split_multi_image_posts enabled."""
        mock_read_secret.return_value = "test_token"

        config = {
            "mastodon": {
                "accounts": [
                    {
                        "name": "archive",
                        "instance_url": "https://mastodon.social",
                        "access_token_file": "/run/secrets/mastodon_access_token",
                        "split_multi_image_posts": True
                    }
                ]
            }
        }

        clients = MastodonClient.from_config(config)

        self.assertEqual(len(clients), 1)
        self.assertTrue(clients[0].enabled)
        self.assertTrue(clients[0].split_multi_image_posts)

    @patch("config.read_secret_file")
    @patch("social.mastodon_client.Mastodon")
    def test_mastodon_split_disabled_from_config(self, mock_mastodon, mock_read_secret):
        """Test loading Mastodon config with split_multi_image_posts disabled."""
        mock_read_secret.return_value = "test_token"

        config = {
            "mastodon": {
                "accounts": [
                    {
                        "name": "personal",
                        "instance_url": "https://mastodon.social",
                        "access_token_file": "/run/secrets/mastodon_access_token",
                        "split_multi_image_posts": False
                    }
                ]
            }
        }

        clients = MastodonClient.from_config(config)

        self.assertEqual(len(clients), 1)
        self.assertTrue(clients[0].enabled)
        self.assertFalse(clients[0].split_multi_image_posts)

    @patch("config.read_secret_file")
    @patch("social.mastodon_client.Mastodon")
    def test_mastodon_split_default_from_config(self, mock_mastodon, mock_read_secret):
        """Test loading Mastodon config without split_multi_image_posts (default)."""
        mock_read_secret.return_value = "test_token"

        config = {
            "mastodon": {
                "accounts": [
                    {
                        "name": "personal",
                        "instance_url": "https://mastodon.social",
                        "access_token_file": "/run/secrets/mastodon_access_token"
                    }
                ]
            }
        }

        clients = MastodonClient.from_config(config)

        self.assertEqual(len(clients), 1)
        self.assertTrue(clients[0].enabled)
        # Should default to False
        self.assertFalse(clients[0].split_multi_image_posts)

    @patch("config.read_secret_file")
    @patch("social.bluesky_client.Client")
    def test_bluesky_split_enabled_from_config(self, mock_client, mock_read_secret):
        """Test loading Bluesky config with split_multi_image_posts enabled."""
        mock_read_secret.return_value = "test_password"

        # Mock the ATProto client
        mock_atproto = MagicMock()
        mock_atproto.me.handle = "test.bsky.social"
        mock_atproto.me.did = "did:plc:test123"
        mock_client.return_value = mock_atproto

        config = {
            "bluesky": {
                "accounts": [
                    {
                        "name": "archive",
                        "instance_url": "https://bsky.social",
                        "handle": "test.bsky.social",
                        "app_password_file": "/run/secrets/bluesky_app_password",
                        "split_multi_image_posts": True
                    }
                ]
            }
        }

        clients = BlueskyClient.from_config(config)

        self.assertEqual(len(clients), 1)
        self.assertTrue(clients[0].enabled)
        self.assertTrue(clients[0].split_multi_image_posts)

    @patch("config.read_secret_file")
    @patch("social.bluesky_client.Client")
    def test_bluesky_split_default_from_config(self, mock_client, mock_read_secret):
        """Test loading Bluesky config without split_multi_image_posts (default)."""
        mock_read_secret.return_value = "test_password"

        # Mock the ATProto client
        mock_atproto = MagicMock()
        mock_atproto.me.handle = "test.bsky.social"
        mock_atproto.me.did = "did:plc:test123"
        mock_client.return_value = mock_atproto

        config = {
            "bluesky": {
                "accounts": [
                    {
                        "name": "main",
                        "instance_url": "https://bsky.social",
                        "handle": "test.bsky.social",
                        "app_password_file": "/run/secrets/bluesky_app_password"
                    }
                ]
            }
        }

        clients = BlueskyClient.from_config(config)

        self.assertEqual(len(clients), 1)
        self.assertTrue(clients[0].enabled)
        # Should default to False
        self.assertFalse(clients[0].split_multi_image_posts)

    @patch("config.read_secret_file")
    @patch("social.mastodon_client.Mastodon")
    def test_multi_account_mixed_split_settings(self, mock_mastodon, mock_read_secret):
        """Test multi-account config with mixed split_multi_image_posts settings."""
        def mock_read_token(filepath):
            if "personal" in filepath:
                return "personal_token"
            elif "archive" in filepath:
                return "archive_token"
            return None

        mock_read_secret.side_effect = mock_read_token

        config = {
            "mastodon": {
                "accounts": [
                    {
                        "name": "personal",
                        "instance_url": "https://mastodon.social",
                        "access_token_file": "/run/secrets/mastodon_personal_access_token",
                        "split_multi_image_posts": False
                    },
                    {
                        "name": "archive",
                        "instance_url": "https://mastodon.archive.org",
                        "access_token_file": "/run/secrets/mastodon_archive_access_token",
                        "split_multi_image_posts": True
                    }
                ]
            }
        }

        clients = MastodonClient.from_config(config)

        # Should return list with two clients
        self.assertEqual(len(clients), 2)

        # First account should have split disabled
        self.assertTrue(clients[0].enabled)
        self.assertEqual(clients[0].account_name, "personal")
        self.assertFalse(clients[0].split_multi_image_posts)

        # Second account should have split enabled
        self.assertTrue(clients[1].enabled)
        self.assertEqual(clients[1].account_name, "archive")
        self.assertTrue(clients[1].split_multi_image_posts)


class TestNosplitTagDetection(unittest.TestCase):
    """Test suite for #nosplit tag detection and filtering."""

    def test_has_nosplit_tag_returns_true_when_present(self):
        """Test that _has_nosplit_tag returns True when #nosplit is in tags."""
        tags = [
            {"name": "#photography", "slug": "hash-photography"},
            {"name": "#nosplit", "slug": "hash-nosplit"},
            {"name": "#posse", "slug": "hash-posse"}
        ]
        self.assertTrue(_has_nosplit_tag(tags))

    def test_has_nosplit_tag_returns_false_when_absent(self):
        """Test that _has_nosplit_tag returns False when #nosplit is not in tags."""
        tags = [
            {"name": "#photography", "slug": "hash-photography"},
            {"name": "#posse", "slug": "hash-posse"}
        ]
        self.assertFalse(_has_nosplit_tag(tags))

    def test_has_nosplit_tag_case_insensitive(self):
        """Test that #nosplit detection is case-insensitive."""
        tags_upper = [{"name": "#NOSPLIT", "slug": "hash-nosplit"}]
        tags_mixed = [{"name": "#NoSplit", "slug": "hash-nosplit"}]

        self.assertTrue(_has_nosplit_tag(tags_upper))
        self.assertTrue(_has_nosplit_tag(tags_mixed))

    def test_has_nosplit_tag_empty_tags(self):
        """Test that _has_nosplit_tag returns False for empty tags list."""
        self.assertFalse(_has_nosplit_tag([]))

    def test_has_nosplit_tag_handles_missing_name(self):
        """Test that _has_nosplit_tag handles tags without name field."""
        tags = [
            {"slug": "hash-nosplit"},  # Missing 'name' field
            {"name": "#photography", "slug": "hash-photography"}
        ]
        self.assertFalse(_has_nosplit_tag(tags))

    def test_filter_nosplit_tag_removes_tag(self):
        """Test that _filter_nosplit_tag removes #nosplit from tags."""
        tags = [
            {"name": "#photography", "slug": "hash-photography"},
            {"name": "#nosplit", "slug": "hash-nosplit"},
            {"name": "#posse", "slug": "hash-posse"}
        ]
        filtered = _filter_nosplit_tag(tags)

        self.assertEqual(len(filtered), 2)
        tag_names = [t["name"] for t in filtered]
        self.assertIn("#photography", tag_names)
        self.assertIn("#posse", tag_names)
        self.assertNotIn("#nosplit", tag_names)

    def test_filter_nosplit_tag_case_insensitive(self):
        """Test that _filter_nosplit_tag is case-insensitive."""
        tags = [
            {"name": "#photography", "slug": "hash-photography"},
            {"name": "#NOSPLIT", "slug": "hash-nosplit"}
        ]
        filtered = _filter_nosplit_tag(tags)

        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]["name"], "#photography")

    def test_filter_nosplit_tag_preserves_other_tags(self):
        """Test that _filter_nosplit_tag doesn't affect tags without #nosplit."""
        tags = [
            {"name": "#photography", "slug": "hash-photography"},
            {"name": "#travel", "slug": "hash-travel"}
        ]
        filtered = _filter_nosplit_tag(tags)

        self.assertEqual(len(filtered), 2)
        self.assertEqual(filtered, tags)

    def test_filter_nosplit_tag_empty_list(self):
        """Test that _filter_nosplit_tag handles empty list."""
        filtered = _filter_nosplit_tag([])
        self.assertEqual(filtered, [])


class TestServiceTagsInPostContent(unittest.TestCase):
    """Test suite for service tags exclusion from formatted post content.

    Service tags are internal tags used for processing control that should
    not be syndicated to social media platforms. Currently includes:
    - #nosplit: Bypasses multi-image post splitting
    - #dont-duplicate-feature: Used internally in Ghost templates
    """

    # --- NOSPLIT_TAG tests ---

    def test_nosplit_tag_excluded_from_hashtags(self):
        """Test that #nosplit is excluded from formatted post hashtags."""
        tags = [
            {"name": "#photography", "slug": "hash-photography"},
            {"name": "#nosplit", "slug": "hash-nosplit"}
        ]
        content = _format_post_content(
            post_title="Test Post",
            post_url="https://example.com/test",
            excerpt="This is a test excerpt",
            tags=tags,
            max_length=500
        )

        self.assertIn("#photography", content)
        self.assertIn("#posse", content)  # Always added
        self.assertNotIn("#nosplit", content)

    def test_nosplit_tag_excluded_mixed_case(self):
        """Test that #nosplit exclusion handles mixed case variations."""
        case_variations = ["#NoSplit", "#NOSPLIT", "#Nosplit", "#noSPLIT"]
        for tag_variant in case_variations:
            with self.subTest(tag_variant=tag_variant):
                tags = [
                    {"name": "#photography", "slug": "hash-photography"},
                    {"name": tag_variant, "slug": "hash-nosplit"}
                ]
                content = _format_post_content(
                    post_title="Test Post",
                    post_url="https://example.com/test",
                    excerpt="This is a test excerpt",
                    tags=tags,
                    max_length=500
                )
                self.assertNotIn("#nosplit", content.lower())

    # --- NOFEATURE_TAG tests ---

    def test_nofeature_tag_excluded_from_hashtags(self):
        """Test that #dont-duplicate-feature is excluded from formatted post hashtags."""
        tags = [
            {"name": "#photography", "slug": "hash-photography"},
            {"name": "#dont-duplicate-feature", "slug": "hash-dont-duplicate-feature"}
        ]
        content = _format_post_content(
            post_title="Test Post",
            post_url="https://example.com/test",
            excerpt="This is a test excerpt",
            tags=tags,
            max_length=500
        )

        self.assertIn("#photography", content)
        self.assertIn("#posse", content)  # Always added
        self.assertNotIn("#dont-duplicate-feature", content)

    def test_nofeature_tag_excluded_mixed_case(self):
        """Test that #dont-duplicate-feature exclusion handles mixed case variations."""
        case_variations = [
            "#Dont-Duplicate-Feature",
            "#DONT-DUPLICATE-FEATURE",
            "#dont-DUPLICATE-feature",
            "#Dont-duplicate-Feature"
        ]
        for tag_variant in case_variations:
            with self.subTest(tag_variant=tag_variant):
                tags = [
                    {"name": "#photography", "slug": "hash-photography"},
                    {"name": tag_variant, "slug": "hash-dont-duplicate-feature"}
                ]
                content = _format_post_content(
                    post_title="Test Post",
                    post_url="https://example.com/test",
                    excerpt="This is a test excerpt",
                    tags=tags,
                    max_length=500
                )
                self.assertNotIn("#dont-duplicate-feature", content.lower())

    # --- Combined service tags tests ---

    def test_both_service_tags_excluded_together(self):
        """Test that both #nosplit and #dont-duplicate-feature are excluded together."""
        tags = [
            {"name": "#photography", "slug": "hash-photography"},
            {"name": "#nosplit", "slug": "hash-nosplit"},
            {"name": "#dont-duplicate-feature", "slug": "hash-dont-duplicate-feature"},
            {"name": "#travel", "slug": "hash-travel"}
        ]
        content = _format_post_content(
            post_title="Test Post",
            post_url="https://example.com/test",
            excerpt="This is a test excerpt",
            tags=tags,
            max_length=500
        )

        # User tags should be present
        self.assertIn("#photography", content)
        self.assertIn("#travel", content)
        self.assertIn("#posse", content)  # Always added
        # Service tags should be excluded
        self.assertNotIn("#nosplit", content)
        self.assertNotIn("#dont-duplicate-feature", content)

    def test_both_service_tags_excluded_mixed_case(self):
        """Test that both service tags with mixed case are excluded together."""
        tags = [
            {"name": "#photography", "slug": "hash-photography"},
            {"name": "#NOSPLIT", "slug": "hash-nosplit"},
            {"name": "#Dont-Duplicate-Feature", "slug": "hash-dont-duplicate-feature"}
        ]
        content = _format_post_content(
            post_title="Test Post",
            post_url="https://example.com/test",
            excerpt="This is a test excerpt",
            tags=tags,
            max_length=500
        )

        self.assertIn("#photography", content)
        self.assertNotIn("#nosplit", content.lower())
        self.assertNotIn("#dont-duplicate-feature", content.lower())

    def test_content_without_service_tags_unchanged(self):
        """Test that content without any service tags includes all hashtags."""
        tags = [
            {"name": "#photography", "slug": "hash-photography"},
            {"name": "#travel", "slug": "hash-travel"}
        ]
        content = _format_post_content(
            post_title="Test Post",
            post_url="https://example.com/test",
            excerpt="This is a test excerpt",
            tags=tags,
            max_length=500
        )

        self.assertIn("#photography", content)
        self.assertIn("#travel", content)
        self.assertIn("#posse", content)

    def test_only_service_tags_results_in_posse_hashtag(self):
        """Test that having only service tags still results in #posse hashtag."""
        tags = [
            {"name": "#nosplit", "slug": "hash-nosplit"},
            {"name": "#dont-duplicate-feature", "slug": "hash-dont-duplicate-feature"}
        ]
        content = _format_post_content(
            post_title="Test Post",
            post_url="https://example.com/test",
            excerpt="This is a test excerpt",
            tags=tags,
            max_length=500
        )

        self.assertIn("#posse", content)
        self.assertNotIn("#nosplit", content)
        self.assertNotIn("#dont-duplicate-feature", content)

    # --- Partial tag match tests (similar but not exact tags should be preserved) ---

    def test_similar_nosplit_tags_not_filtered(self):
        """Test that tags similar to #nosplit are NOT filtered (exact match only)."""
        tags = [
            {"name": "#nosplitter", "slug": "hash-nosplitter"},
            {"name": "#nosplit-extra", "slug": "hash-nosplit-extra"},
            {"name": "#my-nosplit", "slug": "hash-my-nosplit"},
            {"name": "#photography", "slug": "hash-photography"}
        ]
        content = _format_post_content(
            post_title="Test Post",
            post_url="https://example.com/test",
            excerpt="This is a test excerpt",
            tags=tags,
            max_length=500
        )

        # Similar tags should NOT be filtered
        self.assertIn("#nosplitter", content)
        self.assertIn("#nosplit-extra", content)
        self.assertIn("#my-nosplit", content)
        self.assertIn("#photography", content)

    def test_similar_nofeature_tags_not_filtered(self):
        """Test that tags similar to #dont-duplicate-feature are NOT filtered."""
        tags = [
            {"name": "#dont-duplicate-feature-extra", "slug": "hash-feature-extra"},
            {"name": "#my-dont-duplicate-feature", "slug": "hash-my-feature"},
            {"name": "#photography", "slug": "hash-photography"}
        ]
        content = _format_post_content(
            post_title="Test Post",
            post_url="https://example.com/test",
            excerpt="This is a test excerpt",
            tags=tags,
            max_length=500
        )

        # Similar tags should NOT be filtered
        self.assertIn("#dont-duplicate-feature-extra", content)
        self.assertIn("#my-dont-duplicate-feature", content)
        self.assertIn("#photography", content)

    def test_exact_match_filtered_similar_preserved(self):
        """Test exact service tag is filtered but similar tags are preserved."""
        tags = [
            {"name": "#nosplit", "slug": "hash-nosplit"},  # Should be filtered
            {"name": "#nosplitter", "slug": "hash-nosplitter"},  # Should be preserved
            {"name": "#dont-duplicate-feature", "slug": "hash-ddf"},  # Should be filtered
            {"name": "#dont-duplicate-feature-v2", "slug": "hash-ddf-v2"}  # Should be preserved
        ]
        content = _format_post_content(
            post_title="Test Post",
            post_url="https://example.com/test",
            excerpt="This is a test excerpt",
            tags=tags,
            max_length=500
        )

        # Exact matches should be filtered
        self.assertNotIn(" #nosplit ", content)  # Use spaces to ensure exact match check
        self.assertNotIn(" #dont-duplicate-feature ", content)
        # Similar tags should be preserved
        self.assertIn("#nosplitter", content)
        self.assertIn("#dont-duplicate-feature-v2", content)

    # --- Edge case tests ---

    def test_empty_tags_list(self):
        """Test that empty tags list only adds #posse."""
        content = _format_post_content(
            post_title="Test Post",
            post_url="https://example.com/test",
            excerpt="This is a test excerpt",
            tags=[],
            max_length=500
        )

        self.assertIn("#posse", content)

    def test_tags_without_hash_prefix_preserved(self):
        """Test that tags without # prefix are handled gracefully."""
        tags = [
            {"name": "photography", "slug": "photography"},  # No # prefix
            {"name": "#travel", "slug": "hash-travel"}
        ]
        content = _format_post_content(
            post_title="Test Post",
            post_url="https://example.com/test",
            excerpt="This is a test excerpt",
            tags=tags,
            max_length=500
        )

        # Tags without # are excluded from hashtag list by design
        self.assertNotIn("photography", content.split("\n")[1])  # Not in hashtag line
        self.assertIn("#travel", content)
        self.assertIn("#posse", content)

    def test_service_tags_without_hash_prefix_not_special(self):
        """Test that service tag names without # are not filtered (need exact match)."""
        tags = [
            {"name": "nosplit", "slug": "nosplit"},  # No # prefix - not a service tag
            {"name": "#photography", "slug": "hash-photography"}
        ]
        content = _format_post_content(
            post_title="Test Post",
            post_url="https://example.com/test",
            excerpt="This is a test excerpt",
            tags=tags,
            max_length=500
        )

        # 'nosplit' without # is not filtered (but also not in hashtags since no # prefix)
        self.assertIn("#photography", content)


if __name__ == "__main__":
    unittest.main()
