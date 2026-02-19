"""
Tests for Pushover notifications on new social interaction replies.

Covers:
- PushoverNotifier.notify_new_social_reply
- PushoverNotifier.notify_new_webmention_reply
- InteractionSyncService._collect_reply_urls
- InteractionSyncService._notify_new_replies
- InteractionSyncService.sync_post_interactions sends notifications for new replies
- Webmention reply Flask endpoint triggers Pushover notification
"""
import json
import pytest
from queue import Queue
from unittest.mock import patch, MagicMock, call

from notifications.pushover import PushoverNotifier
from interactions.interaction_sync import InteractionSyncService
from interactions.storage import InteractionDataStore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_notifier(enabled=True):
    """Return a PushoverNotifier with test credentials (or disabled)."""
    if not enabled:
        return PushoverNotifier(config_enabled=False)
    return PushoverNotifier(app_token="test_token", user_key="test_key")


def _make_reply_preview(url, author="@user@example.com", content="hello"):
    return {"url": url, "author": author, "content": content, "created_at": "2026-01-01T00:00:00Z"}


def _platforms_with_replies(reply_urls):
    """Build a platforms dict containing mastodon reply previews for each URL."""
    previews = [_make_reply_preview(url) for url in reply_urls]
    return {
        "mastodon": {
            "personal": {
                "favorites": 1,
                "reblogs": 0,
                "replies": len(previews),
                "reply_previews": previews,
            }
        },
        "bluesky": {},
    }


# ---------------------------------------------------------------------------
# PushoverNotifier.notify_new_social_reply
# ---------------------------------------------------------------------------

class TestNotifyNewSocialReply:
    @patch("notifications.pushover.requests.post")
    def test_sends_notification_with_correct_fields(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200)
        notifier = _make_notifier()

        result = notifier.notify_new_social_reply(
            platform="Mastodon",
            account_name="personal",
            author="@alice@mastodon.social",
            content_snippet="Great post!",
            reply_url="https://mastodon.social/@alice/123",
        )

        assert result is True
        data = mock_post.call_args[1]["data"]
        assert "Mastodon" in data["title"]
        assert "💬" in data["title"]
        assert "@alice@mastodon.social" in data["message"]
        assert "personal" in data["message"]
        assert "Great post!" in data["message"]
        assert data["url"] == "https://mastodon.social/@alice/123"
        assert data["url_title"] == "View Reply"
        assert data["priority"] == 0

    @patch("notifications.pushover.requests.post")
    def test_truncates_long_content(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200)
        notifier = _make_notifier()

        long_content = "x" * 500
        notifier.notify_new_social_reply(
            platform="Bluesky",
            account_name="main",
            author="@bob.bsky.social",
            content_snippet=long_content,
            reply_url="https://bsky.app/profile/bob/post/abc",
        )

        data = mock_post.call_args[1]["data"]
        # Message should not contain more than 200 chars of the snippet
        assert long_content[:200] in data["message"]
        assert long_content[201:] not in data["message"]

    def test_skipped_when_disabled(self):
        notifier = _make_notifier(enabled=False)
        result = notifier.notify_new_social_reply(
            platform="Mastodon",
            account_name="personal",
            author="@x",
            content_snippet="hi",
            reply_url="https://mastodon.social/@x/1",
        )
        assert result is False


# ---------------------------------------------------------------------------
# PushoverNotifier.notify_new_webmention_reply
# ---------------------------------------------------------------------------

class TestNotifyNewWebmentionReply:
    @patch("notifications.pushover.requests.post")
    def test_sends_notification_with_correct_fields(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200)
        notifier = _make_notifier()

        result = notifier.notify_new_webmention_reply(
            author_name="Carol",
            content_snippet="Really enjoyed this!",
            target_url="https://blog.example.com/my-post/",
        )

        assert result is True
        data = mock_post.call_args[1]["data"]
        assert "💬" in data["title"]
        assert "Webmention" in data["title"]
        assert "Carol" in data["message"]
        assert "Really enjoyed this!" in data["message"]
        assert data["url"] == "https://blog.example.com/my-post/"
        assert data["url_title"] == "View Post"
        assert data["priority"] == 0

    @patch("notifications.pushover.requests.post")
    def test_truncates_long_content(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200)
        notifier = _make_notifier()

        long_content = "y" * 500
        notifier.notify_new_webmention_reply(
            author_name="Dan",
            content_snippet=long_content,
            target_url="https://blog.example.com/post/",
        )

        data = mock_post.call_args[1]["data"]
        assert long_content[:200] in data["message"]
        assert long_content[201:] not in data["message"]

    def test_skipped_when_disabled(self):
        notifier = _make_notifier(enabled=False)
        result = notifier.notify_new_webmention_reply(
            author_name="Eve",
            content_snippet="hi",
            target_url="https://blog.example.com/post/",
        )
        assert result is False


