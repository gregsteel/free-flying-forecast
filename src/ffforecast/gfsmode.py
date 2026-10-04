"""GFS-only forecast: blocks and outlook straight from GFS point values.

Coarser than a regional model run (25 km grid, no terrain detail) but needs no WRF, so it works
anywhere and serves as the fallback when the regional run fails.
"""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from .config import Rules, Site
from .diagnostics import build_block, sun_from_cloud
from .gfs import BLOCK_HOURS
from .models import DETAILED_DAYS, DailyOutlook, ForecastBlock, Wind
from .outlook import outlook_from_samples
from .profile import wind_at
from .thermal import Thermal
from .units import wind_from_uv

MS_TO_KPH = 3.6


def blocks_from_samples(
    samples: list[dict],
    rules: Rules,
    site: Site,
    first_day: str,
    days: int = DETAILED_DAYS,
    thermal: dict[datetime, Thermal] | None = None,
) -> list[ForecastBlock]:
    """Blocks from GFS point values. `thermal` maps a valid UTC hour to AUSRASP's height and
    updraft; a block whose start hour is in it uses them, any other keeps the GFS estimate."""
    zone = ZoneInfo(site.timezone)
    last_day = datetime.fromisoformat(first_day).date().toordinal() + days - 1
    out = []
    for s in sorted(samples, key=lambda x: x["time"]):
        local = s["time"].astimezone(zone)
        if local.hour not in BLOCK_HOURS or not (
            datetime.fromisoformat(first_day).date().toordinal()
            <= local.date().toordinal()
            <= last_day
        ):
            continue
        gd, gs = wind_from_uv(s["u10"], s["v10"])
        if s.get("u850") is not None and s.get("v850") is not None:
            ad, as_ = wind_from_uv(s["u850"], s["v850"])
        else:
            ad, as_ = gd, gs
        launch = None
        if s.get("profile"):
            ld, ls = wind_at(site.elevation_m, s["profile"])
            launch = Wind(ld, ls * MS_TO_KPH)
        out.append(
            build_block(
                local,
                Wind(gd, gs * MS_TO_KPH),
                Wind(ad, as_ * MS_TO_KPH),
                max(s["hpbl_m"], 0.0),
                max(s["shtfl_wm2"], 0.0),
                s["t2_c"],
                site.elevation_m,
                rules,
                rain_mm_h=s.get("rain_mm_h", 0.0),
                cape_j_kg=s.get("cape_j_kg", 0.0),
                gust_kph=s.get("gust_ms", 0.0) * MS_TO_KPH,
                launch=launch,
                thermal=(thermal or {}).get(s["time"].astimezone(UTC)),
                sun_pct_gfs=_sun_pct(s, rules),
            )
        )
    return out


def _sun_pct(s: dict, rules: Rules) -> float | None:
    """Sunshine from the sample's GFS cloud layers (percent cover), when all three were read."""
    low, mid, high = s.get("cloud_low_pct"), s.get("cloud_mid_pct"), s.get("cloud_high_pct")
    if low is None or mid is None or high is None:
        return None
    return sun_from_cloud(low, mid, high, rules)


def outlook_after_blocks(
    samples: list[dict],
    rules: Rules,
    site: Site,
    first_day: str,
    block_days: int = DETAILED_DAYS,
    thermal: dict[datetime, Thermal] | None = None,
) -> list[DailyOutlook]:
    start = datetime.fromisoformat(first_day).date().toordinal() + block_days
    day = datetime.fromordinal(start).date().isoformat()
    return outlook_from_samples(samples, rules, site.timezone, site.elevation_m, day, thermal)
