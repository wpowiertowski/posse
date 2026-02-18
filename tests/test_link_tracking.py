"""
Tests for webmention link tracking and re-sending.

Covers:
- Outbound link extraction from post HTML
- Link diff computation for updates
- Sent webmention storage (record, query, delete)
- Post-deleted webhook endpoint

Running Tests:
    $ PYTHONPATH=src python -m pytest tests/test_link_tracking.py -v
"""
import json
import pytest
from queue import Queue
from unittest.mock import patch, MagicMock

from indieweb.link_tracking import extract_outbound_links, compute_webmention_diff
from interactions.storage import InteractionDataStore


# =========================================================================
# Unit Tests: Link Extraction
# =========================================================================

class TestExtractOutboundLinks:
    def test_extracts_external_links(self):
        html = '''
        <p>Check out <a href="https://example.com/post">this post</a> and
        <a href="https://other.org/article">this article</a>.</p>
        '''
        links = extract_outbound_links(html, "https://myblog.com")
        assert "https://example.com/post" in links
        assert "https://other.org/article" in links

    def test_excludes_self_links(self):
        html = '<p><a href="https://myblog.com/about">About</a></p>'
        links = extract_outbound_links(html, "https://myblog.com")
        assert len(links) == 0

    def test_excludes_self_links_case_insensitive(self):
        html = '<p><a href="https://MyBlog.COM/about">About</a></p>'
        links = extract_outbound_links(html, "https://myblog.com")
        assert len(links) == 0

    def test_excludes_mailto_links(self):
        html = '<p><a href="mailto:test@example.com">Email</a></p>'
        links = extract_outbound_links(html, "https://myblog.com")
        assert len(links) == 0

    def test_excludes_javascript_links(self):
        html = '<p><a href="javascript:alert(1)">Click</a></p>'
        links = extract_outbound_links(html, "https://myblog.com")
        assert len(links) == 0

    def test_excludes_fragment_only(self):
        html = '<p><a href="#section">Jump</a></p>'
        links = extract_outbound_links(html, "https://myblog.com")
        assert len(links) == 0

    def test_excludes_empty_href(self):
        html = '<p><a href="">Empty</a></p>'
        links = extract_outbound_links(html, "https://myblog.com")
        assert len(links) == 0

    def test_strips_fragments_from_links(self):
        html = '<p><a href="https://example.com/post#comments">Post</a></p>'
        links = extract_outbound_links(html, "https://myblog.com")
        assert "https://example.com/post" in links

    def test_preserves_query_params(self):
        html = '<p><a href="https://example.com/search?q=test">Search</a></p>'
        links = extract_outbound_links(html, "https://myblog.com")
        assert "https://example.com/search?q=test" in links

    def test_deduplicates_links(self):
        html = '''
        <p><a href="https://example.com/post">First</a>
        <a href="https://example.com/post">Second</a></p>
        '''
        links = extract_outbound_links(html, "https://myblog.com")
        assert len(links) == 1

    def test_empty_html(self):
        links = extract_outbound_links("", "https://myblog.com")
        assert len(links) == 0

    def test_no_links_in_html(self):
        html = "<p>Just some text, no links.</p>"
        links = extract_outbound_links(html, "https://myblog.com")
        assert len(links) == 0

    def test_excludes_relative_links(self):
        html = '<p><a href="/about">About</a></p>'
        links = extract_outbound_links(html, "https://myblog.com")
        assert len(links) == 0

    def test_multiple_external_domains(self):
        html = '''
        <a href="https://a.com/1">A</a>
        <a href="https://b.com/2">B</a>
        <a href="https://c.com/3">C</a>
        <a href="https://myblog.com/self">Self</a>
        '''
        links = extract_outbound_links(html, "https://myblog.com")
        assert len(links) == 3
        assert "https://a.com/1" in links
        assert "https://b.com/2" in links
        assert "https://c.com/3" in links


# =========================================================================
# Unit Tests: Link Diff
# =========================================================================

class TestComputeWebmentionDiff:
    def test_new_links_only(self):
        current = {"https://a.com/1", "https://b.com/2"}
        previous = set()
        targets, removed = compute_webmention_diff(current, previous)
        assert targets == {"https://a.com/1", "https://b.com/2"}
        assert removed == set()

    def test_removed_links_included(self):
        current = {"https://a.com/1"}
        previous = {"https://a.com/1", "https://b.com/2"}
        targets, removed = compute_webmention_diff(current, previous)
        assert "https://b.com/2" in targets
        assert "https://a.com/1" in targets
        assert removed == {"https://b.com/2"}

    def test_all_links_removed(self):
        current = set()
        previous = {"https://a.com/1", "https://b.com/2"}
        targets, removed = compute_webmention_diff(current, previous)
        assert targets == {"https://a.com/1", "https://b.com/2"}
        assert removed == {"https://a.com/1", "https://b.com/2"}

    def test_no_change(self):
        links = {"https://a.com/1", "https://b.com/2"}
        targets, removed = compute_webmention_diff(links, links)
        assert targets == links
        assert removed == set()

    def test_both_added_and_removed(self):
        current = {"https://a.com/1", "https://c.com/3"}
        previous = {"https://a.com/1", "https://b.com/2"}
        targets, removed = compute_webmention_diff(current, previous)
        assert targets == {"https://a.com/1", "https://b.com/2", "https://c.com/3"}
        assert removed == {"https://b.com/2"}

    def test_both_empty(self):
        targets, removed = compute_webmention_diff(set(), set())
        assert targets == set()
        assert removed == set()


