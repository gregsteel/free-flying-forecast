"""AUSRASP thermal height and updraft for the launch (specs/003-ausrasp-thermal-source).

AUSRASP publishes the numbers behind its Victoria maps as plain-text grids: one file per
quantity, day and hour, under `OUT+0` (today) to `OUT+6`, plus a file giving each cell's position
and a small manifest whose per-day stamp changes when that day is re-run. This module reads only
two quantities (thermalling height and updraft) at the grid cell nearest the launch, keeps the
values in a small local store, and offers them to the forecast as a lookup by valid time.

Everything here treats the source as unofficial: any problem (unreachable, refused, incomplete,
unexpected format, too old, switched off) is a normal "unavailable" result, never an exception
that stops a run. Requests are few, sequential, identified, budgeted and backed off.
"""

from __future__ import annotations

import json
import math
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np

from .config import AusraspConfig, Site
from .gfs import BLOCK_HOURS
from .thermal import Thermal

FORMAT = (
    3  # older day files are not trusted: 1 assumed a fixed clock, 2 held four hours a day, not nine
)
DAY_KEYS = tuple(f"OUT+{n}" for n in range(7))
HEIGHT, UPDRAFT = "hglider", "wstar"
# Read for the days the page shows hour by hour: the 10 m wind, the wind at the top of the thermals
# (the boundary layer) and the share of possible sunshine that reaches the ground.
SFC_WIND, TOP_WIND, SUN, BL_CLOUD = "sfcwindspd", "bltopwindspd", "sfcsunpct", "blcloudpct"
EXTRAS = (SFC_WIND, TOP_WIND, SUN, BL_CLOUD)
EXTRAS_VERSION = 2  # 2: boundary layer cloud cover added
EXTRAS_DAYS = 4  # OUT+0 to OUT+3
# The quantity named inside a wind file differs from the file's name
HEADER_PARAM = {SFC_WIND: "sfcwindSpeed", TOP_WIND: "bltopwindSpeed"}
QUANTITIES = {  # name -> (unit in the file header, smallest and largest believable value)
    HEIGHT: ("m", 0.0, 5000.0),
    UPDRAFT: ("m/sec", 0.0, 10.0),
    SFC_WIND: ("m/s", 0.0, 60.0),
    TOP_WIND: ("m/s", 0.0, 80.0),
    SUN: ("%", 0.0, 100.0),
    BL_CLOUD: ("%", 0.0, 100.0),
}
# A full refresh is 126 files for height and updraft (seven days, nine hours) and 108 more for the
# wind and sun of the four detailed days; one day's refresh is 18 or 45 files.
REQUESTS_PER_HOUR = 300
BYTES_PER_DAY = 40 * 1024 * 1024
PAUSE_S = 1.0
BACKOFF = timedelta(hours=6)


class AusraspError(Exception):
    """AUSRASP could not be used. The message is the reason shown to the owner."""


@dataclass
class Grid:
    param: str
    unit: str
    valid_utc: datetime
    run: datetime  # model start: valid time less the forecast hours
    values: np.ndarray  # rows from the south, columns from the west, already divided by Mult (the file holds scaled integers)
    offset_h: int = 10  # the clock the file is labelled in: 10 (AES) or 11 (AED)


# ---------------------------------------------------------------------------------------------
# Reading the files


def _header(lines: list[str]) -> dict[str, str]:
    for line in lines[:6]:
        if line.startswith("Day="):
            return {k: v for k, v in re.findall(r"(\w+)=\s*([^\s]+)", line)} | {
                "_day": " ".join(line.split()[1:4])
            }
    raise AusraspError("no 'Day=' header line")


