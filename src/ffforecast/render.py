"""Render the static page from forecast.json."""

from __future__ import annotations

import json
import math
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup, escape

from .config import Rules, Site
from .gfs import BLOCK_HOURS
from .grading import gust_limits_mph
from .models import DETAILED_DAYS, OUTLOOK_DAYS, Forecast, Wind
from .units import (
    FT_PER_M,
    angle_diff,
    c_to_f,
    deg_to_compass,
    kph_to_kts,
    mph_to_kph,
)

# Glider types. The first is the default. Each is rendered side by side and CSS shows the chosen one.
GLIDERS = (("pg", "Paraglider", "PG"), ("hg", "Hang glider", "HG"))


def clock12(hour: int, minute: int = 0) -> str:
    """A 12-hour clock time without am/pm, e.g. 13:00 -> '1:00' (the flying day makes it obvious)."""
    return f"{hour % 12 or 12}:{minute:02d}"


BOM_LINKS = {"bom_warnings": "https://www.bom.gov.au/vic/warnings/"}
ICONS = {
    "ok": "\U0001f44c",  # OK hand
    "good": "\U0001f44d",  # thumbs up
    "strong": "\U0001f525",
    # Poor is the thumbs-up turned on its side (there is no sideways thumb emoji): the same picture as
    # the others, so it matches them in every font. The page's CSS does the turning.
    "poor": Markup('<span class="sideways">\U0001f44d</span>'),
    "bad": "\U0001f44e",  # thumbs down: rough air and dangerous conditions are one grade
}
LABELS = {
    "ok": "Ok",
    "good": "Good",
    "strong": "Strong",
    "poor": "Poor",
    "bad": "Bad",
}
# Sunshine reaching the ground: how much of the sun a block gets, as an icon and a few words
SUN_SUNNY, SUN_PARTLY, SUN_SHADED = "\u2600\ufe0f", "\u26c5", "\u2601\ufe0f"


def sun_indicator(sun_pct: int | None, rules: Rules) -> tuple[str, str]:
    """(icon, words) for a block's sunshine, or ('', '') when it is not known."""
    if sun_pct is None:
        return "", ""
    if sun_pct >= rules.sun_full_pct:
        return SUN_SUNNY, f"Sunny: {sun_pct}% of the possible sun reaches the ground"
    if sun_pct >= rules.sun_shaded_pct:
        return SUN_PARTLY, f"Some cloud shading: {sun_pct}% of the possible sun reaches the ground"
    return SUN_SHADED, f"Mostly shaded: only {sun_pct}% of the possible sun reaches the ground"


TEMPLATE_DIR = Path(__file__).resolve().parents[2] / "templates"


# Unit choices. The first of each group is the default (knots, metres, Celsius).
SPEED_UNITS = ("kts", "kph")
ALT_UNITS = ("m", "ft")
TEMP_UNITS = ("c", "f")


def _u(cls: str, text: str) -> str:
    return f'<span class="u {cls}">{text}</span>'


def spd(kph: float) -> Markup:
    """A speed in every supported unit; CSS shows only the selected one."""
    return Markup(_u("s-kts", f"{kph_to_kts(kph):.0f} kts") + _u("s-kph", f"{kph:.0f} kph"))


def _down(value: float, step: float = 100.0) -> float:
    """Round down to a multiple of `step` (the thermal figures are not that precise)."""
    return math.floor(value / step + 1e-9) * step


def height_down(m: float, short: bool = False) -> Markup:
    """A thermal height rounded DOWN to the nearest 100 m, or to the nearest 100 ft in feet, in
    both units (CSS shows the chosen one). The forecast is not that precise, and rounding down
    keeps the figure on the safe side."""
    m_r, ft_r = _down(m), _down(m * FT_PER_M)
    if short:
        return Markup(_u("a-m", f"{m_r:.0f}") + _u("a-ft", f"{ft_r:.0f}"))
    return Markup(_u("a-m", f"{m_r:,.0f} m") + _u("a-ft", f"{ft_r:,.0f} ft"))


