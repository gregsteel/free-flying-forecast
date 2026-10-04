"""NOAA GFS access: cycle discovery, .idx parsing and ranged downloads from AWS open data."""

from __future__ import annotations

import time
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol

import requests

from .models import DETAILED_DAYS, OUTLOOK_DAYS


class Getter(Protocol):
    """The part of requests.Session used for downloads (lets tests substitute a fake)."""

    def get(
        self, url: str, *, headers: Mapping[str, str] | None = ..., timeout: Any = ...
    ) -> Any: ...


BUCKET = "https://noaa-gfs-bdp-pds.s3.amazonaws.com"
CYCLES = (18, 12, 6, 0)

# (variable, level text as it appears in the .idx file). The eight fields the days 4-7 outlook
# needs. Each GFS field is global (about 0.7 MB), so keeping this short matters.
OUTLOOK_FIELDS: tuple[tuple[str, str], ...] = (
    ("UGRD", "10 m above ground"),
    ("VGRD", "10 m above ground"),
    ("TMP", "2 m above ground"),
    ("HPBL", "surface"),
    ("SHTFL", "surface"),
    ("PRATE", "surface"),  # precipitation rate, kg/m2/s (instantaneous)
    ("CAPE", "surface"),  # storm energy, J/kg
    ("GUST", "surface"),  # wind gust, m/s
)
# GFS-only mode also needs the wind aloft; 850 hPa is about 1,500 m above sea level.
BLOCK_FIELDS: tuple[tuple[str, str], ...] = (
    *OUTLOOK_FIELDS,
    # Wind at launch height is interpolated from these levels and the 10 m wind. Levels below
    # the model ground are dropped by profile.usable_profile using surface pressure.
    ("PRES", "surface"),
    ("HGT", "surface"),
    *((var, f"{lvl} mb") for lvl in (950, 925, 900, 850) for var in ("UGRD", "VGRD", "HGT")),
)
DEFAULT_FIELDS = BLOCK_FIELDS
# GFS reports surface heating as an average since the last multiple of 6 hours, so the heating at
# one hour needs the previous hour's average as well (about 0.7 MB for this one field).
FLUX_FIELDS: tuple[tuple[str, str], ...] = (("SHTFL", "surface"),)
BLOCK_HOURS = tuple(range(10, 19))  # local hours of the hourly blocks: 10:00 to 18:00


@dataclass(frozen=True)
class IdxEntry:
    number: int
    start: int
    end: int | None  # None = to end of file
    variable: str
    level: str
    forecast: str


@dataclass(frozen=True)
class Cycle:
    date: str  # YYYYMMDD
    hour: int

    @property
    def label(self) -> str:
        return f"{self.date[:4]}-{self.date[4:6]}-{self.date[6:]}T{self.hour:02d}Z"

    def file_url(self, fhour: int, suffix: str = "") -> str:
        return (
            f"{BUCKET}/gfs.{self.date}/{self.hour:02d}/atmos/"
            f"gfs.t{self.hour:02d}z.pgrb2.0p25.f{fhour:03d}{suffix}"
        )


def parse_idx(text: str) -> list[IdxEntry]:
    """Parse a wgrib2 .idx file into entries with byte ranges."""
    raw = []
    for line in text.splitlines():
        parts = line.split(":")
        if len(parts) < 6:
            continue
        raw.append((int(parts[0]), int(parts[1]), parts[3], parts[4], parts[5]))
    entries = []
    for i, (num, start, var, level, fc) in enumerate(raw):
        end = raw[i + 1][1] - 1 if i + 1 < len(raw) else None
        entries.append(IdxEntry(num, start, end, var, level, fc))
    return entries


def select(
    entries: list[IdxEntry], fields: tuple[tuple[str, str], ...] = DEFAULT_FIELDS
) -> list[IdxEntry]:
    wanted = set(fields)
    # GFS lists PRATE twice: instantaneous ("6 hour fcst") and an average ("0-6 hour ave fcst").
    # Only the instantaneous value is wanted.
    return [
        e
        for e in entries
        if (e.variable, e.level) in wanted and not (e.variable == "PRATE" and "ave" in e.forecast)
    ]


def merge_ranges(entries: list[IdxEntry]) -> list[tuple[int, int | None]]:
    """Merge byte ranges of adjacent messages to reduce the number of requests."""
    ranges: list[tuple[int, int | None]] = []
    for e in sorted(entries, key=lambda x: x.start):
        if ranges and ranges[-1][1] is not None and ranges[-1][1] + 1 == e.start:
            ranges[-1] = (ranges[-1][0], e.end)
        else:
            ranges.append((e.start, e.end))
    return ranges


def candidate_cycles(now: datetime | None = None, days: int = 2) -> list[Cycle]:
    """Cycles newest first, going back `days` days."""
    now = now or datetime.now(UTC)
    out = []
    for d in range(days + 1):
        day = (now - timedelta(days=d)).strftime("%Y%m%d")
        for h in CYCLES:
            if d == 0 and datetime(now.year, now.month, now.day, h, tzinfo=UTC) > now:
                continue
            out.append(Cycle(day, h))
    return out


