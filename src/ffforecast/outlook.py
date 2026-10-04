"""Days 5 to 7 outlook straight from GFS point values (no regional model)."""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from .config import Rules
from .diagnostics import thermal_quality_pct, usable_thermal_height_asl, wstar
from .gfs import BLOCK_HOURS
from .grading import grade_block
from .models import DailyOutlook, Wind
from .profile import LEVELS_HPA, usable_profile, wind_at
from .thermal import Thermal
from .units import wind_from_uv

FLY_HOURS = BLOCK_HOURS  # local hours that count towards a day's outlook


def _day_thermals(
    thermal: dict[datetime, Thermal] | None, day: str, zone: ZoneInfo
) -> list[Thermal]:
    """AUSRASP's values at the page's block start times on a local day."""
    if not thermal:
        return []
    d = datetime.fromisoformat(day)
    times = (datetime(d.year, d.month, d.day, h, tzinfo=zone).astimezone(UTC) for h in BLOCK_HOURS)
    return [thermal[t] for t in times if t in thermal]


def outlook_from_samples(
    samples: list[dict],
    rules: Rules,
    tz: str,
    terrain_m: float,
    first_day: str,
    thermal: dict[datetime, Thermal] | None = None,
) -> list[DailyOutlook]:
    """samples: dicts with time (aware UTC datetime), u10, v10 (m/s), hpbl_m, shtfl_wm2 (W/m2,
    positive upward), t2_c. One DailyOutlook per local day on or after first_day, using samples
    in the flying hours. Wind direction comes from the middle sample, speed is the day's
    strongest, and thermal values are averaged."""
    zone = ZoneInfo(tz)
    by_day: dict[str, list[dict]] = defaultdict(list)
    for s in samples:
        local = s["time"].astimezone(zone)
        if local.hour in FLY_HOURS and local.date().isoformat() >= first_day:
            by_day[local.date().isoformat()].append(s)
    out = []
    for day in sorted(by_day):
        rows = by_day[day]
        dirs, kphs, ups, heights = [], [], [], []
        for s in rows:
            if s.get("profile"):  # wind at launch altitude when we have the profile
                d, sp = wind_at(terrain_m, s["profile"])
            else:
                d, sp = wind_from_uv(s["u10"], s["v10"])
            dirs.append(d)
            kphs.append(sp * 3.6)
            up_i = wstar(max(s["shtfl_wm2"], 0.0), s["hpbl_m"], s["t2_c"] + 273.15)
            ups.append(up_i)
            heights.append(usable_thermal_height_asl(s["hpbl_m"], up_i, terrain_m, rules))
        mid = len(rows) // 2
        up = sum(ups) / len(ups)
        height = sum(heights) / len(heights)
        # AUSRASP's figures for the day when at least two of its hours are held (spec 003 FR-009)
        a = _day_thermals(thermal, day, zone)
        source = "ausrasp" if len(a) >= 2 else "gfs"
        limits = {}
        if source == "ausrasp":
            up = sum(t.updraft_ms for t in a) / len(a)
            height = max(sum(t.height_m for t in a) / len(a), terrain_m)
            limits = {
                "good_updraft_ms": rules.ausrasp_good_updraft_ms,
                "strong_updraft_ms": rules.ausrasp_strong_updraft_ms,
            }
        quality = thermal_quality_pct(
            up,
            max(kphs),
            rules.quality_full_updraft_ms,
            rules.quality_wind_threshold_kph,
            rules.quality_wind_penalty_per_kph,
        )
        rain = max(s.get("rain_mm_h", 0.0) for s in rows)
        cape = max(s.get("cape_j_kg", 0.0) for s in rows)
        gust = max(s.get("gust_ms", 0.0) for s in rows) * 3.6
        verdict, _ = grade_block(
            dirs[mid],
            max(kphs),
            max(kphs),
            quality,
            height,
            rules,
            "pg",
            rain,
            cape,
            gust,
            up,
            **limits,
        )
        verdict_hg, _ = grade_block(
            dirs[mid],
            max(kphs),
            max(kphs),
            quality,
            height,
            rules,
            "hg",
            rain,
            cape,
            gust,
            up,
            **limits,
        )
        out.append(
            DailyOutlook(
                day,
                Wind(round(dirs[mid]), round(max(kphs))),
                verdict,
                "low",
                round(rain, 2),
                round(cape),
                verdict_hg,
                source,
            )
        )
    return out


