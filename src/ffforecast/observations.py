"""Measured wind from the Mystic weather station, kept so the forecast can be checked against it.

The station (FreeFlightWx) offers its log as a CSV download: `table.php?h=<hours>&download=csv`, one row
about every 11 seconds, newest first, local time, speeds in mph. It is fetched once a day, and the
log is summarised into 5 minute buckets (average wind, strongest gust, lightest lull, direction,
temperature, cloudbase) stored in one file per local date under `state/observations/`.

A day that was missed is caught up from a longer log: 2, 7 or 30 days (the longest the station offers).
A gap longer than that is recorded and cannot be recovered. See docs/verification.md.
"""

from __future__ import annotations

import csv
import io
import json
import math
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from .config import ObservationsConfig
from .units import mph_to_kph

BUCKET_S = 300
HOURS_OPTIONS = (24, 48, 168, 720)  # the log lengths the station offers that we use
RETRY_AFTER = timedelta(hours=1)
MARGIN_H = 2  # overlap, so a reading at the edge of a download is not lost


@dataclass(frozen=True)
class Reading:
    time: datetime  # UTC
    avg_kph: float
    gust_kph: float
    lull_kph: float
    dir_deg: float
    temp_c: float | None
    humidity: float | None
    qnh_pa: float | None
    dew_c: float | None = None
    # Where cumulus would form, metres above sea level. The station works it out from its own
    # temperature and dew point (its height plus 125 m per degree between them): not a measurement of cloud.
    cloudbase_m: float | None = None


# ---------------------------------------------------------------------------------------------
# Reading the CSV


def _num(row: dict[str, str], key: str) -> float | None:
    try:
        v = row.get(key, "").strip()
        return float(v) if v != "" else None
    except ValueError:
        return None


def _feet_to_m(ft: float | None) -> float | None:
    return round(ft * 0.3048) if ft is not None else None


def parse_csv(text: str, tz: str) -> tuple[list[Reading], int]:
    """(readings oldest first, number of rows skipped). Times in the file are local; the hour that
    repeats when daylight saving ends is told apart by the file order (newest first)."""
    zone = ZoneInfo(tz)
    reader = csv.DictReader(io.StringIO(text))
    if "Date_Time" not in (reader.fieldnames or []):
        raise ValueError("this does not look like the station's log (no Date_Time column)")
    rows = list(reader)
    readings: list[Reading] = []
    skipped = 0
    prev: datetime | None = None
    fold = 0
    for row in reversed(rows):  # oldest first
        try:
            naive = datetime.strptime(row["Date_Time"].strip(), "%Y-%m-%d %H:%M:%S")
        except (KeyError, ValueError):
            skipped += 1
            continue
        avg, gust, lull = (
            _num(row, k) for k in ("Windspeedmph", "WindspeedmphMax", "WindspeedmphMin")
        )
        direction = _num(row, "Winddir")
        if avg is None or gust is None or lull is None or direction is None:
            skipped += 1
            continue
        if prev is not None and naive < prev - timedelta(minutes=30):
            fold = 1  # local time went back: the clocks were put back an hour
        prev = naive
        local = naive.replace(tzinfo=zone, fold=fold)
        readings.append(
            Reading(
                local.astimezone(UTC),
                round(mph_to_kph(avg), 1),
                round(mph_to_kph(gust), 1),
                round(mph_to_kph(lull), 1),
                direction % 360,
                _num(row, "Tempc"),
                _num(row, "Humidity"),
                _num(row, "realQNH"),
                _num(row, "DewPoint"),
                _feet_to_m(_num(row, "CloudbaseAGLft_AMSL")),
            )
        )
    return readings, skipped


# ---------------------------------------------------------------------------------------------
# Five minute summaries


def circular_mean(dirs: list[float], weights: list[float]) -> float | None:
    """The mean of compass directions, weighted (by speed, so calm noise counts for little).
    None when there is no wind to point anywhere."""
    x = sum(w * math.sin(math.radians(d)) for d, w in zip(dirs, weights, strict=True))
    y = sum(w * math.cos(math.radians(d)) for d, w in zip(dirs, weights, strict=True))
    if math.hypot(x, y) < 1e-9:
        return None
    return round(math.degrees(math.atan2(x, y)) % 360)