def parse_grid(text: str, param: str, shape: tuple[int, int] | None = None) -> Grid:
    """Parse one grid file and check it is what we asked for. Raises AusraspError otherwise."""
    lines = [ln.strip() for ln in text.splitlines()]
    h = _header(lines)
    unit, lo, hi = QUANTITIES.get(param, ("", -math.inf, math.inf))
    if h.get("Param") != HEADER_PARAM.get(param, param):
        raise AusraspError(f"expected quantity {param}, file says {h.get('Param')}")
    if unit and h.get("Unit") != unit:
        raise AusraspError(f"{param}: expected unit {unit}, file says {h.get('Unit')}")
    try:
        year, month, day = (int(x) for x in h["_day"].split())
        lst_hour = int(h["ValidLST"]) // 100
        z_hour = int(h["ValidZ"]) // 100
        fcst_h = float(h["Fcst"])
        mult = float(h["Mult"])
    except (KeyError, ValueError) as e:
        raise AusraspError(f"unreadable header: {e}") from e
    start = next(n for n, ln in enumerate(lines) if ln.startswith("Day=")) + 1
    rows = [ln for ln in lines[start:] if ln and ln != "---"]
    try:
        values = np.array([[float(x) for x in r.split()] for r in rows], dtype=float) / mult
    except ValueError as e:
        raise AusraspError(f"{param}: non-numeric grid value") from e
    if values.ndim != 2 or (shape is not None and values.shape != shape):
        raise AusraspError(f"{param}: grid shape {values.shape}, expected {shape}")
    if not np.isfinite(values).all() or values.min() < lo or values.max() > hi:
        raise AusraspError(f"{param}: values outside {lo:g} to {hi:g}")
    # AUSRASP labels times with its own clock, which is Australian Eastern Standard (UTC+10) or
    # Daylight (UTC+11) depending on when the run was made, so the offset comes from the file's
    # own local and UTC hours rather than from an assumption.
    offset = (lst_hour - z_hour) % 24
    if offset not in (10, 11):
        raise AusraspError(f"unexpected clock offset of {offset} hours in the header")
    valid_utc = datetime(year, month, day, lst_hour, tzinfo=UTC) - timedelta(hours=offset)
    return Grid(
        param, h.get("Unit", ""), valid_utc, valid_utc - timedelta(hours=fcst_h), values, offset
    )


def nearest_cell(latlon: list, lat: float, lon: float) -> dict:
    """The grid cell nearest (lat, lon). `latlon` is AUSRASP's corner-point list (rows from the
    south); a cell's position is the midpoint of its corner and the one diagonal to it."""
    ll = np.asarray(latlon, dtype=float)
    shape: tuple[int, ...] = ll.shape
    if len(shape) != 3 or shape[2] != 2 or min(shape[:2]) < 2:
        raise AusraspError("unreadable cell position file")
    c = (ll[:-1, :-1] + ll[1:, 1:]) / 2
    dy = (c[..., 0] - lat) * 111.19
    dx = (c[..., 1] - lon) * 111.19 * math.cos(math.radians(lat))
    d = np.hypot(dx, dy)
    i, j = np.unravel_index(int(np.argmin(d)), d.shape)
    return {
        "shape": [int(c.shape[0]), int(c.shape[1])],
        "row": int(i),
        "col": int(j),
        "lat": round(float(c[i, j, 0]), 5),
        "lon": round(float(c[i, j, 1]), 5),
        "distance_km": round(float(d[i, j]), 2),
    }


# ---------------------------------------------------------------------------------------------
# The local store


def store_dir(cache_dir: Path) -> Path:
    return cache_dir / "ausrasp"