# ---------------------------------------------------------------------------
# InteractionSyncService._collect_reply_urls
# ---------------------------------------------------------------------------

class TestCollectReplyUrls:
    def _make_service(self):
        return InteractionSyncService.__new__(InteractionSyncService)

    def test_empty_platforms(self):
        service = self._make_service()
        result = service._collect_reply_urls({})
        assert result == set()

    def test_collects_mastodon_urls(self):
        service = self._make_service()
        platforms = _platforms_with_replies([
            "https://mastodon.social/@a/1",
            "https://mastodon.social/@b/2",
        ])
        result = service._collect_reply_urls(platforms)
        assert result == {
            "https://mastodon.social/@a/1",
            "https://mastodon.social/@b/2",
        }

    def test_collects_bluesky_urls(self):
        service = self._make_service()
        platforms = {
            "mastodon": {},
            "bluesky": {
                "main": {
                    "reply_previews": [
                        _make_reply_preview("https://bsky.app/profile/x/post/1"),
                    ]
                }
            },
        }
        result = service._collect_reply_urls(platforms)
        assert "https://bsky.app/profile/x/post/1" in result

    def test_skips_replies_without_url(self):
        service = self._make_service()
        platforms = {
            "mastodon": {
                "personal": {
                    "reply_previews": [{"author": "@x", "content": "hi"}],  # no url
                }
            },
            "bluesky": {},
        }
        result = service._collect_reply_urls(platforms)
        assert result == set()


# ---------------------------------------------------------------------------
# InteractionSyncService._notify_new_replies
# ---------------------------------------------------------------------------

class TestNotifyNewReplies:
    def _make_service(self, notifier=None):
        svc = InteractionSyncService.__new__(InteractionSyncService)
        svc.notifier = notifier
        return svc

    def test_no_notifications_when_no_new_replies(self):
        notifier = MagicMock()
        service = self._make_service(notifier)

        prev_urls = {"https://masto/@a/1"}
        new = {"platforms": _platforms_with_replies(["https://masto/@a/1"])}
        service._notify_new_replies(prev_urls, new)

        notifier.notify_new_social_reply.assert_not_called()

    def test_notifies_for_new_mastodon_reply(self):
        notifier = MagicMock()
        service = self._make_service(notifier)

        prev_urls = {"https://masto/@a/1"}
        new = {"platforms": _platforms_with_replies([
            "https://masto/@a/1",
            "https://masto/@b/2",  # new
        ])}
        service._notify_new_replies(prev_urls, new)

        notifier.notify_new_social_reply.assert_called_once()
        kwargs = notifier.notify_new_social_reply.call_args[1]
        assert kwargs["platform"] == "Mastodon"
        assert kwargs["reply_url"] == "https://masto/@b/2"

    def test_notifies_for_new_bluesky_reply(self):
        notifier = MagicMock()
        service = self._make_service(notifier)

        new_url = "https://bsky.app/profile/carol/post/9"
        prev_urls: set = set()
        new = {
            "platforms": {
                "mastodon": {},
                "bluesky": {
                    "main": {
                        "reply_previews": [_make_reply_preview(new_url)],
                    }
                },
            }
        }
        service._notify_new_replies(prev_urls, new)

        notifier.notify_new_social_reply.assert_called_once()
        kwargs = notifier.notify_new_social_reply.call_args[1]
        assert kwargs["platform"] == "Bluesky"
        assert kwargs["reply_url"] == new_url

    def test_multiple_new_replies_each_notified(self):
        notifier = MagicMock()
        service = self._make_service(notifier)

        prev_urls: set = set()
        new = {
            "platforms": _platforms_with_replies([
                "https://masto/@a/1",
                "https://masto/@b/2",
            ])
        }
        service._notify_new_replies(prev_urls, new)

        assert notifier.notify_new_social_reply.call_count == 2

    def test_notification_failure_does_not_raise(self):
        notifier = MagicMock()
        notifier.notify_new_social_reply.side_effect = RuntimeError("boom")
        service = self._make_service(notifier)

        prev_urls: set = set()
        new = {"platforms": _platforms_with_replies(["https://masto/@a/1"])}

        # Should not raise
        service._notify_new_replies(prev_urls, new)


# ---------------------------------------------------------------------------
# InteractionSyncService: notifier wired into sync_post_interactions
# ---------------------------------------------------------------------------

