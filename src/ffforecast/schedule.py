"""When the AUSRASP manifest should be checked (pure functions; see spec 003 FR-012)."""

from __future__ import annotations

from datetime import datetime, timedelta

from .config import PollWindow


def interval_min(now: datetime, windows: tuple[PollWindow, ...], default_every_min: int) -> int:
    """Minutes between checks at `now` (UTC): the shortest interval of any window holding it."""
    minute = now.hour * 60 + now.minute
    inside = [w.every_min for w in windows if w.start_min <= minute < w.end_min]
    return min(inside) if inside else default_every_min


def due(
    now: datetime,
    last_check: datetime | None,
    windows: tuple[PollWindow, ...],
    default_every_min: int,
) -> bool:
    """True when a check is due: never checked, or the interval for this time has passed.

    A small allowance (a minute) is taken off the interval so a job started every `every_min`
    minutes by launchd is not skipped by a few seconds of drift."""
    if last_check is None:
        return True
    every = interval_min(now, windows, default_every_min)
    return now - last_check >= timedelta(minutes=every) - timedelta(minutes=1)