# (discipline, category, number, typeOfLevel, level) -> sample key. HPBL has no standard
# short name in ecCodes, so messages are matched by their numeric identifiers.
_WANTED = {
    (0, 2, 2, "heightAboveGround", 10): "u10",
    (0, 2, 3, "heightAboveGround", 10): "v10",
    (0, 0, 0, "heightAboveGround", 2): "t2m_k",
    (0, 3, 196, "surface", 0): "hpbl_m",
    (0, 0, 11, "surface", 0): "shtfl_wm2",  # positive upward (checked against real data)
    (0, 1, 7, "surface", 0): "prate",  # kg/m2/s, instantaneous only (see the step check)
    (0, 7, 6, "surface", 0): "cape",  # J/kg
    (0, 2, 22, "surface", 0): "gust_ms",
    (0, 3, 0, "surface", 0): "sp_pa",
    (0, 3, 5, "surface", 0): "orog_m",
    (0, 6, 3, "lowCloudLayer", 0): "cloud_low",  # percent cover, instantaneous only
    (0, 6, 4, "middleCloudLayer", 0): "cloud_mid",
    (0, 6, 5, "highCloudLayer", 0): "cloud_high",
    (0, 2, 2, "isobaricInhPa", 850): "u850",
    (0, 2, 3, "isobaricInhPa", 850): "v850",
    **{
        (0, cat, num, "isobaricInhPa", lvl): f"{name}{lvl}"
        for lvl in LEVELS_HPA
        for cat, num, name in ((2, 2, "u"), (2, 3, "v"), (3, 5, "gh"))
    },
}


_INSTANT_ONLY = ("prate", "cloud_low", "cloud_mid", "cloud_high")


def _int(handle, key: str) -> int:
    import eccodes

    return int(eccodes.codes_get(handle, key))  # pyright: ignore[reportArgumentType]


def _profile(v: dict[str, float]) -> list[tuple[float, float, float]]:
    """Vertical wind profile (height_m, u, v) at the point, from a sample's raw GFS values."""
    if not {"orog_m", "sp_pa", "u10", "v10"} <= v.keys():
        return []
    levels = {
        lvl: (v[f"gh{lvl}"], v[f"u{lvl}"], v[f"v{lvl}"])
        for lvl in LEVELS_HPA
        if {f"gh{lvl}", f"u{lvl}", f"v{lvl}"} <= v.keys()
    }
    return usable_profile(v["orog_m"], v["sp_pa"], v["u10"], v["v10"], levels)