def _write(path: Path, data: object) -> None:
    """Atomic write: readers never see half a file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2))
    tmp.replace(path)


def _read(path: Path, default):
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return default


def read_status(store: Path) -> dict:
    return _read(store / "status.json", {})


def update_status(store: Path, **fields) -> dict:
    status = read_status(store)
    status.update(fields)
    _write(store / "status.json", status)
    return status


def parse_iso(value: str | None) -> datetime | None:
    try:
        return datetime.fromisoformat(value) if value else None
    except ValueError:
        return None


def _iso(t: datetime) -> str:
    return t.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


# ---------------------------------------------------------------------------------------------
# The client: identified, sequential, budgeted, and backs off


class Client:
    def __init__(
        self,
        cfg: AusraspConfig,
        store: Path,
        session,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
        sleep: Callable[[float], None] | None = None,
        version: str = "0.1",
    ):
        self.cfg, self.store, self.session = cfg, store, session
        self._now = now
        self._sleep = sleep or (lambda seconds: time.sleep(seconds))
        who = f" (+{cfg.contact})" if cfg.contact else ""
        self.headers = {"User-Agent": f"FreeFlyingForecast/{version}{who}"}
        self._last_request: float | None = None

    def check_allowed(self) -> None:
        """Raise AusraspError if the source is off, backed off, or over budget."""
        if not self.cfg.enabled:
            raise AusraspError("AUSRASP is turned off in the site configuration")
        until = parse_iso(_read(self.store / "backoff.json", {}).get("until"))
        if until and self._now() < until:
            raise AusraspError(f"holding off until {_iso(until)} after a refusal")
        budget = self._budget()
        if len(budget["requests"]) >= REQUESTS_PER_HOUR:
            raise AusraspError(f"request limit reached ({REQUESTS_PER_HOUR} an hour)")
        if budget["bytes"] >= BYTES_PER_DAY:
            raise AusraspError("daily transfer limit reached")

    def _budget(self) -> dict:
        """Requests in the last hour (kept across midnight) and bytes so far today."""
        now = self._now()
        b = _read(self.store / "budget.json", {})
        if b.get("day") != now.date().isoformat():
            b = {"day": now.date().isoformat(), "bytes": 0, "requests": b.get("requests", [])}
        b["requests"] = [t for t in b["requests"] if t > now.timestamp() - 3600]
        return b

    def get(self, relative: str) -> str:
        """GET `base_url + relative` and return the text. Raises AusraspError on any problem."""
        self.check_allowed()
        if self._last_request is not None:
            wait = PAUSE_S - (time.monotonic() - self._last_request)
            if wait > 0:
                self._sleep(wait)
        url = self.cfg.base_url + relative
        try:
            resp = self.session.get(url, headers=self.headers, timeout=30)
        except Exception as e:  # noqa: BLE001 - any network failure is just "unavailable"
            raise AusraspError(f"could not reach AUSRASP ({type(e).__name__})") from e
        finally:
            self._last_request = time.monotonic()
        b = self._budget()
        b["requests"].append(self._now().timestamp())
        size = int(resp.headers.get("content-length") or len(resp.content))
        b["bytes"] += size
        _write(self.store / "budget.json", b)
        status = resp.status_code
        if status in (403, 429) or status >= 500:
            until = self._now() + BACKOFF
            _write(self.store / "backoff.json", {"until": _iso(until), "reason": f"HTTP {status}"})
            raise AusraspError(f"AUSRASP answered HTTP {status}; holding off for 6 hours")
        if status != 200:
            raise AusraspError(f"AUSRASP answered HTTP {status} for {relative}")
        return resp.text


# ---------------------------------------------------------------------------------------------
# Finding the cell and the hours


def ensure_cell(client: Client, site: Site) -> dict:
    """The stored cell for the launch, found from AUSRASP's position file when not yet known."""
    path = client.store / "cell.json"
    cell = _read(path, None)
    if (
        cell
        and abs(cell.get("site_lat", 0) - site.lat) < 1e-6
        and abs(cell.get("site_lon", 0) - site.lon) < 1e-6
    ):
        return cell
    try:
        latlon = json.loads(client.get("latlon2d.json"))
    except json.JSONDecodeError as e:
        raise AusraspError("unreadable cell position file") from e
    cell = nearest_cell(latlon, site.lat, site.lon)
    cell.update(site_lat=site.lat, site_lon=site.lon, found_at=_iso(client._now()))
    if cell["distance_km"] > client.cfg.max_cell_km:
        raise AusraspError(
            f"nearest AUSRASP cell is {cell['distance_km']} km from the launch "
            f"(limit {client.cfg.max_cell_km} km)"
        )
    _write(path, cell)
    return cell


def wanted_hours(day: date, tz: str) -> list[datetime]:
    """The valid UTC times of the page's block starts on a local date."""
    zone = ZoneInfo(tz)
    return [
        datetime(day.year, day.month, day.day, hour, tzinfo=zone).astimezone(UTC)
        for hour in BLOCK_HOURS
    ]


def _clock_guess(stamp: str, tz: str) -> int:
    """The clock AUSRASP's server was probably on when it made the run stamped `stamp`: the
    local clock of the site at that moment (UTC+10 or +11 in Victoria). Wrong guesses are caught
    by the file's own header and the other clock is tried."""
    try:
        t = datetime.strptime(stamp, "%Y%m%dT%H%MZ").replace(tzinfo=UTC)
        off = (t.astimezone(ZoneInfo(tz)).utcoffset() or timedelta(hours=10)).total_seconds() / 3600
    except ValueError:
        return 10
    return 11 if round(off) == 11 else 10


# ---------------------------------------------------------------------------------------------
# Fetching a day and refreshing from the manifest


