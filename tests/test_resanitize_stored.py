"""Tests for the stored-webmention re-sanitization tool."""

import os
import sqlite3

import pytest

from indieweb.resanitize_stored import main, resanitize_storage
from interactions.storage import InteractionDataStore


@pytest.fixture
def populated_store(tmp_path):
    """A store with a mix of clean and dirty stored webmentions."""
    store = InteractionDataStore(str(tmp_path))

    rows = [
        # 0: dirty — JSON-LD inside <script> should be dropped from both fields
        (
            "https://a.example/post",
            "https://blog.example.com/p1",
            "<p>Real reply.</p>"
            '<script type="application/ld+json">{"@context":"x"}</script>',
            '<script type="application/ld+json">{"@context":"x"}</script>Real reply.',
        ),
        # 1: dirty — disallowed attrs and tags
        (
            "https://b.example/post",
            "https://blog.example.com/p2",
            '<p class="x" onclick="alert(1)">hi <span>there</span></p>',
            "hi there",
        ),
        # 2: clean — already sanitized
        (
            "https://c.example/post",
            "https://blog.example.com/p3",
            "<p>already clean</p>",
            "already clean",
        ),
        # 3: NULL content (some early rows may have NULLs)
        (
            "https://d.example/post",
            "https://blog.example.com/p4",
            None,
            None,
        ),
    ]

    with sqlite3.connect(store.db_path) as conn:
        conn.executemany(
            "INSERT INTO received_webmentions "
            "(source, target, content_html, content_text, received_at, status) "
            "VALUES (?, ?, ?, ?, '2026-01-01T00:00:00+00:00', 'verified')",
            rows,
        )

    return str(tmp_path)


def _fetch_all(storage_path):
    db = os.path.join(storage_path, "interactions.db")
    with sqlite3.connect(db) as conn:
        return conn.execute(
            "SELECT source, content_html, content_text "
            "FROM received_webmentions ORDER BY source"
        ).fetchall()


class TestResanitizeStorage:
    def test_dry_run_does_not_write(self, populated_store):
        before = _fetch_all(populated_store)
        summary = resanitize_storage(populated_store, dry_run=True)
        after = _fetch_all(populated_store)

        assert before == after
        assert summary["rows_scanned"] == 4
        assert summary["rows_changed"] == 2

    def test_applies_changes(self, populated_store):
        summary = resanitize_storage(populated_store, dry_run=False)
        assert summary["rows_changed"] == 2

        rows = {source: (html, text) for source, html, text in _fetch_all(populated_store)}

        # Row 0: script body dropped from html, JSON-LD stripped from text
        assert rows["https://a.example/post"][0] == "<p>Real reply.</p>"
        assert "@context" not in rows["https://a.example/post"][0]
        assert "@context" not in (rows["https://a.example/post"][1] or "")

        # Row 1: disallowed attrs/tags stripped
        assert rows["https://b.example/post"][0] == "<p>hi there</p>"

        # Row 2: untouched
        assert rows["https://c.example/post"][0] == "<p>already clean</p>"

        # Row 3: NULLs left as-is (sanitizers map empty -> empty, no change)
        assert rows["https://d.example/post"] == (None, None)

    def test_is_idempotent(self, populated_store):
        first = resanitize_storage(populated_store, dry_run=False)
        second = resanitize_storage(populated_store, dry_run=False)

        assert first["rows_changed"] == 2
        assert second["rows_changed"] == 0

    def test_on_change_callback(self, populated_store):
        observed = []

        def cb(rowid, before, after):
            observed.append((rowid, before, after))

        resanitize_storage(populated_store, dry_run=True, on_change=cb)
        assert len(observed) == 2
        # before != after for every reported change
        for _, before, after in observed:
            assert before != after

    def test_missing_db_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            resanitize_storage(str(tmp_path / "nope"))

    def test_empty_table(self, tmp_path):
        InteractionDataStore(str(tmp_path))  # creates empty DB
        summary = resanitize_storage(str(tmp_path), dry_run=False)
        assert summary == {
            "rows_scanned": 0,
            "rows_changed": 0,
            "html_bytes_before": 0,
            "html_bytes_after": 0,
            "text_bytes_before": 0,
            "text_bytes_after": 0,
        }


class TestCli:
    def test_dry_run_exit_zero(self, populated_store, capsys):
        rc = main(["--storage-path", populated_store, "--dry-run"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "[dry-run]" in out
        assert "2 changed" in out

    def test_apply_exit_zero(self, populated_store, capsys):
        rc = main(["--storage-path", populated_store])
        assert rc == 0
        out = capsys.readouterr().out
        assert "[applied]" in out
        assert "2 changed" in out

    def test_verbose_lists_rows(self, populated_store, capsys):
        rc = main(["--storage-path", populated_store, "--dry-run", "--verbose"])
        assert rc == 0
        out = capsys.readouterr().out
        # Two changed rows should be reported individually
        assert out.count("row ") >= 2

    def test_missing_db_exit_one(self, tmp_path, capsys):
        rc = main(["--storage-path", str(tmp_path / "nope")])
        assert rc == 1
        err = capsys.readouterr().err
        assert "error" in err.lower()
