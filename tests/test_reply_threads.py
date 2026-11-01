"""
Tests for capturing reply threads beneath direct replies to syndicated posts.

Covers:
- Mastodon: nested descendants are stored as a ``children`` tree on each reply preview
- Mastodon: followers-only and direct statuses (and their subtrees) are left out of threads
- Bluesky: nested thread replies are stored as ``children``; blocked/not-found are skipped
- InteractionSyncService._build_reply_thread depth and reply caps
"""
from types import SimpleNamespace
from unittest.mock import MagicMock

from interactions import interaction_sync
from interactions.interaction_sync import InteractionSyncService, REPLY_THREAD_MAX_DEPTH


GHOST_POST_ID = "507f1f77bcf86cd799439011"


def _make_service(tmp_path, mastodon_clients=None, bluesky_clients=None):
    return InteractionSyncService(
        mastodon_clients=mastodon_clients or [],
        bluesky_clients=bluesky_clients or [],
        storage_path=str(tmp_path),
        timezone_name="UTC",
    )


def _mastodon_status(status_id, in_reply_to_id, acct, visibility="public"):
    return {
        "id": status_id,
        "in_reply_to_id": in_reply_to_id,
        "visibility": visibility,
        "account": {
            "acct": acct,
            "url": f"https://mastodon.social/@{acct}",
            "avatar": f"https://mastodon.social/avatars/{acct}.png",
        },
        "content": f"<p>reply {status_id}</p>",
        "created_at": f"2026-01-01T00:00:{int(status_id) % 60:02d}Z",
        "url": f"https://mastodon.social/@{acct}/{status_id}",
    }


def _mastodon_client(descendants):
    client = MagicMock()
    client.account_name = "personal"
    client.enabled = True
    client.api.status.return_value = {
        "favourites_count": 0,
        "reblogs_count": 0,
        "replies_count": len(descendants),
    }
    client.api.status_context.return_value = {"descendants": descendants}
    return client


def _bluesky_reply(rkey, handle, replies=None):
    return SimpleNamespace(
        post=SimpleNamespace(
            uri=f"at://did:plc:{handle}/app.bsky.feed.post/{rkey}",
            author=SimpleNamespace(handle=handle, avatar=f"https://cdn.bsky.app/{handle}.jpg"),
            record=SimpleNamespace(text=f"reply {rkey}", created_at="2026-01-01T00:00:00Z"),
        ),
        replies=replies or [],
    )


def _urls(previews):
    return [p["url"] for p in previews]


class TestMastodonReplyThreads:
    def test_nested_replies_stored_as_children_tree(self, tmp_path):
        descendants = [
            _mastodon_status("101", "100", "alice"),
            _mastodon_status("103", "101", "me"),
            _mastodon_status("104", "103", "alice"),
            _mastodon_status("102", "100", "bob"),
            _mastodon_status("105", "102", "carol"),
        ]
        svc = _make_service(tmp_path, mastodon_clients=[_mastodon_client(descendants)])
        svc.data_store.put_syndication_mapping(GHOST_POST_ID, {
            "ghost_post_id": GHOST_POST_ID,
            "ghost_post_url": "https://blog.example.com/post/",
            "syndicated_at": "2026-01-01T00:00:00+00:00",
            "platforms": {
                "mastodon": {
                    "personal": {"status_id": "100", "post_url": "https://mastodon.social/@me/100"}
                },
                "bluesky": {},
            },
        })

        svc.sync_post_interactions(GHOST_POST_ID)

        stored = svc.data_store.get(GHOST_POST_ID)
        previews = stored["platforms"]["mastodon"]["personal"]["reply_previews"]
        # Only direct replies at the top level; nested ones live under them.
        assert _urls(previews) == [
            "https://mastodon.social/@alice/101",
            "https://mastodon.social/@bob/102",
        ]
        alice, bob = previews
        assert _urls(alice["children"]) == ["https://mastodon.social/@me/103"]
        my_reply = alice["children"][0]
        assert my_reply["author"] == "@me"
        assert my_reply["content"] == "reply 103"
        assert _urls(my_reply["children"]) == ["https://mastodon.social/@alice/104"]
        assert my_reply["children"][0]["children"] == []
        assert _urls(bob["children"]) == ["https://mastodon.social/@carol/105"]

    def test_non_public_statuses_left_out_of_threads(self, tmp_path):
        descendants = [
            _mastodon_status("101", "100", "alice"),
            _mastodon_status("102", "101", "bob", visibility="private"),
            _mastodon_status("103", "102", "carol"),
            _mastodon_status("104", "101", "dave", visibility="direct"),
            _mastodon_status("105", "101", "erin", visibility="unlisted"),
        ]
        svc = _make_service(tmp_path, mastodon_clients=[_mastodon_client(descendants)])

        data = svc._sync_mastodon_interactions("personal", "100", "https://mastodon.social/@me/100")

        (alice,) = data["reply_previews"]
        # The followers-only reply and the public reply beneath it are both dropped.
        assert _urls(alice["children"]) == ["https://mastodon.social/@erin/105"]

    def test_direct_reply_without_thread_has_empty_children(self, tmp_path):
        svc = _make_service(
            tmp_path, mastodon_clients=[_mastodon_client([_mastodon_status("101", "100", "alice")])]
        )

        data = svc._sync_mastodon_interactions("personal", "100", "https://mastodon.social/@me/100")

        assert data["reply_previews"][0]["children"] == []