def fetch_day(
    client: Client, key: str, stamp: str, cell: dict, site: Site, extras: bool = False
) -> dict:
    """All wanted hours of both quantities for one day, for the cell. Raises AusraspError if
    anything is missing, unreadable, or from different model runs; stores nothing in that case.

    With `extras` the wind and sun files are read too. They are optional: if one cannot be read
    (but AUSRASP itself is up) the day is kept without them and marked `"extras": false`, so the
    height and updraft are never lost for the sake of them.

    File names carry AUSRASP's own clock hour, so the hour to ask for depends on which clock the
    run used (standard or daylight time). The first file settles it: it must be valid at the
    expected UTC time or the other clock is tried, and every later file is checked the same way."""
    now = client._now()
    radius = client.cfg.cell_radius
    shape = tuple(cell["shape"])
    zone = ZoneInfo(site.timezone)
    day = now.astimezone(zone).date() + timedelta(days=int(key[4:]))

    def get(valid: datetime, offset: int, param: str) -> Grid:
        hhmm = f"{(valid + timedelta(hours=offset)).hour:02d}00"
        text = client.get(f"{key}/FCST/{param}.curr.{hhmm}lst.d2.data")
        return parse_grid(text, param, shape)  # type: ignore[arg-type]

    guess = _clock_guess(stamp, site.timezone)
    plan = wanted_hours(day, site.timezone)
    offset, first = guess, None
    for _attempt in range(2):  # the second time plans from the day the directory really holds
        for offset in (guess, 21 - guess):
            first = get(plan[0], offset, HEIGHT)
            if first.valid_utc == plan[0]:
                break
        else:
            actual = first.valid_utc.astimezone(zone).date() if first else day
            if actual == day or _attempt:
                raise AusraspError(f"{key}: the first file is not valid at the expected time")
            day = actual
            plan = wanted_hours(day, site.timezone)
            continue
        break
    assert first is not None
    values: dict[str, dict] = {}
    run = first.run
    have_extras = extras
    for valid in plan:
        entry = values.setdefault(_iso(valid), {})
        for param in (HEIGHT, UPDRAFT):
            grid = first if (param == HEIGHT and valid == plan[0]) else get(valid, offset, param)
            if grid.valid_utc != valid:
                raise AusraspError(f"{key}: {param} is not valid at the expected time")
            if grid.run != run:
                raise AusraspError(f"{key}: files are from different model runs")
            entry["height_m" if param == HEIGHT else "updraft_ms"] = block_max(
                grid.values, cell["row"], cell["col"], radius
            )
        if have_extras:
            try:
                for param in EXTRAS:
                    grid = get(valid, offset, param)
                    if grid.valid_utc != valid or grid.run != run:
                        raise AusraspError(f"{key}: {param} is not from the same run and hour")
                    # the strongest wind in the block (a ridge launch), the average sunshine
                    pick = block_mean if param in (SUN, BL_CLOUD) else block_max
                    entry[_EXTRA_KEYS[param]] = pick(grid.values, cell["row"], cell["col"], radius)
            except AusraspError as e:
                if client_blocked(e):
                    raise
                have_extras = False  # keep the thermals; the wind and sun are left out
    if extras and not have_extras:
        for entry in values.values():
            for k in _EXTRA_KEYS.values():
                entry.pop(k, None)
    return {
        "key": key,
        "format": FORMAT,
        "stamp": stamp,
        "model_start": _iso(run),
        "fetched_at": _iso(now),
        "radius": radius,
        "extras": have_extras,
        "extras_v": EXTRAS_VERSION,
        "values": values,
    }


_EXTRA_KEYS = {
    SFC_WIND: "sfc_wind_ms",
    TOP_WIND: "top_wind_ms",
    SUN: "sun_pct",
    BL_CLOUD: "bl_cloud_pct",
}


def block_mean(values: np.ndarray, row: int, col: int, radius: int) -> float:
    """The average value in the block of cells `radius` around (row, col), clipped to the grid."""
    block = values[max(row - radius, 0) : row + radius + 1, max(col - radius, 0) : col + radius + 1]
    return float(block.mean())


def block_max(values: np.ndarray, row: int, col: int, radius: int) -> float:
    """The highest value in the block of cells `radius` around (row, col), clipped to the grid."""
    block = values[max(row - radius, 0) : row + radius + 1, max(col - radius, 0) : col + radius + 1]
    return float(block.max())


def day_path(store: Path, key: str) -> Path:
    return store / "days" / f"{key}.json"


def read_day(store: Path, key: str) -> dict | None:
    d = _read(day_path(store, key), None)
    ok = isinstance(d, dict) and "values" in d and d.get("format") == FORMAT
    return d if ok else None


@dataclass
class Refresh:
    changed: list[str] = field(default_factory=list)  # day keys stored this time
    reason: str = ""  # why AUSRASP could not be used at all (empty when it could)
    problems: list[str] = field(default_factory=list)  # per-day problems


