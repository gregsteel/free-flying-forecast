"""Compare the forecasts kept in `state/history/` with the wind the station measured.

For each hourly block on a date, the measured conditions are taken over the hour centred on the block's
start (the 5 minute summaries from `observations.py`). Two forecasts of each date are scored: the one
that stood the evening before ("day before": the last issued before local midnight) and the one that stood
at breakfast ("morning": the last issued before 08:00 local). See docs/verification.md.

What is scored, forecast minus measured (so a positive bias means the forecast was too high):

- wind speed: the global model's 10 m wind, its wind at launch height, AUSRASP's 10 m wind, and the
  speed the grade was judged on (the stronger of launch and AUSRASP);
- gusts: the model's 10 m gust and the estimated gust at launch, against the strongest gust measured;
- ground temperature;
- thermal height against the cumulus base the station works out (meaningful only when the forecast
  height is near it, so only blocks within 300 m below it or above are counted);
- wind direction at launch (only when the wind was at least 5 kph);
- "rough air": whether the forecast and the measurement were each at or over the Bad wind or gust
  limit, as hits, false alarms, misses and quiet days.
"""

from __future__ import annotations

from datetime import UTC, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from . import history, observations
from .config import Rules
from .units import angle_diff, kph_to_mph

MIN_BUCKETS = 6  # of the 12 five minute buckets in an hour, for the measurement to count
COARSE_N = 12  # a bucket built from fewer readings came from a thinned (7 or 30 day) log
CLOUD_WINDOW_M = 300
KINDS = ("day_before", "morning")


def measured_hour(buckets: dict[str, dict], start: datetime) -> dict | None:
    """The measured conditions in the hour centred on `start` (aware), or None without enough data."""
    lo, hi = start - timedelta(minutes=30), start + timedelta(minutes=30)
    got = []
    for iso, b in buckets.items():
        t = observations.parse_iso(iso)
        if t is not None and lo <= t < hi:
            got.append(b)
    if len(got) < MIN_BUCKETS:
        return None
    weights = [b["n"] for b in got]
    total = sum(weights)
    dirs = [(b["dir_deg"], b["avg_kph"]) for b in got if b.get("dir_deg") is not None]
    cloud = [b["cloudbase_m"] for b in got if b.get("cloudbase_m") is not None]
    temp = [b["temp_c"] for b in got if b.get("temp_c") is not None]
    return {
        "avg_kph": sum(b["avg_kph"] * w for b, w in zip(got, weights, strict=True)) / total,
        "gust_kph": max(b["gust_kph"] for b in got),
        "dir_deg": observations.circular_mean([d for d, _ in dirs], [w for _, w in dirs])
        if dirs
        else None,
        "temp_c": sum(temp) / len(temp) if temp else None,
        "cloudbase_m": sum(cloud) / len(cloud) if cloud else None,
        "buckets": len(got),
        "coarse": min(weights) < COARSE_N,
    }


def pick_snapshots(snaps: list[dict], date: str, tz: str) -> dict[str, dict]:
    """{kind: the snapshot that stood at that time}; a kind with no snapshot is left out."""
    zone = ZoneInfo(tz)
    day = datetime.fromisoformat(date).date()
    cutoffs = {
        "day_before": datetime.combine(day, time(0), tzinfo=zone),
        "morning": datetime.combine(day, time(8), tzinfo=zone),
    }
    out = {}
    for kind, cutoff in cutoffs.items():
        before = [s for s in snaps if datetime.fromisoformat(s["issued"]) < cutoff]
        if before:
            out[kind] = max(before, key=lambda s: s["issued"])
    return out


def _judged_kph(b: dict, rules: Rules) -> float | None:
    launch = (b.get("wind_launch") or b.get("wind_ground") or {}).get("kph")
    if launch is None:
        return None
    rasp = b.get("wind_ausrasp_kph")
    return max(launch, rasp) if rasp is not None and rules.ausrasp_wind_counts else launch