# =========================================================================
# Unit Tests: Sent Webmention Storage
# =========================================================================

class TestSentWebmentionStorage:
    @pytest.fixture
    def store(self, tmp_path):
        return InteractionDataStore(str(tmp_path))

    def test_record_and_retrieve(self, store):
        store.record_sent_webmention(
            source_url="https://myblog.com/post-1",
            target_url="https://example.com/article",
            post_id="abc123",
            endpoint="https://example.com/webmention",
        )
        targets = store.get_sent_webmention_targets("https://myblog.com/post-1")
        assert targets == ["https://example.com/article"]

    def test_retrieve_by_post_id(self, store):
        store.record_sent_webmention(
            source_url="https://myblog.com/post-1",
            target_url="https://a.com/1",
            post_id="abc123",
        )
        store.record_sent_webmention(
            source_url="https://myblog.com/post-1",
            target_url="https://b.com/2",
            post_id="abc123",
        )
        targets = store.get_sent_webmention_targets_by_post_id("abc123")
        assert set(targets) == {"https://a.com/1", "https://b.com/2"}

    def test_upsert_updates_timestamp(self, store):
        store.record_sent_webmention(
            source_url="https://myblog.com/post-1",
            target_url="https://example.com/article",
            post_id="abc123",
            sent_at="2026-01-01T00:00:00+00:00",
        )
        store.record_sent_webmention(
            source_url="https://myblog.com/post-1",
            target_url="https://example.com/article",
            post_id="abc123",
            sent_at="2026-02-01T00:00:00+00:00",
        )
        # Should still be one record, not duplicate
        targets = store.get_sent_webmention_targets("https://myblog.com/post-1")
        assert len(targets) == 1

    def test_delete_by_post_id(self, store):
        store.record_sent_webmention(
            source_url="https://myblog.com/post-1",
            target_url="https://a.com/1",
            post_id="abc123",
        )
        store.record_sent_webmention(
            source_url="https://myblog.com/post-1",
            target_url="https://b.com/2",
            post_id="abc123",
        )
        deleted = store.delete_sent_webmentions_for_post("abc123")
        assert deleted == 2
        assert store.get_sent_webmention_targets("https://myblog.com/post-1") == []

    def test_delete_nonexistent(self, store):
        deleted = store.delete_sent_webmentions_for_post("nonexistent")
        assert deleted == 0

    def test_empty_result_for_unknown_source(self, store):
        targets = store.get_sent_webmention_targets("https://unknown.com/post")
        assert targets == []

    def test_different_posts_isolated(self, store):
        store.record_sent_webmention(
            source_url="https://myblog.com/post-1",
            target_url="https://a.com/1",
            post_id="post1",
        )
        store.record_sent_webmention(
            source_url="https://myblog.com/post-2",
            target_url="https://b.com/2",
            post_id="post2",
        )
        assert store.get_sent_webmention_targets("https://myblog.com/post-1") == ["https://a.com/1"]
        assert store.get_sent_webmention_targets("https://myblog.com/post-2") == ["https://b.com/2"]


# =========================================================================
# Integration Tests: Post Deleted Webhook
# =========================================================================

class TestPostDeletedWebhook:
    @pytest.fixture
    def app(self, tmp_path):
        from ghost.ghost import create_app
        config = {
            "webmention": {"enabled": True, "targets": []},
            "interactions": {"cache_directory": str(tmp_path)},
            "cors": {"enabled": False},
            "pushover": {"enabled": False},
        }
        q = Queue()
        app = create_app(q, config=config)
        app.config["TESTING"] = True
        app.config["INTERACTIONS_STORAGE_PATH"] = str(tmp_path)
        return app

    @pytest.fixture
    def client(self, app):
        return app.test_client()

    def test_non_json_rejected(self, client):
        resp = client.post(
            "/webhook/ghost/post-deleted",
            data="not json",
            content_type="text/plain",
        )
        assert resp.status_code == 400

    def test_deletion_without_url(self, client):
        payload = {
            "post": {
                "current": {},
                "previous": {"id": "abc123def456abc123def456", "title": "Test Post"},
            }
        }
        resp = client.post(
            "/webhook/ghost/post-deleted",
            json=payload,
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert "no URL available" in data["message"]

    @patch("indieweb.webmention.send_webmention")
    def test_deletion_sends_webmentions_to_tracked_targets(
        self, mock_send, app, client, tmp_path
    ):
        from indieweb.webmention import WebmentionResult

        # Pre-populate sent webmentions
        store = InteractionDataStore(str(tmp_path))
        store.record_sent_webmention(
            source_url="https://myblog.com/post-1/",
            target_url="https://example.com/article",
            post_id="abc123def456abc123def456",
        )

        mock_send.return_value = WebmentionResult(
            success=True, status_code=200, message="ok"
        )

        payload = {
            "post": {
                "current": {},
                "previous": {
                    "id": "abc123def456abc123def456",
                    "url": "https://myblog.com/post-1/",
                    "title": "Test Post",
                },
            }
        }
        resp = client.post(
            "/webhook/ghost/post-deleted",
            json=payload,
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["targets_count"] == 1

    def test_deletion_with_no_tracked_webmentions(self, client):
        payload = {
            "post": {
                "current": {},
                "previous": {
                    "id": "abc123def456abc123def456",
                    "url": "https://myblog.com/post-1/",
                    "title": "Test Post",
                },
            }
        }
        resp = client.post(
            "/webhook/ghost/post-deleted",
            json=payload,
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert "no webmentions to retract" in data["message"]
