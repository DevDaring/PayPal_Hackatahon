"""A single clock for the application so tests can freeze the scenario time."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

_frozen: datetime | None = None


def now() -> datetime:
    return _frozen if _frozen is not None else datetime.now(UTC)


def freeze(at: datetime | None) -> None:
    global _frozen
    _frozen = at


def local_date(tz: str, at: datetime | None = None) -> date:
    return (at or now()).astimezone(ZoneInfo(tz)).date()


def end_of_local_day(d: date, tz: str) -> datetime:
    """23:59:59 on `d` in `tz`, returned in UTC (storage is always UTC)."""
    local = datetime(d.year, d.month, d.day, 23, 59, 59, tzinfo=ZoneInfo(tz))
    return local.astimezone(UTC)


def add_days_local(start: datetime, days: int, tz: str) -> date:
    return start.astimezone(ZoneInfo(tz)).date() + timedelta(days=days)
