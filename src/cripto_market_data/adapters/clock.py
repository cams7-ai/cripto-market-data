"""Operational UTC timestamps; no financial clock or global state."""

from datetime import UTC, datetime


def utc_now() -> datetime:
    return datetime.now(UTC)


def utc_timestamp(instant: datetime) -> str:
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise ValueError("timestamp exige timezone")
    return instant.astimezone(UTC).isoformat()