def _mean(values: list[float | None], digits: int = 1) -> float | None:
    got = [v for v in values if v is not None]
    return round(sum(got) / len(got), digits) if got else None


def bucketize(readings: list[Reading]) -> dict[str, dict]:
    """{bucket start (ISO UTC): summary}. n is how many readings the bucket holds."""
    groups: dict[int, list[Reading]] = {}
    for r in readings:
        groups.setdefault(int(r.time.timestamp()) // BUCKET_S, []).append(r)
    out = {}
    for k, rs in sorted(groups.items()):
        start = datetime.fromtimestamp(k * BUCKET_S, UTC)
        out[start.isoformat().replace("+00:00", "Z")] = {
            "n": len(rs),
            "avg_kph": round(sum(r.avg_kph for r in rs) / len(rs), 1),
            "gust_kph": max(r.gust_kph for r in rs),
            "lull_kph": min(r.lull_kph for r in rs),
            "dir_deg": circular_mean([r.dir_deg for r in rs], [r.avg_kph for r in rs]),
            "temp_c": _mean([r.temp_c for r in rs]),
            "humidity": _mean([r.humidity for r in rs]),
            "qnh_pa": _mean([r.qnh_pa for r in rs], 0),
            "dew_c": _mean([r.dew_c for r in rs]),
            "cloudbase_m": _mean([r.cloudbase_m for r in rs], 0),
        }
    return out


# ---------------------------------------------------------------------------------------------
# The store: one file per local date, and a status file


def obs_dir(state_dir: Path) -> Path:
    return state_dir / "observations"


def _write(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=1))
    tmp.replace(path)


def _read(path: Path, default):
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return default


def parse_iso(value: str | None) -> datetime | None:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")) if value else None
    except (ValueError, AttributeError):
        return None


def store_buckets(directory: Path, buckets: dict[str, dict], tz: str) -> int:
    """Merge buckets into the files of their local dates. A bucket already held is replaced only by
    one built from more readings, so a download that starts or ends part way through a bucket never
    makes it worse. Returns how many buckets were added or improved."""
    zone = ZoneInfo(tz)
    by_date: dict[str, dict[str, dict]] = {}
    for iso, b in buckets.items():
        local = parse_iso(iso)
        assert local is not None
        by_date.setdefault(local.astimezone(zone).date().isoformat(), {})[iso] = b
    changed = 0
    for date, new in by_date.items():
        path = directory / f"{date}.json"
        held = _read(path, {"date": date, "buckets": {}})
        for iso, b in new.items():
            old = held["buckets"].get(iso)
            if old is None or b["n"] > old["n"]:
                held["buckets"][iso] = b
                changed += 1
        held["buckets"] = dict(sorted(held["buckets"].items()))
        _write(path, held)
    return changed


def read_day(directory: Path, date: str) -> dict[str, dict]:
    """The 5 minute buckets held for a local date, by start time (ISO UTC). Empty when none."""
    return _read(directory / f"{date}.json", {}).get("buckets", {})


def read_status(directory: Path) -> dict:
    return _read(directory / "status.json", {})


def last_reading(directory: Path) -> datetime | None:
    return parse_iso(read_status(directory).get("last_reading"))


# ---------------------------------------------------------------------------------------------
# When to download, and how much


def plan_hours(last: datetime | None, now: datetime) -> tuple[int, str]:
    """How many hours of log to ask for, and a note when something was missed. The log must reach back
    past the last reading we hold (with a margin); the next longer length is used if it does not."""
    if last is None:
        return HOURS_OPTIONS[
            -1
        ], "no observations held yet: starting with the longest log (30 days)"
    gap_h = (now - last).total_seconds() / 3600
    need = gap_h + MARGIN_H
    for h in HOURS_OPTIONS:
        if h >= need:
            note = "" if h <= 48 else f"catching up after {gap_h / 24:.1f} days"
            return h, note
    return HOURS_OPTIONS[-1], (
        f"{gap_h / 24:.0f} days have passed since the last reading: more than the 30 day log "
        "holds, so the earlier days are lost"
    )


