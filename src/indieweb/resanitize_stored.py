"""
One-shot maintenance: re-apply the content sanitizer to received
webmentions already in storage.

Rows persisted before the server-side sanitizer was added still hold
raw third-party HTML, so JSON-LD payloads, inline CSS, and disallowed
attributes still come back through ``/api/webmentions``. This walks
``received_webmentions``, runs the same sanitizers the receiver now
applies, and rewrites any row whose content changed. The operation is
idempotent — re-running reports zero changes.

Usage (via the Makefile shortcuts that wrap ``docker compose run``)::

    make resanitize-webmentions-dryrun
    make resanitize-webmentions
    make resanitize-webmentions STORAGE_PATH=/app/data/interactions

Or directly inside the container::

    poetry run python -m indieweb.resanitize_stored --storage-path ./data --dry-run
    poetry run python -m indieweb.resanitize_stored --storage-path ./data
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from typing import Iterator, Optional, Tuple

from indieweb.content_sanitizer import sanitize_content_html, sanitize_content_text


def _iter_rows(conn: sqlite3.Connection) -> Iterator[Tuple[int, str, str]]:
    cursor = conn.execute(
        "SELECT rowid, content_html, content_text FROM received_webmentions"
    )
    for row in cursor:
        yield row[0], row[1] or "", row[2] or ""


def resanitize_storage(
    storage_path: str,
    *,
    dry_run: bool = False,
    on_change=None,
) -> dict:
    """Re-sanitize all stored received-webmention content.

    Args:
        storage_path: Directory containing ``interactions.db``.
        dry_run: When True, do not write any updates.
        on_change: Optional callback invoked as ``on_change(rowid, before, after)``
            for each row whose sanitized form differs from its stored form.
            ``before`` and ``after`` are ``(html, text)`` tuples.

    Returns:
        Summary dict with ``rows_scanned``, ``rows_changed``, and per-field
        byte deltas.
    """
    db_path = os.path.join(storage_path, "interactions.db")
    if not os.path.isfile(db_path):
        raise FileNotFoundError(f"Database not found: {db_path}")

    summary = {
        "rows_scanned": 0,
        "rows_changed": 0,
        "html_bytes_before": 0,
        "html_bytes_after": 0,
        "text_bytes_before": 0,
        "text_bytes_after": 0,
    }

    conn = sqlite3.connect(db_path)
    try:
        changes: list[Tuple[int, str, str]] = []
        for rowid, html_in, text_in in _iter_rows(conn):
            summary["rows_scanned"] += 1
            html_out = sanitize_content_html(html_in)
            text_out = sanitize_content_text(text_in)

            if html_out == html_in and text_out == text_in:
                continue

            summary["rows_changed"] += 1
            summary["html_bytes_before"] += len(html_in)
            summary["html_bytes_after"] += len(html_out)
            summary["text_bytes_before"] += len(text_in)
            summary["text_bytes_after"] += len(text_out)
            changes.append((rowid, html_out, text_out))

            if on_change is not None:
                on_change(rowid, (html_in, text_in), (html_out, text_out))

        if not dry_run and changes:
            with conn:
                conn.executemany(
                    "UPDATE received_webmentions "
                    "SET content_html = ?, content_text = ? "
                    "WHERE rowid = ?",
                    [(html, text, rowid) for rowid, html, text in changes],
                )
    finally:
        conn.close()

    return summary


def _print_change(rowid: int, before, after) -> None:
    html_before, text_before = before
    html_after, text_after = after
    print(
        f"  row {rowid}: "
        f"html {len(html_before)} -> {len(html_after)} bytes, "
        f"text {len(text_before)} -> {len(text_after)} bytes"
    )


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Re-sanitize content_html and content_text on all stored "
            "received webmentions."
        ),
    )
    parser.add_argument(
        "--storage-path",
        default="./data",
        help="Directory containing interactions.db (default: ./data)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would change without writing anything.",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Print every row that changes.",
    )
    args = parser.parse_args(argv)

    try:
        summary = resanitize_storage(
            storage_path=args.storage_path,
            dry_run=args.dry_run,
            on_change=_print_change if args.verbose else None,
        )
    except FileNotFoundError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    mode = "dry-run" if args.dry_run else "applied"
    print(
        f"[{mode}] scanned {summary['rows_scanned']} row(s), "
        f"{summary['rows_changed']} changed"
    )
    if summary["rows_changed"]:
        print(
            f"  content_html: {summary['html_bytes_before']} "
            f"-> {summary['html_bytes_after']} bytes"
        )
        print(
            f"  content_text: {summary['text_bytes_before']} "
            f"-> {summary['text_bytes_after']} bytes"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