def alt(m: float) -> Markup:
    return Markup(_u("a-m", f"{m:,.0f} m") + _u("a-ft", f"{m * FT_PER_M:,.0f} ft"))


def rate(ms: float) -> Markup:
    """Updraft strength: follows the altitude unit (m/s, or ft/sec to one decimal)."""
    return Markup(_u("a-m", f"{ms:.1f} m/s") + _u("a-ft", f"{ms * FT_PER_M:.1f} ft/sec"))


def _est(kph: float | None) -> Markup:
    """An estimated gust, or 'not available' for a forecast made before gusts were estimated."""
    return spd_short(kph) if kph is not None else Markup("not available")


def spd_short(kph: float) -> Markup:
    """A speed as bare numbers, for the narrow hourly cells (the unit is in the settings)."""
    return Markup(_u("s-kts", f"{kph_to_kts(kph):.0f}") + _u("s-kph", f"{kph:.0f}"))


def rate_whole(ms: float) -> Markup:
    """An updraft published in whole m/s (AUSRASP's): no false decimal in either unit."""
    return Markup(_u("a-m", f"{ms:.0f} m/s") + _u("a-ft", f"{ms * FT_PER_M:.1f} ft/sec"))


def rain(mm_h: float) -> Markup:
    """Rain rate; follows the height unit (mm/h or in/h)."""
    return Markup(_u("a-m", f"{mm_h:.1f} mm/h") + _u("a-ft", f"{mm_h / 25.4:.2f} in/h"))


def temp(c: float, decimals: int = 0) -> Markup:
    return Markup(
        _u("t-c", f"{c:.{decimals}f} \u00b0C") + _u("t-f", f"{c_to_f(c):.{decimals}f} \u00b0F")
    )


_KPH_RE = re.compile(r"(\d+(?:\.\d+)?) kph")
_M_RE = re.compile(r"(\d+(?:\.\d+)?) m\b")
_RAIN_RE = re.compile(r"(\d+(?:\.\d+)?) mm/h")


def unitise(text: str) -> Markup:
    """Turn plain-text reasons such as 'Wind 12 kph' or '885 m' into unit-switchable markup."""
    found = sorted(
        [*_KPH_RE.finditer(text), *_M_RE.finditer(text), *_RAIN_RE.finditer(text)],
        key=lambda m: m.start(),
    )
    out, pos = [], 0
    for m in found:
        out.append(str(escape(text[pos : m.start()])))
        value = float(m.group(1))
        if m.group(0).endswith("mm/h"):
            out.append(str(rain(value)))
        elif m.group(0).endswith("kph"):
            out.append(str(spd(value)))
        else:
            out.append(str(height_down(value)))  # reasons quote thermal heights
        pos = m.end()
    out.append(str(escape(text[pos:])))
    return Markup("".join(out))


def direction_class(dir_deg: float, rules: Rules) -> str:
    """'ok' inside the green sector, 'marginal' just outside it, 'off' beyond that.
    Uses the same sector and margin as the grading, so the arrow always agrees with the verdict."""
    off = angle_diff(dir_deg, rules.sector_center_deg)
    if off <= rules.sector_half_width_deg:
        return "ok"
    if off <= rules.sector_half_width_deg + rules.marginal_margin_deg:
        return "marginal"
    return "off"


def _wind_short(w: Wind) -> Markup:
    return spd_short(w.kph)


# Numbers only, for the detail table: the unit is in the row label (see _row_label).
def _wind_num(w: Wind) -> Markup:
    return Markup(f"{deg_to_compass(w.dir_deg)} ") + spd_short(w.kph)


def _height_num(m: float) -> Markup:
    m_r, ft_r = _down(m), _down(m * FT_PER_M)
    return Markup(_u("a-m", f"{m_r:,.0f}") + _u("a-ft", f"{ft_r:,.0f}"))


def _rate_num(ms: float, whole: bool) -> Markup:
    d = 0 if whole else 1
    return Markup(_u("a-m", f"{ms:.{d}f}") + _u("a-ft", f"{ms * FT_PER_M:.1f}"))