def due(cfg: ObservationsConfig, directory: Path, now: datetime, tz: str) -> bool:
    """True when the daily download should run: after the day's run time on a date not yet fetched,
    or at once when the newest reading is older than `max_age_h` (a day was missed)."""
    if not cfg.enabled:
        return False
    status = read_status(directory)
    attempt = parse_iso(status.get("last_attempt"))
    if attempt is not None and now - attempt < RETRY_AFTER:
        return False  # it failed a short while ago: do not hammer the station
    last = parse_iso(status.get("last_reading"))
    if last is None or now - last > timedelta(hours=cfg.max_age_h):
        return True
    local = now.astimezone(ZoneInfo(tz))
    hh, mm = (int(x) for x in cfg.run_time.split(":"))
    if (local.hour, local.minute) < (hh, mm):
        return False
    return status.get("last_fetch_date") != local.date().isoformat()


# ---------------------------------------------------------------------------------------------
# Fetching


@dataclass
class Result:
    fetched_hours: int = 0
    readings: int = 0
    skipped: int = 0
    buckets_changed: int = 0
    notes: list[str] = field(default_factory=list)
    error: str = ""


def fetch_csv(session, cfg: ObservationsConfig, hours: int, user_agent: str) -> str:
    resp = session.get(
        cfg.url,
        params={"h": hours, "download": "csv"},
        headers={"User-Agent": user_agent},
        timeout=180,
    )
    if resp.status_code != 200:
        raise OSError(f"the station answered HTTP {resp.status_code}")
    return resp.text


def refresh(
    cfg: ObservationsConfig,
    state_dir: Path,
    tz: str,
    session,
    user_agent: str,
    now: datetime | None = None,
    hours: int | None = None,
) -> Result:
    """Download the log, merge it into the store and update the status. Never raises: a failure is
    in `error` and the store is left as it was."""
    now = now or datetime.now(UTC)
    directory = obs_dir(state_dir)
    result = Result()
    if not cfg.enabled:
        result.error = "observations are turned off in the site configuration"
        return result
    plan, note = plan_hours(last_reading(directory), now)
    result.fetched_hours = hours or plan
    if note and hours is None:
        result.notes.append(note)
    stamp = now.isoformat(timespec="seconds").replace("+00:00", "Z")

    def failed(reason: str) -> Result:
        result.error = reason
        status = read_status(directory)
        status.update(last_attempt=stamp, last_error=reason)
        _write(directory / "status.json", status)
        return result

    try:
        text = fetch_csv(session, cfg, result.fetched_hours, user_agent)
        readings, skipped = parse_csv(text, tz)
    except (OSError, ValueError) as e:
        return failed(str(e) or type(e).__name__)
    if not readings:
        return failed("the log held no readings")
    result.readings, result.skipped = len(readings), skipped
    result.buckets_changed = store_buckets(directory, bucketize(readings), tz)
    status = read_status(directory)
    status["last_fetch"] = stamp
    status["last_attempt"] = stamp
    status.pop("last_error", None)
    status["last_fetch_date"] = now.astimezone(ZoneInfo(tz)).date().isoformat()
    newest = readings[-1].time.isoformat().replace("+00:00", "Z")
    status["last_reading"] = max(newest, status.get("last_reading") or "")
    # a gap the log could not cover (the oldest reading is later than the last one we held)
    previous = parse_iso(status.get("previous_last_reading"))
    oldest = readings[0].time
    if previous is not None and oldest - previous > timedelta(minutes=30):
        gap = {
            "from": previous.isoformat().replace("+00:00", "Z"),
            "to": oldest.isoformat().replace("+00:00", "Z"),
        }
        status.setdefault("gaps", []).append(gap)
        result.notes.append(f"no readings between {gap['from']} and {gap['to']}")
    status["previous_last_reading"] = status["last_reading"]
    _write(directory / "status.json", status)
    return result
