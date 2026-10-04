"""Regenerate tests/fixtures/forecast.json (run: uv run python tests/make_fixture.py)."""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ffforecast.config import load_rules
from ffforecast.diagnostics import build_block
from ffforecast.models import DailyOutlook, Forecast, Wind

root = Path(__file__).resolve().parents[1]
rules = load_rules(root / "config/rules.toml")
tz = timezone(timedelta(hours=11))  # AEDT starts 2026-10-04

# (ground dir, kph, aloft dir, kph, pblh, hfx, t2)
cases = {
    "ok": (350, 12, 10, 14, 1200, 90, 15),  # decent thermals, updraft about 1.5 m/s
    "good": (350, 12, 10, 14, 1500, 380, 16),  # strong thermals, updraft about 2.6 m/s
    "strong": (350, 12, 10, 14, 2200, 700, 18),  # very strong thermals, updraft about 3.6 m/s
    "poor": (350, 12, 10, 14, 100, 20, 14),
    "turbulent": (350, 20, 10, 20, 1600, 380, 15),
    "dangerous": (200, 30, 220, 38, 1200, 180, 12),
}
# (rain mm/h, CAPE J/kg, gust kph) per case; the dangerous case is also a wet storm
weather = {
    "dangerous": (2.3, 900, 40),
    "turbulent": (0, 0, 20),
}  # gusts under the limit: only the wind differs by glider
# Percent of possible sun reaching the ground (GFS-style cloud estimate); anything else is 90
sun = {"poor": 35, "turbulent": 60}
# Hourly blocks, 10:00 to 18:00. The original four per day stay at 11, 13, 15 and 17 o'clock; the other
# hours are Ok, so every grade still appears. Day 1 keeps its original order; days 2 to 4 bring in Ok and Strong.
per_day = [
    ["good", "poor", "turbulent", "dangerous"],
    ["ok", "good", "strong", "poor"],
    ["strong", "ok", "turbulent", "dangerous"],
    ["good", "ok", "poor", "strong"],
]
blocks = []
for day, four in enumerate(per_day):
    for hour in range(10, 19):
        key = four[(hour - 11) // 2] if hour in (11, 13, 15, 17) else "ok"
        start = datetime(2026, 10, 4 + day, hour, tzinfo=tz)
        g, gk, a, ak, pb, hfx, t2 = cases[key]
        rain, cape, gust = weather.get(key, (0, 0, 0))
        blocks.append(
            build_block(
                start, Wind(g, gk), Wind(a, ak), pb, hfx, t2, 785, rules,
                rain_mm_h=rain, cape_j_kg=cape, gust_kph=gust,
                launch=Wind(g + 5, gk + 2), sun_pct_gfs=sun.get(key, 90),
            )
        )  # fmt: skip

fc = Forecast(
    site="mystic",
    model="NOAA GFS, WRF 4.6 (fixture)",
    cycle="2026-10-03T00Z",
    generated_at="2026-10-03T14:00:00+11:00",
    rules_version=rules.version,
    blocks=blocks,
    outlook=[
        DailyOutlook(
            "2026-10-08",
            Wind(200, 25),
            "dangerous",
            rain_mm_h=2.0,
            cape_j_kg=900,
            verdict_hg="dangerous",
        ),
        DailyOutlook("2026-10-09", Wind(10, 22), "turbulent", verdict_hg="good"),
        DailyOutlook("2026-10-10", Wind(340, 8), "poor", verdict_hg="poor"),
    ],
)
(root / "tests/fixtures/forecast.json").write_text(json.dumps(fc.to_dict(), indent=2))
print("wrote fixture")