class TestBlueskyReplyThreads:
    def test_nested_replies_stored_as_children_tree(self, tmp_path):
        not_found = SimpleNamespace(uri="at://did:plc:gone/app.bsky.feed.post/x", not_found=True)
        thread = SimpleNamespace(
            post=SimpleNamespace(like_count=0, repost_count=0, reply_count=1),
            replies=[
                _bluesky_reply("r1", "alice.bsky.social", replies=[
                    _bluesky_reply("r2", "me.bsky.social", replies=[
                        _bluesky_reply("r3", "alice.bsky.social"),
                    ]),
                    not_found,
                ]),
            ],
        )
        client = MagicMock()
        client.account_name = "main"
        client.enabled = True
        client.api.app.bsky.feed.get_post_thread.return_value = SimpleNamespace(thread=thread)
        svc = _make_service(tmp_path, bluesky_clients=[client])

        data = svc._sync_bluesky_interactions(
            "main", "at://did:plc:me/app.bsky.feed.post/root", "https://bsky.app/profile/me/post/root"
        )

        client.api.app.bsky.feed.get_post_thread.assert_called_once_with({
            "uri": "at://did:plc:me/app.bsky.feed.post/root",
            "depth": REPLY_THREAD_MAX_DEPTH + 1,
        })
        (alice,) = data["reply_previews"]
        assert _urls(alice["children"]) == ["https://bsky.app/profile/me.bsky.social/post/r2"]
        my_reply = alice["children"][0]
        assert my_reply["content"] == "reply r2"
        assert _urls(my_reply["children"]) == ["https://bsky.app/profile/alice.bsky.social/post/r3"]
        assert my_reply["children"][0]["children"] == []


class TestBuildReplyThread:
    """Caps on the captured thread, using a plain {name: [child names]} tree."""

    @staticmethod
    def _build(tree, root="root"):
        return InteractionSyncService._build_reply_thread(
            root,
            lambda node: tree.get(node, []),
            lambda node: {"url": node, "children": []},
        )

    def test_depth_capped(self):
        chain = {"root": ["n1"]}
        for i in range(1, REPLY_THREAD_MAX_DEPTH + 5):
            chain[f"n{i}"] = [f"n{i + 1}"]

        node = {"children": self._build(chain)}
        depth = 0
        while node["children"]:
            node = node["children"][0]
            depth += 1

        assert depth == REPLY_THREAD_MAX_DEPTH

    def test_reply_cap_keeps_replies_closest_to_root(self, monkeypatch):
        monkeypatch.setattr(interaction_sync, "REPLY_THREAD_MAX_REPLIES", 4)
        # "a" opens a long chain; "b" has a single reply. Breadth-first keeps "b1"
        # rather than spending the whole cap on the chain under "a".
        tree = {"root": ["a", "b"], "a": ["a1"], "a1": ["a2"], "a2": ["a3"], "b": ["b1"]}

        thread = self._build(tree)

        a, b = thread
        assert _urls(a["children"]) == ["a1"]
        assert a["children"][0]["children"] == []
        assert _urls(b["children"]) == ["b1"]