def read_gfs_samples(files: list[Path], lat: float, lon: float) -> list[dict]:
    """Read downloaded GFS GRIB2 subset files and return per-time samples at the nearest grid
    point: dicts with time (aware UTC), u10, v10 (m/s), hpbl_m, shtfl_wm2, t2_c."""
    import eccodes

    by_time: dict[datetime, dict[str, float]] = defaultdict(dict)
    windows: dict[datetime, tuple[int, int]] = {}
    for path in files:
        with path.open("rb") as f:
            while (h := eccodes.codes_grib_new_from_file(f)) is not None:
                try:
                    key = (
                        _int(h, "discipline"),
                        _int(h, "parameterCategory"),
                        _int(h, "parameterNumber"),
                        str(eccodes.codes_get(h, "typeOfLevel")),
                        _int(h, "level"),
                    )
                    name = _WANTED.get(key)
                    if name is None:
                        continue
                    if name in _INSTANT_ONLY and "-" in str(eccodes.codes_get(h, "stepRange")):
                        continue  # skip the 6-hour average; take the instantaneous value
                    date = _int(h, "validityDate")
                    hhmm = _int(h, "validityTime")
                    t = datetime(
                        date // 10000, date // 100 % 100, date % 100, hhmm // 100, hhmm % 100,
                        tzinfo=UTC,
                    )  # fmt: skip
                    by_time[t][name] = float(eccodes.codes_grib_find_nearest(h, lat, lon)[0].value)
                    if name == "shtfl_wm2":
                        windows[t] = _window(str(eccodes.codes_get(h, "stepRange")))
                finally:
                    eccodes.codes_release(h)
    out = []
    for t, v in sorted(by_time.items()):
        if {"u10", "v10", "hpbl_m", "t2m_k"} <= v.keys():
            out.append(
                {
                    "time": t,
                    "u10": v["u10"],
                    "v10": v["v10"],
                    "hpbl_m": v["hpbl_m"],
                    "shtfl_wm2": v.get("shtfl_wm2", 0.0),
                    "shtfl_window": windows.get(t),
                    "t2_c": v["t2m_k"] - 273.15,
                    "rain_mm_h": v.get("prate", 0.0) * 3600,
                    "cape_j_kg": v.get("cape", 0.0),
                    "gust_ms": v.get("gust_ms", 0.0),
                    "cloud_low_pct": v.get("cloud_low"),
                    "cloud_mid_pct": v.get("cloud_mid"),
                    "cloud_high_pct": v.get("cloud_high"),
                    "u850": v.get("u850"),
                    "v850": v.get("v850"),
                    "profile": _profile(v),
                }
            )
    return out


def _window(step_range: str) -> tuple[int, int]:
    """'30-33' -> (30, 33); a single hour '33' -> (33, 33)."""
    lo, _, hi = step_range.partition("-")
    return int(lo), int(hi or lo)


def read_flux_samples(
    files: list[Path], lat: float, lon: float
) -> dict[datetime, tuple[float, tuple[int, int]]]:
    """Surface heating averages (W/m2, positive upward) with their averaging window, by valid
    time, from files that hold only the heating field."""
    import eccodes

    out: dict[datetime, tuple[float, tuple[int, int]]] = {}
    for path in files:
        with path.open("rb") as f:
            while (h := eccodes.codes_grib_new_from_file(f)) is not None:
                try:
                    if (
                        _int(h, "discipline"),
                        _int(h, "parameterCategory"),
                        _int(h, "parameterNumber"),
                    ) != (0, 0, 11):
                        continue
                    date, hhmm = _int(h, "validityDate"), _int(h, "validityTime")
                    t = datetime(
                        date // 10000, date // 100 % 100, date % 100, hhmm // 100, hhmm % 100,
                        tzinfo=UTC,
                    )  # fmt: skip
                    value = float(eccodes.codes_grib_find_nearest(h, lat, lon)[0].value)
                    out[t] = (value, _window(str(eccodes.codes_get(h, "stepRange"))))
                finally:
                    eccodes.codes_release(h)
    return out


def deaccumulate_flux(
    samples: list[dict], previous: dict[datetime, tuple[float, tuple[int, int]]]
) -> list[dict]:
    """Replace each sample's window-average heating with the heating at that hour.

    GFS gives the average since the last multiple of 6 hours. With the average a hour earlier from
    the same window, the hour's own value is n * avg(n) - (n - 1) * avg(n - 1), where n is the
    hours into the window. Without that earlier hour the average is kept. Averages are what made
    the morning look too weak and the late afternoon too strong."""
    for s in samples:
        window = s.get("shtfl_window")
        if not window:
            continue
        lo, hi = window
        n = hi - lo
        s["shtfl_avg_wm2"] = s["shtfl_wm2"]
        if n <= 1:
            continue
        prev = previous.get(s["time"] - timedelta(hours=1))
        if prev is None or prev[1] != (lo, hi - 1):
            continue
        s["shtfl_wm2"] = n * s["shtfl_wm2"] - (n - 1) * prev[0]
    return samples
