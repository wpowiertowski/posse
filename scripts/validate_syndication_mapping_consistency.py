#!/usr/bin/env python3
"""Validate syndication mappings consistency between JSON files and SQLite."""

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any


ALLOWED_PLATFORMS = {"mastodon", "bluesky"}


def _validate_account_data(account_data: Any) -> list[str]:
    errors: list[str] = []

    def validate_entry(entry: dict[str, Any]) -> None:
        if "post_url" not in entry or not isinstance(entry["post_url"], str) or not entry["post_url"]:
            errors.append("entry missing non-empty string post_url")
        has_status = isinstance(entry.get("status_id"), str) and bool(entry.get("status_id"))
        has_uri = isinstance(entry.get("post_uri"), str) and bool(entry.get("post_uri"))
        if not (has_status or has_uri):
            errors.append("entry must include non-empty status_id or post_uri")

    if isinstance(account_data, dict):
        validate_entry(account_data)
    elif isinstance(account_data, list):
        if not account_data:
            errors.append("split entry list cannot be empty")
        for entry in account_data:
            if not isinstance(entry, dict):
                errors.append("split list must contain objects")
                continue
            validate_entry(entry)
    else:
        errors.append("account mapping must be object or list")

    return errors


def validate_mapping(mapping: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if not isinstance(mapping.get("ghost_post_id"), str) or not mapping["ghost_post_id"]:
        errors.append("ghost_post_id must be a non-empty string")
    if not isinstance(mapping.get("ghost_post_url"), str) or not mapping["ghost_post_url"]:
        errors.append("ghost_post_url must be a non-empty string")
    if not isinstance(mapping.get("syndicated_at"), str):
        errors.append("syndicated_at must be a string")

    platforms = mapping.get("platforms")
    if not isinstance(platforms, dict):
        errors.append("platforms must be an object")
        return errors

    for platform, accounts in platforms.items():
        if platform not in ALLOWED_PLATFORMS:
            errors.append(f"unsupported platform '{platform}'")
        if not isinstance(accounts, dict):
            errors.append(f"platform '{platform}' accounts must be an object")
            continue
        for account_name, account_data in accounts.items():
            if not isinstance(account_name, str) or not account_name:
                errors.append(f"invalid account key for platform '{platform}'")
                continue
            errors.extend(
                f"{platform}/{account_name}: {detail}" for detail in _validate_account_data(account_data)
            )

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mappings-path", default="./data/syndication_mappings")
    parser.add_argument("--storage-path", default="./data/interactions")
    args = parser.parse_args()

    mappings_path = Path(args.mappings_path)
    db_path = Path(args.storage_path) / "interactions.db"

    json_mappings: dict[str, dict[str, Any]] = {}
    issues: list[str] = []

    for path in sorted(mappings_path.glob("*.json")):
        try:
            payload = json.loads(path.read_text())
        except Exception as exc:
            issues.append(f"JSON {path.name}: failed to parse ({exc})")
            continue

        errors = validate_mapping(payload)
        if errors:
            issues.append(f"JSON {path.name}: " + "; ".join(errors))
            continue

        ghost_post_id = payload["ghost_post_id"]
        json_mappings[ghost_post_id] = payload

    db_mappings: dict[str, dict[str, Any]] = {}
    if db_path.exists():
        with sqlite3.connect(db_path) as conn:
            rows = conn.execute("SELECT ghost_post_id, payload FROM syndication_mappings").fetchall()
        for ghost_post_id, payload in rows:
            try:
                mapping = json.loads(payload)
            except Exception as exc:
                issues.append(f"DB {ghost_post_id}: invalid JSON payload ({exc})")
                continue
            errors = validate_mapping(mapping)
            if errors:
                issues.append(f"DB {ghost_post_id}: " + "; ".join(errors))
                continue
            db_mappings[ghost_post_id] = mapping

    for ghost_post_id in sorted(set(json_mappings) | set(db_mappings)):
        in_json = ghost_post_id in json_mappings
        in_db = ghost_post_id in db_mappings

        if not in_json:
            issues.append(f"Missing JSON mapping for ghost_post_id={ghost_post_id}")
            continue
        if not in_db:
            issues.append(f"Missing DB mapping for ghost_post_id={ghost_post_id}")
            continue
        if json_mappings[ghost_post_id] != db_mappings[ghost_post_id]:
            issues.append(f"Payload mismatch for ghost_post_id={ghost_post_id}")

    if issues:
        print("Consistency check failed:")
        for issue in issues:
            print(f"- {issue}")
        return 1

    print(
        f"Consistency check passed for {len(json_mappings)} JSON mappings and "
        f"{len(db_mappings)} DB mappings"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