def block_rows(snapshot: dict, buckets: dict[str, dict], rules: Rules, tz: str) -> list[dict]:
    """One row per block of the snapshot that has a measurement: the forecast and measured values."""
    rows = []
    for b in snapshot["blocks"]:
        start = datetime.fromisoformat(b["start"])
        m = measured_hour(buckets, start.astimezone(UTC))
        if m is None:
            continue
        gust_est = b.get("gust_launch_kph")
        rows.append(
            {
                "time": start.astimezone(ZoneInfo(tz)).strftime("%H:%M"),
                "measured": m,
                "f_ground": (b.get("wind_ground") or {}).get("kph"),
                "f_launch": (b.get("wind_launch") or {}).get("kph"),
                "f_ausrasp": b.get("wind_ausrasp_kph"),
                "f_judged": _judged_kph(b, rules),
                "f_gust10": b.get("gust_kph"),
                "f_gust_launch": gust_est,
                "f_temp": b.get("temp_ground_c"),
                "f_height": b.get("thermal_height_m"),
                "f_dir": (b.get("wind_launch") or b.get("wind_ground") or {}).get("dir_deg"),
                "f_verdict": b.get("verdict_pg"),
            }
        )
    return rows


def _stats(pairs: list[tuple[float, float]]) -> dict | None:
    """Bias (forecast minus measured) and mean absolute error over (forecast, measured) pairs."""
    if not pairs:
        return None
    diffs = [f - m for f, m in pairs]
    return {
        "n": len(diffs),
        "bias": round(sum(diffs) / len(diffs), 1),
        "mae": round(sum(abs(d) for d in diffs) / len(diffs), 1),
    }


def _rough(avg_kph: float | None, gust_kph: float | None, rules: Rules) -> bool | None:
    if avg_kph is None and gust_kph is None:
        return None
    wind = avg_kph is not None and kph_to_mph(avg_kph) >= rules.speed_orange_from_mph
    gust = gust_kph is not None and kph_to_mph(gust_kph) >= rules.gust_orange_from_mph
    return wind or gust


def summarise(rows: list[dict], rules: Rules) -> dict:
    """The scores over a set of block rows (see the module's description)."""

    def pairs(key: str, field: str) -> list[tuple[float, float]]:
        return [
            (r[key], r["measured"][field])
            for r in rows
            if r[key] is not None and r["measured"][field] is not None
        ]

    out: dict = {"blocks": len(rows), "coarse_blocks": sum(r["measured"]["coarse"] for r in rows)}
    out["wind"] = {
        "ground_10m": _stats(pairs("f_ground", "avg_kph")),
        "launch": _stats(pairs("f_launch", "avg_kph")),
        "ausrasp_10m": _stats(pairs("f_ausrasp", "avg_kph")),
        "judged": _stats(pairs("f_judged", "avg_kph")),
    }
    out["gust"] = {
        "model_10m": _stats(pairs("f_gust10", "gust_kph")),
        "estimate_at_launch": _stats(pairs("f_gust_launch", "gust_kph")),
    }
    out["temperature_c"] = _stats(pairs("f_temp", "temp_c"))
    capped = [
        (r["f_height"], r["measured"]["cloudbase_m"])
        for r in rows
        if r["f_height"] is not None
        and r["measured"]["cloudbase_m"] is not None
        and r["f_height"] >= r["measured"]["cloudbase_m"] - CLOUD_WINDOW_M
    ]
    out["thermal_height_vs_cumulus_base_m"] = _stats(capped)
    dirs = [
        angle_diff(r["f_dir"], r["measured"]["dir_deg"])
        for r in rows
        if r["f_dir"] is not None
        and r["measured"]["dir_deg"] is not None
        and r["measured"]["avg_kph"] >= 5
    ]
    out["direction_mae_deg"] = (
        {"n": len(dirs), "mae": round(sum(dirs) / len(dirs))} if dirs else None
    )
    table = {"hit": 0, "false_alarm": 0, "miss": 0, "quiet": 0}
    for r in rows:
        f = _rough(
            r["f_judged"],
            r["f_gust_launch"] if r["f_gust_launch"] is not None else r["f_gust10"],
            rules,
        )
        a = _rough(r["measured"]["avg_kph"], r["measured"]["gust_kph"], rules)
        if f is None or a is None:
            continue
        table["hit" if f and a else "false_alarm" if f else "miss" if a else "quiet"] += 1
    out["rough_air"] = table
    return out


