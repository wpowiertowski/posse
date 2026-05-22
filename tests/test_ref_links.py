"""Tests for ?ref= query parameter on syndicated post URLs.

Ghost analytics uses the `ref` query parameter to attribute incoming
traffic to a referrer. POSSE appends `?ref=<platform>` to the post URL
in the syndicated content so Ghost can distinguish visits coming from
Mastodon vs Bluesky vs other sources.
"""
import unittest

from posse.posse import _add_ref_to_url, _format_post_content


class TestAddRefToUrl(unittest.TestCase):
    """Tests for _add_ref_to_url helper."""

    def test_appends_ref_to_plain_url(self):
        result = _add_ref_to_url("https://example.com/post", "mastodon")
        self.assertEqual(result, "https://example.com/post?ref=mastodon")

    def test_appends_ref_when_existing_query_present(self):
        result = _add_ref_to_url("https://example.com/post?utm_source=foo", "bluesky")
        self.assertEqual(result, "https://example.com/post?utm_source=foo&ref=bluesky")

    def test_preserves_existing_ref(self):
        url = "https://example.com/post?ref=newsletter"
        result = _add_ref_to_url(url, "mastodon")
        self.assertEqual(result, url)

    def test_preserves_fragment(self):
        result = _add_ref_to_url("https://example.com/post#section", "mastodon")
        self.assertEqual(result, "https://example.com/post?ref=mastodon#section")

    def test_empty_url_returns_unchanged(self):
        self.assertEqual(_add_ref_to_url("", "mastodon"), "")

    def test_empty_ref_returns_unchanged(self):
        url = "https://example.com/post"
        self.assertEqual(_add_ref_to_url(url, ""), url)


class TestFormatPostContentRef(unittest.TestCase):
    """Tests for ref parameter in _format_post_content."""

    def test_ref_appended_to_post_url(self):
        content = _format_post_content(
            post_title="Test",
            post_url="https://example.com/post",
            excerpt="An excerpt",
            tags=[],
            max_length=500,
            ref="mastodon",
        )
        self.assertIn("https://example.com/post?ref=mastodon", content)

    def test_no_ref_leaves_url_unchanged(self):
        content = _format_post_content(
            post_title="Test",
            post_url="https://example.com/post",
            excerpt="An excerpt",
            tags=[],
            max_length=500,
        )
        self.assertIn("https://example.com/post", content)
        self.assertNotIn("ref=", content)

    def test_different_platforms_get_different_refs(self):
        mastodon_content = _format_post_content(
            post_title="Test",
            post_url="https://example.com/post",
            excerpt="An excerpt",
            tags=[],
            max_length=500,
            ref="mastodon",
        )
        bluesky_content = _format_post_content(
            post_title="Test",
            post_url="https://example.com/post",
            excerpt="An excerpt",
            tags=[],
            max_length=500,
            ref="bluesky",
        )
        self.assertIn("?ref=mastodon", mastodon_content)
        self.assertIn("?ref=bluesky", bluesky_content)

    def test_ref_counts_against_max_length(self):
        # Long excerpt should be trimmed to fit ref= addition
        long_excerpt = "x" * 1000
        content = _format_post_content(
            post_title="Test",
            post_url="https://example.com/post",
            excerpt=long_excerpt,
            tags=[],
            max_length=200,
            ref="mastodon",
        )
        self.assertLessEqual(len(content), 200)
        self.assertIn("?ref=mastodon", content)


if __name__ == "__main__":
    unittest.main()