def latest_available_cycle(
    session: requests.Session | None = None,
    now: datetime | None = None,
    check_fhour: int = 168,
) -> Cycle | None:
    """Newest cycle whose last needed forecast hour has been published (its .idx exists)."""
    s = session or requests.Session()
    for c in candidate_cycles(now):
        try:
            r = s.head(c.file_url(check_fhour, ".idx"), timeout=(10, 20))
        except requests.RequestException:
            continue
        if r.status_code == 200:
            return c
    return None


def _get_range(session: Getter, url: str, hdr: str, attempts: int, backoff_s: float) -> bytes:
    last: Exception | None = None
    for n in range(attempts):
        try:
            r = session.get(url, headers={"Range": hdr}, timeout=(10, 60))
            if r.status_code in (200, 206):
                return r.content
            last = RuntimeError(f"HTTP {r.status_code}")
        except requests.RequestException as e:
            last = e
        if n + 1 < attempts:
            time.sleep(backoff_s * (n + 1))
    raise RuntimeError(f"GFS download failed for {url} {hdr}: {last}")


def download_ranges(
    session: Getter,
    url: str,
    ranges: list[tuple[int, int | None]],
    dest: Path,
    attempts: int = 4,
    backoff_s: float = 2.0,
) -> int:
    """Download byte ranges of `url` and concatenate them into `dest`, retrying each range.
    Returns bytes written. The destination only appears once every range has arrived."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    total = 0
    with tmp.open("wb") as f:
        for start, end in ranges:
            hdr = f"bytes={start}-{end}" if end is not None else f"bytes={start}-"
            data = _get_range(session, url, hdr, attempts, backoff_s)
            f.write(data)
            total += len(data)
    tmp.replace(dest)
    return total


def fields_key(fields: tuple[tuple[str, str], ...]) -> str:
    """Short stable key for a field list, so a cached file is never reused for a different one."""
    import hashlib

    return hashlib.sha1(repr(sorted(fields)).encode()).hexdigest()[:8]


def fetch_forecast_hour(
    session: requests.Session,
    cycle: Cycle,
    fhour: int,
    dest_dir: Path,
    fields: tuple[tuple[str, str], ...] = DEFAULT_FIELDS,
) -> Path:
    dest = dest_dir / f"gfs.t{cycle.hour:02d}z.f{fhour:03d}.{fields_key(fields)}.grib2"
    if dest.exists():
        return dest
    url = cycle.file_url(fhour)
    idx = session.get(url + ".idx", timeout=(10, 60))
    idx.raise_for_status()
    chosen = select(parse_idx(idx.text), fields)
    if not chosen:
        raise RuntimeError(f"no wanted fields found in {url}.idx")
    download_ranges(session, url, merge_ranges(chosen), dest)
    return dest


def plan_hours(
    cycle: Cycle,
    now_utc: datetime,
    tz: str,
    block_days: int = DETAILED_DAYS,
    outlook_days: int = OUTLOOK_DAYS,
) -> tuple[list[int], list[int], str]:
    """Forecast hours to download for the GFS-only forecast.

    Returns (block_hours, outlook_hours, first_day). Blocks are the hourly 10:00 to 18:00
    local blocks on `block_days` days, starting today if the day's flying is not over, else
    tomorrow. The outlook uses the 3-hourly steps inside flying hours on the following days
    (3-hourly because GFS is only hourly to f120).
    """
    from zoneinfo import ZoneInfo

    zone = ZoneInfo(tz)
    now_local = now_utc.astimezone(zone)
    first = now_local.date() if now_local.hour < 18 else (now_local + timedelta(days=1)).date()
    start = datetime(
        int(cycle.date[:4]), int(cycle.date[4:6]), int(cycle.date[6:]), cycle.hour, tzinfo=UTC
    )

    def fh_for(local_dt: datetime) -> int:
        return int((local_dt.astimezone(UTC) - start).total_seconds() // 3600)

    blocks: list[int] = []
    outlook: list[int] = []
    for d in range(block_days + outlook_days):
        day = first + timedelta(days=d)
        for hour in BLOCK_HOURS:
            fh = fh_for(datetime(day.year, day.month, day.day, hour, tzinfo=zone))
            if fh < 1 or fh > 384:
                continue
            if d < block_days:
                if fh <= 120 or fh % 3 == 0:  # GFS is hourly only to f120
                    blocks.append(fh)
            elif d >= block_days and fh % 3 == 0:
                outlook.append(fh)
    return sorted(set(blocks)), sorted(set(outlook)), first.isoformat()


def flux_prev_hours(block_hours: list[int]) -> list[int]:
    """Forecast hours whose heating average is needed to recover the true hourly heating.

    GFS restarts its heating average every 6 hours, so forecast hours 1, 7, 13 and so on hold a
    single hour already and need nothing. Every other hour needs the hour before it (unless that
    is a block hour itself, which is fetched anyway)."""
    have = set(block_hours)
    return sorted(
        {h - 1 for h in block_hours if (h - 1) % 6 != 0 and h - 1 >= 1 and h - 1 not in have}
    )
