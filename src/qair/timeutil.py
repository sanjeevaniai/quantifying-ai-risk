"""Timestamp normalisation."""

from __future__ import annotations

from datetime import datetime, timezone

__all__ = ["to_utc", "parse_utc"]


def to_utc(value: datetime) -> datetime:
    """Return ``value`` in UTC.

    A naive datetime is assumed to be UTC. An offset-aware one is converted,
    which preserves the instant it refers to.
    """
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def parse_utc(value: str) -> datetime:
    """Parse an ISO 8601 date or datetime and normalise it to UTC."""
    return to_utc(datetime.fromisoformat(value))
