"""
Unit Tests for Post Filtering Module.

This test suite validates the filtering functionality for Ghost posts.
"""
import unittest

from social.filters import matches_filters, get_matching_accounts


class TestPostFilters(unittest.TestCase):
    """Test suite for post filtering functions."""
    
    def setUp(self):
        """Set up test fixtures."""
        # Sample Ghost post with various attributes
        self.sample_post = {
            "post": {
                "current": {
                    "id": "test123",
                    "title": "Test Post",
                    "tags": [
                        {"id": "1", "name": "Tech", "slug": "tech"},
                        {"id": "2", "name": "Programming", "slug": "programming"}
                    ],
                    "visibility": "public",
                    "featured": True,
                    "status": "published"
                }
            }
        }
        
        # Post with no tags
        self.post_no_tags = {
            "post": {
                "current": {
                    "id": "test456",
                    "title": "No Tags Post",
                    "tags": [],
                    "visibility": "public",
                    "featured": False,
                    "status": "published"
                }
            }
        }
        
        # Private post
        self.private_post = {
            "post": {
                "current": {
                    "id": "test789",
                    "title": "Private Post",
                    "tags": [{"id": "1", "name": "Personal", "slug": "personal"}],
                    "visibility": "members",
                    "featured": False,
                    "status": "published"
                }
            }
        }
    
    def test_empty_filters_match_all(self):
        """Test that empty filters match all posts."""
        self.assertTrue(matches_filters(self.sample_post, {}))
        self.assertTrue(matches_filters(self.post_no_tags, {}))
        self.assertTrue(matches_filters(self.private_post, {}))
    
    def test_tag_filter_matches(self):
        """Test tag filtering with matching tags."""
        filters = {"tags": ["tech", "programming"]}
        self.assertTrue(matches_filters(self.sample_post, filters))
        
        # Should match if ANY tag matches
        filters = {"tags": ["tech"]}
        self.assertTrue(matches_filters(self.sample_post, filters))
        
        filters = {"tags": ["programming"]}
        self.assertTrue(matches_filters(self.sample_post, filters))
    
    def test_tag_filter_no_match(self):
        """Test tag filtering with non-matching tags."""
        filters = {"tags": ["business", "finance"]}
        self.assertFalse(matches_filters(self.sample_post, filters))
        
        # Post with no tags should not match tag filter
        filters = {"tags": ["tech"]}
        self.assertFalse(matches_filters(self.post_no_tags, filters))
    
    def test_exclude_tags_filter(self):
        """Test exclude_tags filtering."""
        # Should exclude posts with specified tags
        filters = {"exclude_tags": ["tech"]}
        self.assertFalse(matches_filters(self.sample_post, filters))
        
        # Should not exclude if tags don't match
        filters = {"exclude_tags": ["business"]}
        self.assertTrue(matches_filters(self.sample_post, filters))
        
        # exclude_tags takes precedence over tags
        filters = {"tags": ["tech"], "exclude_tags": ["programming"]}
        self.assertFalse(matches_filters(self.sample_post, filters))
    
    def test_visibility_filter(self):
        """Test visibility filtering."""
        # Public post should match public filter
        filters = {"visibility": ["public"]}
        self.assertTrue(matches_filters(self.sample_post, filters))
        
        # Public post should not match members filter
        filters = {"visibility": ["members"]}
        self.assertFalse(matches_filters(self.sample_post, filters))
        
        # Private post should match members filter
        filters = {"visibility": ["members"]}
        self.assertTrue(matches_filters(self.private_post, filters))
        
        # Should match if visibility is in the list
        filters = {"visibility": ["public", "members"]}
        self.assertTrue(matches_filters(self.sample_post, filters))
        self.assertTrue(matches_filters(self.private_post, filters))
    
    def test_featured_filter(self):
        """Test featured filtering."""
        # Featured post should match featured: true filter
        filters = {"featured": True}
        self.assertTrue(matches_filters(self.sample_post, filters))
        self.assertFalse(matches_filters(self.post_no_tags, filters))
        
        # Non-featured post should match featured: false filter
        filters = {"featured": False}
        self.assertFalse(matches_filters(self.sample_post, filters))
        self.assertTrue(matches_filters(self.post_no_tags, filters))
    
    def test_status_filter(self):
        """Test status filtering."""
        # Published post should match published filter
        filters = {"status": ["published"]}
        self.assertTrue(matches_filters(self.sample_post, filters))
        
        # Published post should not match draft filter
        filters = {"status": ["draft"]}
        self.assertFalse(matches_filters(self.sample_post, filters))
        
        # Should match if status is in the list
        filters = {"status": ["draft", "published"]}
        self.assertTrue(matches_filters(self.sample_post, filters))
    
    def test_combined_filters(self):
        """Test multiple filters combined (AND logic)."""
        # All filters must match
        filters = {
            "tags": ["tech"],
            "visibility": ["public"],
            "featured": True,
            "status": ["published"]
        }
        self.assertTrue(matches_filters(self.sample_post, filters))
        
        # If any filter fails, should not match
        filters = {
            "tags": ["tech"],
            "visibility": ["public"],
            "featured": False  # This doesn't match
        }
        self.assertFalse(matches_filters(self.sample_post, filters))
    
    def test_get_matching_accounts_single_match(self):
        """Test getting matching accounts with one match."""
        accounts = [
            {
                "name": "personal",
                "filters": {"tags": ["tech"]}
            },
            {
                "name": "work",
                "filters": {"tags": ["business"]}
            }
        ]
        
        matching = get_matching_accounts(self.sample_post, accounts)
        self.assertEqual(len(matching), 1)
        self.assertEqual(matching[0]["name"], "personal")
    
    def test_get_matching_accounts_multiple_matches(self):
        """Test getting matching accounts with multiple matches."""
        accounts = [
            {
                "name": "personal",
                "filters": {"tags": ["tech"]}
            },
            {
                "name": "all",
                "filters": {}  # Empty filters match all
            }
        ]
        
        matching = get_matching_accounts(self.sample_post, accounts)
        self.assertEqual(len(matching), 2)
        account_names = [acc["name"] for acc in matching]
        self.assertIn("personal", account_names)
        self.assertIn("all", account_names)
    
    def test_get_matching_accounts_no_matches(self):
        """Test getting matching accounts with no matches."""
        accounts = [
            {
                "name": "personal",
                "filters": {"tags": ["business"]}
            },
            {
                "name": "work",
                "filters": {"tags": ["finance"]}
            }
        ]
        
        matching = get_matching_accounts(self.sample_post, accounts)
        self.assertEqual(len(matching), 0)
    
    def test_get_matching_accounts_empty_list(self):
        """Test getting matching accounts with empty account list."""
        matching = get_matching_accounts(self.sample_post, [])
        self.assertEqual(len(matching), 0)


if __name__ == '__main__':
    unittest.main()
