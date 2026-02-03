"""Backfill module for legacy post syndication."""

from backfill.legacy_sync import LegacyBackfillService, create_backfill_blueprint

__all__ = ["LegacyBackfillService", "create_backfill_blueprint"]