def _temp_num(c: float, decimals: int = 0) -> Markup:
    return Markup(_u("t-c", f"{c:.{decimals}f}") + _u("t-f", f"{c_to_f(c):.{decimals}f}"))


def _rain_num(mm_h: float) -> Markup:
    return Markup(_u("a-m", f"{mm_h:.1f}") + _u("a-ft", f"{mm_h / 25.4:.2f}"))


# Unit names for the row labels; each switches with the settings like the numbers do.
_U_SPD = _u("s-kts", "kts") + _u("s-kph", "kph")
_U_ALT = _u("a-m", "m") + _u("a-ft", "ft")
_U_RATE = _u("a-m", "m/s") + _u("a-ft", "ft/sec")
_U_TEMP = _u("t-c", "\u00b0C") + _u("t-f", "\u00b0F")
_U_RAIN = _u("a-m", "mm/h") + _u("a-ft", "in/h")


def _row_label(name: str, units: str = "") -> Markup:
    return Markup(f'{name} <span class="nb">({units})</span>' if units else name)


def _wind(w: Wind) -> Markup:
    return Markup(f"{deg_to_compass(w.dir_deg)} ") + spd(w.kph)


def _gust_limits(rules: Rules, glider: str) -> dict[str, Markup]:
    o, r, ao, ar = gust_limits_mph(rules, glider)
    return {
        "gust_orange": spd(mph_to_kph(o)),
        "gust_red": spd(mph_to_kph(r)),
        "gust_aloft_orange": spd(mph_to_kph(ao)),
        "gust_aloft_red": spd(mph_to_kph(ar)),
    }


def _estimated(value: Markup | str, source: str) -> Markup:
    """A thermal figure, followed by "est" when it is our own estimate and not AUSRASP's."""
    if source == "ausrasp":
        return Markup(value)
    return Markup(value) + Markup('<small class="est"> est</small>')


def _label(verdict: str) -> str:
    return LABELS[verdict]


def _run_label(run_iso: str, zone: ZoneInfo) -> str:
    """The AUSRASP model start in the page's time zone, e.g. 'Fri 2 Oct 23:00 AEDT'."""
    run = datetime.fromisoformat(run_iso.replace("Z", "+00:00")).astimezone(zone)
    return run.strftime("%a %-d %b %H:%M %Z")


def _thermal_summary(fc: Forecast, zone: ZoneInfo) -> str:
    """One line for the page header saying where the thermal figures come from: AUSRASP and the
    run(s) it came from, and the days that use the page's own estimate instead."""
    runs = sorted({b.thermal_run for b in fc.blocks if b.thermal_source == "ausrasp"})
    if not runs:
        return "Thermals: estimate from the global model."
    labels = ", ".join(_run_label(r, zone) for r in runs)
    text = f"Thermals: AUSRASP, run{'s' if len(runs) > 1 else ''} {labels}"
    days = []
    for b in fc.blocks:
        if b.thermal_source != "ausrasp":
            day = datetime.fromisoformat(b.start).astimezone(zone).strftime("%a")
            if day not in days:
                days.append(day)
    if days:
        text += f"; estimate from the global model for {', '.join(days)}"
    return text + "."