def compare_dates(
    history_dir: Path, obs_dir: Path, dates: list[str], rules: Rules, tz: str
) -> dict:
    """{"days": {date: {kind: rows}}, "summary": {kind: summarise(...)}} over the dates that have both
    a forecast and measurements."""
    days: dict[str, dict[str, list[dict]]] = {}
    pooled: dict[str, list[dict]] = {k: [] for k in KINDS}
    for date in dates:
        buckets = observations.read_day(obs_dir, date)
        # a local date spans two UTC dates' worth of buckets near midnight; the file is by local date
        snaps = history.read_day(history_dir, date)
        if not buckets or not snaps:
            continue
        for kind, snap in pick_snapshots(snaps, date, tz).items():
            rows = block_rows(snap, buckets, rules, tz)
            if rows:
                days.setdefault(date, {})[kind] = rows
                pooled[kind].extend(rows)
    return {
        "days": days,
        "summary": {k: summarise(v, rules) for k, v in pooled.items() if v},
    }


def _fmt(s: dict | None, unit: str = "kph") -> str:
    if not s:
        return "no data"
    return f"bias {s['bias']:+.1f} {unit}, mean error {s['mae']:.1f} {unit}  (n={s['n']})"


def format_report(result: dict, show_blocks: bool = False) -> str:
    """A plain-text report of a `compare_dates` result."""
    if not result["summary"]:
        return (
            "Nothing to compare yet: a date needs both a saved forecast (state/history) and "
            "measured readings (state/observations).\n"
        )
    lines: list[str] = []
    label = {
        "day_before": "Forecast made the evening before",
        "morning": "Forecast made that morning",
    }
    for kind in KINDS:
        s = result["summary"].get(kind)
        if not s:
            continue
        dates = sorted(d for d, k in result["days"].items() if kind in k)
        lines += [
            f"{label[kind]}: {s['blocks']} hourly blocks over {len(dates)} days ({dates[0]} to {dates[-1]})",
            "  Wind speed (forecast minus measured average):",
        ]
        names = {
            "ground_10m": "global model, 10 m",
            "launch": "global model, at launch height",
            "ausrasp_10m": "AUSRASP, 10 m",
            "judged": "the speed the grade used",
        }
        lines += [f"    {names[k]:<32} {_fmt(v)}" for k, v in s["wind"].items()]
        lines.append("  Gusts (forecast minus the strongest gust measured in the hour):")
        gn = {"model_10m": "global model, 10 m", "estimate_at_launch": "estimate at launch"}
        lines += [f"    {gn[k]:<32} {_fmt(v)}" for k, v in s["gust"].items()]
        lines.append(f"  Ground temperature: {_fmt(s['temperature_c'], 'C')}")
        lines.append(
            "  Thermal height against the cumulus base the station works out (blocks near it): "
            + _fmt(s["thermal_height_vs_cumulus_base_m"], "m")
        )
        d = s["direction_mae_deg"]
        lines.append(
            "  Wind direction at launch: "
            + (
                f"mean error {d['mae']} degrees (n={d['n']}, wind of 5 kph or more)"
                if d
                else "no data"
            )
        )
        r = s["rough_air"]
        lines.append(
            f"  Rough air (wind or gust at the Bad limit): {r['hit']} hits, "
            f"{r['false_alarm']} false alarms, {r['miss']} misses, {r['quiet']} quiet"
        )
        if s["coarse_blocks"]:
            lines.append(
                f"  Note: {s['coarse_blocks']} blocks used a thinned (7 or 30 day) log, so their "
                "measured gusts are low."
            )
        lines.append("")
    if show_blocks:
        lines.append("Block by block (morning forecast, else day before):")
        lines.append(
            "  date        time  measured avg/gust  launch  AUSRASP  judged  gust est  verdict"
        )
        for date in sorted(result["days"]):
            kinds = result["days"][date]
            rows = kinds.get("morning") or kinds.get("day_before") or []
            for r in rows:
                m = r["measured"]
                cells = [r["f_launch"], r["f_ausrasp"], r["f_judged"], r["f_gust_launch"]]
                lines.append(
                    f"  {date}  {r['time']}  {m['avg_kph']:>6.0f}/{m['gust_kph']:<6.0f}    "
                    + "  ".join(f"{(round(c) if c is not None else '-')!s:>6}" for c in cells)
                    + f"  {r['f_verdict']}"
                )
    return "\n".join(lines).rstrip() + "\n"


def dates_back(today: datetime, days: int, tz: str) -> list[str]:
    """The last `days` local dates before today, oldest first."""
    d = today.astimezone(ZoneInfo(tz)).date()
    return [(d - timedelta(days=i)).isoformat() for i in range(days, 0, -1)]