def refresh(cfg: AusraspConfig, site: Site, cache_dir: Path, session, **client_kw) -> Refresh:
    """Check the manifest and fetch the days whose stamp changed. Never raises."""
    store = store_dir(cache_dir)
    client = Client(cfg, store, session, **client_kw)
    now = client._now()
    result = Refresh()
    try:
        cell = ensure_cell(client, site)
        stamps = json.loads(client.get("version.json"))["days"]
    except (AusraspError, json.JSONDecodeError, KeyError, TypeError) as e:
        result.reason = str(e) if isinstance(e, AusraspError) else "unreadable manifest"
        update_status(store, last_check=_iso(now), fallback=_fallback(store, now, result.reason))
        return result
    seen = dict(read_status(store).get("manifest", {}))
    for key in DAY_KEYS:
        stamp = stamps.get(key)
        if not stamp:
            continue
        stored = read_day(store, key)
        if stamp != seen.get(key):  # the stamp log: every change, noticed once
            _append(
                store / "stamps.jsonl",
                {
                    "seen_at": _iso(now),
                    "key": key,
                    "old": seen.get(key),
                    "new": stamp,
                    "model_start": (stored or {}).get("model_start"),
                },
            )
            seen[key] = stamp
        want_extras = cfg.extras and int(key[4:]) < EXTRAS_DAYS
        if (
            stored
            and stored.get("stamp") == stamp
            and stored.get("radius") == cfg.cell_radius
            # a day stored without the current extras is fetched again; a stored false waits for the next stamp
            and (
                not want_extras
                or stored.get("extras") is False
                or stored.get("extras_v") == EXTRAS_VERSION
            )
        ):
            continue
        try:
            day = fetch_day(client, key, stamp, cell, site, want_extras)
        except AusraspError as e:
            result.problems.append(f"{key}: {e}")
            if client_blocked(e):
                result.reason = str(e)
                break
            continue
        if stored and stored.get("model_start", "") > day["model_start"]:
            result.problems.append(f"{key}: not replaced by an older run")
            continue
        _write(day_path(store, key), day)
        result.changed.append(key)
    fields: dict = {
        "last_check": _iso(now),
        "manifest": seen,
        "days": {k: _day_summary(d) for k in DAY_KEYS if (d := read_day(store, k))},
        "problems": result.problems,
    }
    if result.reason:
        fields["fallback"] = _fallback(store, now, result.reason)
    else:
        fields.update(last_success=_iso(now), fallback=None)
    update_status(store, **fields)
    return result


def client_blocked(e: AusraspError) -> bool:
    """True when the problem is with AUSRASP as a whole (refusal, back-off, limit), not one day."""
    return any(w in str(e) for w in ("holding off", "limit reached", "could not reach", "HTTP 5"))


def _append(path: Path, line: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        f.write(json.dumps(line) + "\n")


def _fallback(store: Path, now: datetime, reason: str) -> dict:
    old = read_status(store).get("fallback") or {}
    return {"since": old.get("since") or _iso(now), "reason": reason}


def _day_summary(d: dict | None) -> dict:
    d = d or {}
    return {k: d.get(k) for k in ("stamp", "model_start", "fetched_at")}


# ---------------------------------------------------------------------------------------------
# Offering the values to the forecast


def thermal_lookup(
    cache_dir: Path, cfg: AusraspConfig, now: datetime | None = None
) -> tuple[dict[datetime, Thermal], list[str]]:
    """{valid UTC hour: Thermal} from the stored days that are fresh enough, and the reasons any
    day was left out. Empty when AUSRASP is off. Needs no network."""
    now = now or datetime.now(UTC)
    if not cfg.enabled:
        return {}, ["AUSRASP is turned off in the site configuration"]
    store = store_dir(cache_dir)
    out: dict[datetime, Thermal] = {}
    notes: list[str] = []
    held = 0
    for key in DAY_KEYS:
        day = read_day(store, key)
        if not day:
            continue
        run = parse_iso(day.get("model_start", "").replace("Z", "+00:00"))
        if run is None:
            notes.append(f"{key}: unreadable run time")
            continue
        held += 1
        if day.get("radius") != cfg.cell_radius:
            notes.append(
                f"{key}: stored for a different cell block; fetched again at the next check"
            )
            continue
        if now - run > timedelta(hours=cfg.max_age_h):
            notes.append(f"{key}: run from {_iso(run)} is older than {cfg.max_age_h:g} hours")
            continue
        for iso, v in day["values"].items():
            t = parse_iso(iso.replace("Z", "+00:00"))
            if t is not None:
                out[t] = Thermal(
                    float(v["height_m"]),
                    float(v["updraft_ms"]),
                    _iso(run),
                    v.get("sfc_wind_ms"),
                    v.get("top_wind_ms"),
                    v.get("sun_pct"),
                    v.get("bl_cloud_pct"),
                )
    if not held:
        notes.append("no AUSRASP data has been fetched yet")
    return out, notes