def build_context(fc: Forecast, site: Site, rules: Rules) -> dict:
    zone = ZoneInfo(site.timezone)
    ausrasp_runs = sorted({b.thermal_run for b in fc.blocks if b.thermal_source == "ausrasp"})
    days: dict[str, dict] = {}
    for b in fc.blocks:
        start = datetime.fromisoformat(b.start).astimezone(zone)
        key = start.date().isoformat()
        day = days.setdefault(
            key,
            {
                "label": start.strftime("%A %d %B"),
                "short_day": start.strftime("%a"),
                "short_date": start.strftime("%-d %b"),
                "blocks": [],
            },
        )
        sun_icon, sun_words = sun_indicator(b.sun_pct, rules)
        day["blocks"].append(
            {
                "time": start.strftime("%H:%M"),  # 24-hour key for the slot lookup
                "clock": clock12(start.hour, start.minute),
                "gl": [
                    {
                        "id": gid,
                        "name": gname,
                        "abbr": gabbr,
                        "verdict": v,
                        "label": _label(v),
                        "icon": ICONS[v],
                        "reasons": [
                            unitise(r)
                            for r in (b.reasons if gid == "pg" else (b.reasons_hg or b.reasons))
                        ],
                    }
                    for (gid, gname, gabbr), v in zip(
                        GLIDERS, (b.verdict_pg, b.verdict_hg), strict=True
                    )
                ],
                "verdict_pg": b.verdict_pg,
                "verdict_hg": b.verdict_hg,
                "verdict_pg_label": _label(b.verdict_pg),
                "verdict_hg_label": _label(b.verdict_hg),
                "pg_icon": ICONS[b.verdict_pg],
                "hg_icon": ICONS[b.verdict_hg],
                "launch": _wind(b.wind_launch) if b.wind_launch else None,
                "launch_rot": round(b.wind_launch.dir_deg) if b.wind_launch else 0,
                "launch_dir": direction_class(b.wind_launch.dir_deg, rules)
                if b.wind_launch
                else "",
                "ground": _wind_num(b.wind_ground),
                "aloft": _wind_num(b.wind_aloft),
                "shear": b.shear,
                "hour": clock12(start.hour),
                "est": b.thermal_source != "ausrasp",  # the thermal figures are our estimate
                "thermal_height": _estimated(_height_num(b.thermal_height_m), b.thermal_source),
                "thermal_height_short": height_down(b.thermal_height_m, short=True),
                "launch_short": _wind_short(b.wind_launch) if b.wind_launch else None,
                "quality": _estimated(f"{b.thermal_quality_pct}%", b.thermal_source),
                "thermal_quality_pct": b.thermal_quality_pct,
                "updraft": _estimated(
                    _rate_num(b.updraft_ms, whole=b.thermal_source == "ausrasp"), b.thermal_source
                ),
                "thermal_ausrasp": b.thermal_source == "ausrasp",
                "temp_ground": _temp_num(b.temp_ground_c),
                "temp_air": _temp_num(b.temp_air_c, 1),
                "rain": _rain_num(b.rain_mm_h) if b.rain_mm_h >= 0.05 else Markup("none"),
                "gusts": spd_short(b.gust_kph) if b.gust_kph > 0 else Markup("not available"),
                "gusts_launch": _est(b.gust_launch_kph),
                "gusts_aloft": _est(b.gust_aloft_kph),
                "sun": f"{sun_icon} {b.sun_pct}%"
                if b.sun_pct is not None
                else Markup("not available"),
                "sun_icon": sun_icon,
                "sun_title": sun_words,
                "storm": b.cape_j_kg >= rules.cape_overdevelop_j_kg,
                "reasons": [unitise(r) for r in b.reasons],
            }
        )
    # One column per block hour so every day lines up, even when a block is missing.
    for day in days.values():
        by_time = {b["time"]: b for b in day["blocks"]}
        day["slots"] = [by_time.get(f"{h:02d}:00") for h in BLOCK_HOURS]
        day["has_launch"] = any(b.get("launch") for b in day["blocks"])
    outlook = []
    for o in fc.outlook:
        d = datetime.fromisoformat(o.date)
        outlook.append(
            {
                "label": d.strftime("%a %d %b"),
                "gl": [
                    {
                        "id": gid,
                        "name": gname,
                        "abbr": gabbr,
                        "verdict": v,
                        "label": _label(v),
                        "icon": ICONS[v],
                    }
                    for (gid, gname, gabbr), v in zip(
                        GLIDERS, (o.verdict, o.verdict_hg or o.verdict), strict=True
                    )
                ],
                "verdict_pg": o.verdict,
                "verdict_hg": o.verdict_hg or o.verdict,
                "verdict": o.verdict,
                "verdict_label": _label(o.verdict),
                "icon": ICONS[o.verdict],
                "wind": _wind(o.wind),
                "wind_rot": round(o.wind.dir_deg),
                "wind_dir": direction_class(o.wind.dir_deg, rules),
                "wet": o.rain_mm_h >= rules.rain_light_mm_h
                or o.cape_j_kg >= rules.cape_overdevelop_j_kg,
            }
        )
    wet_days = sorted(
        {
            datetime.fromisoformat(b.start).astimezone(zone).strftime("%A")
            for b in fc.blocks
            if b.rain_mm_h >= rules.rain_light_mm_h or b.cape_j_kg >= rules.cape_overdevelop_j_kg
        }
    )
    gen = datetime.fromisoformat(fc.generated_at)
    lo = (rules.sector_center_deg - rules.sector_half_width_deg) % 360
    hi = (rules.sector_center_deg + rules.sector_half_width_deg) % 360
    return {
        "site": site,
        "links": {**BOM_LINKS, **site.links},
        "days": list(days.values()),
        "outlook": outlook,
        "launch_alt": alt(site.elevation_m),
        "weather_tabs": list(site.weather_tabs),
        # only what the script needs to ask for each place's weather
        "tabs_js": [
            {k: t[k] for k in ("id", "label", "lat", "lon", "elevation_m")}
            for t in site.weather_tabs
        ],
        "launch_unit": Markup(_U_SPD),
        "detailed_days": DETAILED_DAYS,
        "slot_count": len(BLOCK_HOURS),
        "slot_labels": [
            clock12(h) for h in BLOCK_HOURS
        ],  # hour label of each column, for blank tiles
        "first_hour": clock12(BLOCK_HOURS[0]),
        "last_hour": clock12(BLOCK_HOURS[-1]),
        "outlook_range": f"{DETAILED_DAYS + 1} to {DETAILED_DAYS + OUTLOOK_DAYS}",
        "outlook_cols": OUTLOOK_DAYS,
        "gliders": [{"id": i, "name": n, "abbr": a} for i, n, a in GLIDERS],
        "icons": ICONS,
        "limits": {
            "pg": {
                "orange": spd(mph_to_kph(rules.speed_orange_from_mph)),
                "red": spd(mph_to_kph(rules.speed_red_from_mph)),
                **_gust_limits(rules, "pg"),
            },
            "hg": {
                "orange": spd(mph_to_kph(rules.hg_speed_orange_from_mph)),
                "red": spd(mph_to_kph(rules.hg_speed_red_from_mph)),
                **_gust_limits(rules, "hg"),
            },
        },
        "station_charts": site.station_charts,
        "station_default": site.station_default,
        "detail_rows": [
            (_row_label("Ground wind", _U_SPD), "ground"),
            (_row_label("Gusts at 10 m (model)", _U_SPD), "gusts"),
            (_row_label("Gusts at launch (est.)", _U_SPD), "gusts_launch"),
            (_row_label("Wind aloft", _U_SPD), "aloft"),
            (_row_label("Gusts at thermal height (est.)", _U_SPD), "gusts_aloft"),
            (_row_label("Wind shear"), "shear"),
            (_row_label("Thermal height", _U_ALT), "thermal_height"),
            (_row_label("Thermal quality"), "quality"),  # a percentage: no unit label
            (_row_label("Updraft", _U_RATE), "updraft"),
            (_row_label("Sun reaching the ground"), "sun"),  # a percentage: no unit label
            (_row_label("Temperature, ground", _U_TEMP), "temp_ground"),
            (_row_label("Temperature, at thermal height", _U_TEMP), "temp_air"),
            (_row_label("Rain", _U_RAIN), "rain"),
        ],
        "wet_days": wet_days,
        "lat": site.lat,
        "lon": site.lon,
        "speed_units": SPEED_UNITS,
        "alt_units": ALT_UNITS,
        "temp_units": TEMP_UNITS,
        "thermal_summary": _thermal_summary(fc, zone),
        "uses_ausrasp": bool(ausrasp_runs),
        "ausrasp_max_age_h": f"{site.ausrasp.max_age_h:g}",
        "cell_radius": site.ausrasp.cell_radius,
        "ausrasp_area": (
            f"the highest value in the block of {2 * site.ausrasp.cell_radius + 1} by "
            f"{2 * site.ausrasp.cell_radius + 1} grid cells (4 km each) around the launch"
            if site.ausrasp.cell_radius
            else "the grid cell nearest the launch"
        ),
        "ausrasp_runs": [_run_label(r, zone) for r in ausrasp_runs],
        "some_estimate": any(b.thermal_source != "ausrasp" for b in fc.blocks),
        "model": fc.model,
        "cycle_label": fc.cycle,
        "generated_local": gen.astimezone(zone).strftime("%a %d %b %Y %H:%M %Z"),
        "generated_iso": gen.isoformat(),
        "rules_version": fc.rules_version,
        "rules_source": rules.source,
        "legend": {
            "critical": rate(rules.critical_updraft_ms),
            "good_quality": f"{rules.thermal_good_quality_pct:.0f}",
            "good_updraft": rate(rules.thermal_good_updraft_ms),
            "strong_updraft": rate(rules.thermal_strong_updraft_ms),
            "a_good_updraft": rate_whole(rules.ausrasp_good_updraft_ms),
            "a_strong_updraft": rate_whole(rules.ausrasp_strong_updraft_ms),
            "depth_pct": f"{rules.usable_depth_fraction * 100:.0f}",
            "quality_full": rate(rules.quality_full_updraft_ms),
            "wind_threshold": spd(rules.quality_wind_threshold_kph),
            "penalty": Markup(
                _u("s-kts", f"{rules.quality_wind_penalty_per_kph * 1.852:.1f} points per knot")
                + _u("s-kph", f"{rules.quality_wind_penalty_per_kph:.1f} points per km/h")
            ),
            "green_from": spd(mph_to_kph(rules.speed_green_from_mph)),
            "gust_orange": spd(mph_to_kph(rules.gust_orange_from_mph)),
            "gust_red": spd(mph_to_kph(rules.gust_red_from_mph)),
            "gust_aloft_orange": spd(mph_to_kph(rules.gust_aloft_orange_from_mph)),
            "gust_aloft_red": spd(mph_to_kph(rules.gust_aloft_red_from_mph)),
            "gust_mix": f"{rules.gust_mix_fraction * 100:.0f}",
            "gust_aloft_factor": f"{rules.gust_aloft_factor:g}",
            "sun_full": f"{rules.sun_full_pct:.0f}",
            "sun_shaded": f"{rules.sun_shaded_pct:.0f}",
            "rain_light": rain(rules.rain_light_mm_h),
            "rain_heavy": rain(rules.rain_heavy_mm_h),
            "cape_overdevelop": f"{rules.cape_overdevelop_j_kg:.0f}",
            "cape_storm": f"{rules.cape_storm_j_kg:.0f}",
            "margin": f"{rules.marginal_margin_deg:.0f}",
            "quality": f"{rules.thermal_ok_quality_pct:.0f}",
            "min_height": alt(rules.thermal_min_height_m),
            "orange": spd(mph_to_kph(rules.speed_orange_from_mph)),
            "red": spd(mph_to_kph(rules.speed_red_from_mph)),
            "hg_orange": spd(mph_to_kph(rules.hg_speed_orange_from_mph)),
            "hg_red": spd(mph_to_kph(rules.hg_speed_red_from_mph)),
            "sector_from": f"{deg_to_compass(lo)} ({lo:.0f} degrees)",
            "sector_to": f"{deg_to_compass(hi)} ({hi:.0f} degrees)",
        },
    }


def render_page(fc: Forecast, site: Site, rules: Rules) -> str:
    env = Environment(
        loader=FileSystemLoader(TEMPLATE_DIR), autoescape=select_autoescape(["html", "j2"])
    )
    return env.get_template("page.html.j2").render(**build_context(fc, site, rules))


def render_to_dir(fc: Forecast, site: Site, rules: Rules, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "index.html").write_text(render_page(fc, site, rules), encoding="utf-8")
    (out_dir / "forecast.json").write_text(json.dumps(fc.to_dict(), indent=2), encoding="utf-8")
    return out_dir / "index.html"
