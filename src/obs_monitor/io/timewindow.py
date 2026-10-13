"""
obs_monitor.io.timewindow
=========================

Cycle arithmetic. This is the only place obs-monitor builds lists of cycle
times; nothing else should do ``timedelta`` math on cycles.

All cycles are naive :class:`datetime.datetime` objects meaning UTC.

>>> from obs_monitor.io.timewindow import cycle_range, trailing_window
>>> cycle_range("2026093000", "2026093018", interval_hours=6)
[datetime(2026, 9, 30, 0, 0), datetime(2026, 9, 30, 6, 0), datetime(2026, 9, 30, 12, 0), datetime(2026, 9, 30, 18, 0)]
>>> trailing_window("2026100100", n_cycles=4, interval_hours=6)[0]
datetime(2026, 9, 30, 6, 0)
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

_FORMATS = {10: "%Y%m%d%H", 12: "%Y%m%d%H%M"}


class CycleError(ValueError):
    """A cycle time or cycle range is invalid."""


def parse_cycle(value: str | int | datetime) -> datetime:
    """
    Parse ``YYYYMMDDHH`` or ``YYYYMMDDHHMM`` (str or int), or pass a datetime
    through. Timezone-aware datetimes are converted to naive UTC.
    """
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            value = value.astimezone(timezone.utc).replace(tzinfo=None)
        return value
    s = str(value).strip()
    fmt = _FORMATS.get(len(s))
    if fmt is None or not s.isdigit():
        raise CycleError(f"Cycle '{value}' must be YYYYMMDDHH or YYYYMMDDHHMM.")
    try:
        return datetime.strptime(s, fmt)
    except ValueError as exc:
        raise CycleError(f"Cycle '{value}' is not a valid date/time: {exc}") from exc


def format_cycle(cycle: datetime) -> str:
    """``datetime(2026, 9, 30, 18) -> '2026093018'``."""
    return cycle.strftime("%Y%m%d%H")


def _check_interval(interval_hours: int) -> timedelta:
    if not isinstance(interval_hours, int) or isinstance(interval_hours, bool) or interval_hours <= 0:
        raise CycleError(f"interval_hours must be a positive integer, got {interval_hours!r}.")
    return timedelta(hours=interval_hours)


def cycle_range(start, end, interval_hours: int = 6) -> list[datetime]:
    """
    Every cycle from ``start`` to ``end`` inclusive, ``interval_hours`` apart.

    Raises
    ------
    CycleError
        ``end`` is before ``start``, or ``end - start`` is not a whole number
        of intervals (a typo like 2026093017 would otherwise silently drop
        the last cycle).
    """
    t0, t1 = parse_cycle(start), parse_cycle(end)
    step = _check_interval(interval_hours)
    if t1 < t0:
        raise CycleError(f"End cycle {format_cycle(t1)} is before start cycle {format_cycle(t0)}.")
    if (t1 - t0) % step:
        raise CycleError(
            f"{format_cycle(t0)} to {format_cycle(t1)} is not a whole number of {interval_hours}-hour intervals."
        )
    n = (t1 - t0) // step + 1
    return [t0 + i * step for i in range(n)]


def trailing_window(end, n_cycles: int, interval_hours: int = 6) -> list[datetime]:
    """
    The ``n_cycles`` cycles ending at ``end`` (inclusive), oldest first.
    This is the operational rolling window: the current cycle plus history.
    """
    if not isinstance(n_cycles, int) or isinstance(n_cycles, bool) or n_cycles <= 0:
        raise CycleError(f"n_cycles must be a positive integer, got {n_cycles!r}.")
    t1 = parse_cycle(end)
    step = _check_interval(interval_hours)
    return [t1 - (n_cycles - 1 - i) * step for i in range(n_cycles)]