class TestSyncPostInteractionsNotifications:
    """Integration-level test: sync_post_interactions calls the notifier for new replies."""

    def _make_service_with_storage(self, tmp_path, notifier):
        from zoneinfo import ZoneInfo
        svc = InteractionSyncService(
            mastodon_clients=[],
            bluesky_clients=[],
            storage_path=str(tmp_path),
            timezone_name="UTC",
            notifier=notifier,
        )
        return svc

    def test_notification_sent_for_new_reply_on_sync(self, tmp_path):
        notifier = MagicMock()
        svc = self._make_service_with_storage(tmp_path, notifier)

        ghost_post_id = "507f1f77bcf86cd799439011"

        # Store an existing syndication mapping
        existing_mapping = {
            "ghost_post_id": ghost_post_id,
            "ghost_post_url": "https://blog.example.com/post/",
            "syndicated_at": "2026-01-01T00:00:00+00:00",
            "platforms": {
                "mastodon": {
                    "personal": {
                        "status_id": "111",
                        "post_url": "https://mastodon.social/@me/111",
                    }
                },
                "bluesky": {},
            },
        }
        svc.data_store.put_syndication_mapping(ghost_post_id, existing_mapping)

        # Pre-seed an old interaction record with one reply
        old_reply_url = "https://mastodon.social/@old/999"
        old_data = {
            "ghost_post_id": ghost_post_id,
            "updated_at": "2026-01-01T00:00:00+00:00",
            "syndication_links": {"mastodon": {}, "bluesky": {}},
            "platforms": {
                "mastodon": {
                    "personal": {
                        "post_url": "https://mastodon.social/@me/111",
                        "favorites": 0,
                        "reblogs": 0,
                        "replies": 1,
                        "reply_previews": [_make_reply_preview(old_reply_url)],
                    }
                },
                "bluesky": {},
            },
        }
        svc.data_store.put(ghost_post_id, old_data)

        # Mock the mastodon client to return a new reply
        new_reply_url = "https://mastodon.social/@new/888"
        mock_client = MagicMock()
        mock_client.account_name = "personal"
        mock_client.enabled = True

        mock_status = {"favourites_count": 1, "reblogs_count": 0, "replies_count": 2}
        mock_client.api.status.return_value = mock_status
        mock_client.api.status_favourited_by.return_value = []
        mock_client.api.status_reblogged_by.return_value = []
        mock_context = {
            "descendants": [
                {
                    "in_reply_to_id": "111",
                    "account": {
                        "acct": "old",
                        "url": "https://mastodon.social/@old",
                        "avatar": "",
                    },
                    "content": "old reply",
                    "created_at": "2026-01-01T00:00:00Z",
                    "url": old_reply_url,
                },
                {
                    "in_reply_to_id": "111",
                    "account": {
                        "acct": "new",
                        "url": "https://mastodon.social/@new",
                        "avatar": "",
                    },
                    "content": "brand new reply",
                    "created_at": "2026-01-02T00:00:00Z",
                    "url": new_reply_url,
                },
            ]
        }
        mock_client.api.status_context.return_value = mock_context

        svc.mastodon_clients = [mock_client]

        svc.sync_post_interactions(ghost_post_id)

        # The notifier should have been called exactly once for the new reply
        notifier.notify_new_social_reply.assert_called_once()
        call_kwargs = notifier.notify_new_social_reply.call_args[1]
        assert call_kwargs["reply_url"] == new_reply_url
        assert call_kwargs["platform"] == "Mastodon"

    def test_no_notification_sent_when_no_new_replies(self, tmp_path):
        notifier = MagicMock()
        svc = self._make_service_with_storage(tmp_path, notifier)

        ghost_post_id = "507f1f77bcf86cd799439012"

        existing_mapping = {
            "ghost_post_id": ghost_post_id,
            "ghost_post_url": "https://blog.example.com/p/",
            "syndicated_at": "2026-01-01T00:00:00+00:00",
            "platforms": {
                "mastodon": {
                    "personal": {
                        "status_id": "222",
                        "post_url": "https://mastodon.social/@me/222",
                    }
                },
                "bluesky": {},
            },
        }
        svc.data_store.put_syndication_mapping(ghost_post_id, existing_mapping)

        same_reply_url = "https://mastodon.social/@x/100"
        old_data = {
            "ghost_post_id": ghost_post_id,
            "updated_at": "2026-01-01T00:00:00+00:00",
            "syndication_links": {"mastodon": {}, "bluesky": {}},
            "platforms": {
                "mastodon": {
                    "personal": {
                        "post_url": "https://mastodon.social/@me/222",
                        "favorites": 0,
                        "reblogs": 0,
                        "replies": 1,
                        "reply_previews": [_make_reply_preview(same_reply_url)],
                    }
                },
                "bluesky": {},
            },
        }
        svc.data_store.put(ghost_post_id, old_data)

        mock_client = MagicMock()
        mock_client.account_name = "personal"
        mock_client.enabled = True
        mock_client.api.status.return_value = {"favourites_count": 0, "reblogs_count": 0, "replies_count": 1}
        mock_client.api.status_favourited_by.return_value = []
        mock_client.api.status_reblogged_by.return_value = []
        mock_client.api.status_context.return_value = {
            "descendants": [
                {
                    "in_reply_to_id": "222",
                    "account": {"acct": "x", "url": "https://mastodon.social/@x", "avatar": ""},
                    "content": "same reply",
                    "created_at": "2026-01-01T00:00:00Z",
                    "url": same_reply_url,
                }
            ]
        }
        svc.mastodon_clients = [mock_client]

        svc.sync_post_interactions(ghost_post_id)

        notifier.notify_new_social_reply.assert_not_called()


# ---------------------------------------------------------------------------
# Webmention reply Flask endpoint triggers Pushover notification
# ---------------------------------------------------------------------------

class TestWebmentionReplyEndpointNotification:
    """Test that submitting a webmention reply triggers a Pushover notification."""

    @pytest.fixture
    def reply_config(self, tmp_path):
        return {
            "webmention_reply": {
                "enabled": True,
                "blog_name": "Test Blog",
                "allowed_target_origins": ["https://blog.example.com"],
                "rate_limit": 5,
                "rate_limit_window_seconds": 3600,
                "turnstile_site_key": "",
                "turnstile_secret_key": "",
            },
            "interactions": {"cache_directory": str(tmp_path)},
            "cors": {"enabled": False},
            "pushover": {"enabled": False},
        }

    @pytest.fixture
    def ghost_api_client(self):
        client = MagicMock()
        client.enabled = True
        client.get_post_by_slug.side_effect = lambda slug: (
            {"url": f"https://blog.example.com/{slug}/"} if slug == "my-post" else None
        )
        return client

    @pytest.fixture
    def notifier(self):
        return MagicMock()

    @pytest.fixture
    def app(self, reply_config, tmp_path, ghost_api_client, notifier):
        from ghost.ghost import create_app, clear_rate_limit_caches
        clear_rate_limit_caches()
        q = Queue()
        flask_app = create_app(q, config=reply_config, ghost_api_client=ghost_api_client, notifier=notifier)
        flask_app.config["INTERACTIONS_STORAGE_PATH"] = str(tmp_path)
        flask_app.config["TESTING"] = True
        return flask_app

    def test_notification_sent_on_reply_submission(self, app, notifier):
        from ghost.ghost import clear_rate_limit_caches
        clear_rate_limit_caches()
        client = app.test_client()
        payload = {
            "author_name": "Fiona",
            "author_url": "https://fiona.example.com",
            "content": "Love this article!",
            "target": "https://blog.example.com/my-post/",
            "website": "",
        }
        with patch("indieweb.webmention.send_webmention") as mock_send_wm:
            mock_send_wm.return_value = MagicMock(success=True, message="ok")
            resp = client.post(
                "/api/webmention/reply",
                json=payload,
                content_type="application/json",
            )
        assert resp.status_code == 200, resp.data
        notifier.notify_new_webmention_reply.assert_called_once()
        kwargs = notifier.notify_new_webmention_reply.call_args[1]
        assert kwargs["author_name"] == "Fiona"
        assert "Love this article!" in kwargs["content_snippet"]
        assert kwargs["target_url"] == "https://blog.example.com/my-post/"

    def test_notification_not_sent_for_honeypot_submission(self, app, notifier):
        from ghost.ghost import clear_rate_limit_caches
        clear_rate_limit_caches()
        client = app.test_client()
        payload = {
            "author_name": "Bot",
            "content": "spam",
            "target": "https://blog.example.com/my-post/",
            "website": "http://spam.example.com",  # honeypot filled
        }
        with patch("indieweb.webmention.send_webmention") as mock_send_wm:
            mock_send_wm.return_value = MagicMock(success=True, message="ok")
            resp = client.post(
                "/api/webmention/reply",
                json=payload,
                content_type="application/json",
            )
        # Honeypot replies return 200 (silent accept) but should NOT be stored or notified
        assert resp.status_code == 200
        notifier.notify_new_webmention_reply.assert_not_called()
