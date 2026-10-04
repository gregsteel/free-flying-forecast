"""Load and validate site and rules configuration (contracts/config-schema.md)."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class PollWindow:
    """Check the AUSRASP manifest every `every_min` minutes between two UTC clock times."""

    start_min: int  # minutes after 00:00 UTC
    end_min: int
    every_min: int


@dataclass(frozen=True)
class AusraspConfig:
    """Where thermal height and updraft come from (specs/003-ausrasp-thermal-source)."""

    enabled: bool = True
    base_url: str = "https://ausrasp.com/VIC/"
    contact: str = ""
    max_cell_km: float = 3.0
    # Cells around the nearest one that are also read: 1 means a block of 3 by 3, 0 the nearest cell
    # alone. The highest value in the block is used (the launch sits on a mountain).
    cell_radius: int = 1
    max_age_h: float = 36.0
    windows: tuple[PollWindow, ...] = ()
    default_every_min: int = 180


@dataclass(frozen=True)
class Site:
    id: str
    name: str
    lat: float
    lon: float
    elevation_m: float
    timezone: str
    links: dict[str, str]
    domain: dict[str, dict[str, float]]
    station_charts: tuple[dict[str, str], ...] = ()
    station_default: str = ""
    ausrasp: AusraspConfig = AusraspConfig(enabled=False)
    # The tabs of the "Today" weather panel. Each is {id, label, heading, lat, lon, elevation_m, note}.
    weather_tabs: tuple[dict[str, Any], ...] = ()


@dataclass(frozen=True)
class Rules:
    version: int
    source: str
    speed_green_from_mph: float
    speed_orange_from_mph: float
    speed_red_from_mph: float
    hg_speed_orange_from_mph: float
    hg_speed_red_from_mph: float
    sector_center_deg: float
    sector_half_width_deg: float
    marginal_margin_deg: float
    shear_moderate_from_kph: float
    shear_strong_from_kph: float
    thermal_ok_quality_pct: float
    thermal_min_height_m: float
    rain_light_mm_h: float = 0.1
    rain_heavy_mm_h: float = 1.0
    cape_overdevelop_j_kg: float = 400.0
    cape_storm_j_kg: float = 1000.0
    gust_orange_from_mph: float = 16.0
    gust_red_from_mph: float = 20.0
    critical_updraft_ms: float = 1.143
    usable_depth_fraction: float = 0.48
    quality_full_updraft_ms: float = 1.6
    quality_wind_threshold_kph: float = 12.0
    quality_wind_penalty_per_kph: float = 2.5
    thermal_good_quality_pct: float = 70.0
    thermal_good_updraft_ms: float = 2.5
    thermal_strong_updraft_ms: float = 3.5
    strong_wind_from_mph: float = 9.0
    hg_strong_wind_from_mph: float = 11.0
    # Good and Strong updraft limits when the updraft is AUSRASP's, which is published in whole m/s
    ausrasp_good_updraft_ms: float = 3.0
    ausrasp_strong_updraft_ms: float = 4.0


def _read(path: Path) -> dict[str, Any]:
    try:
        with path.open("rb") as f:
            return tomllib.load(f)
    except FileNotFoundError as e:
        raise ConfigError(f"config file not found: {path}") from e
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"{path}: invalid TOML: {e}") from e


def _need(d: dict[str, Any], key: str, where: str) -> Any:
    if key not in d:
        raise ConfigError(f"{where}: missing required key '{key}'")
    return d[key]


def _station(d: dict[str, Any], where: str) -> dict[str, Any]:
    """The weather-station chart periods (Current, 1 hour, ...), validated."""
    charts = []
    for i, c in enumerate(d.get("station_charts", [])):
        for key in ("id", "label", "heading", "link", "page", "chart"):
            if not str(c.get(key, "")).strip():
                raise ConfigError(f"{where}: station_charts[{i}] is missing '{key}'")
        if not str(c["page"]).startswith("https://") or not str(c["chart"]).startswith("https://"):
            raise ConfigError(f"{where}: station_charts[{i}] links must be https")
        charts.append({k: str(v) for k, v in c.items()})
    ids = [c["id"] for c in charts]
    if len(ids) != len(set(ids)):
        raise ConfigError(f"{where}: station_charts ids must be unique")
    default = str(d.get("station_default", ids[0] if ids else ""))
    if charts and default not in ids:
        raise ConfigError(f"{where}: station_default '{default}' is not one of {ids}")
    return {"station_charts": tuple(charts), "station_default": default}


def _weather_tabs(
    d: dict[str, Any], lat: float, lon: float, where: str
) -> tuple[dict[str, Any], ...]:
    """The "Today" panel's tabs from [[weather_tabs]]. With none configured there is one, for the
    site itself. A tab without lat/lon uses the site's; elevation_m (optional) is the height the
    forecast is adjusted to; note (optional) is shown under the panel; link_label and link_url
    (optional, https) add a link to a measured source, such as the Bureau of Meteorology."""
    tabs: list[dict[str, Any]] = []
    for i, t in enumerate(d.get("weather_tabs", [])):
        here = f"{where}: weather_tabs[{i}]"
        for key in ("id", "label", "heading"):
            if not str(t.get(key, "")).strip():
                raise ConfigError(f"{here} is missing '{key}'")
        tlat, tlon = float(t.get("lat", lat)), float(t.get("lon", lon))
        if not -90 <= tlat <= 90 or not -180 <= tlon <= 180:
            raise ConfigError(f"{here}: lat/lon out of range")
        tab: dict[str, Any] = {
            "id": str(t["id"]),
            "label": str(t["label"]),
            "heading": str(t["heading"]),
            "lat": tlat,
            "lon": tlon,
            "elevation_m": float(t["elevation_m"]) if "elevation_m" in t else None,
            "note": str(t.get("note", "")).strip(),
            "link_label": str(t.get("link_label", "")).strip(),
            "link_url": str(t.get("link_url", "")).strip(),
        }
        if bool(tab["link_label"]) != bool(tab["link_url"]):
            raise ConfigError(f"{here}: link_label and link_url go together")
        if tab["link_url"] and not tab["link_url"].startswith("https://"):
            raise ConfigError(f"{here}: link_url must be https")
        if not tab["id"].replace("-", "").replace("_", "").isalnum():
            raise ConfigError(f"{here}: id may only hold letters, digits, - and _")
        tabs.append(tab)
    ids = [t["id"] for t in tabs]
    if len(ids) != len(set(ids)):
        raise ConfigError(f"{where}: weather_tabs ids must be unique")
    if not tabs:
        tabs = [
            {"id": "site", "label": "Today", "heading": "Today", "lat": lat, "lon": lon,
             "elevation_m": None, "note": "", "link_label": "", "link_url": ""}
        ]  # fmt: skip
    return tuple(tabs)


def _clock_min(value: Any, where: str) -> int:
    try:
        hh, mm = str(value).split(":")
        minutes = int(hh) * 60 + int(mm)
    except ValueError as e:
        raise ConfigError(f"{where}: '{value}' is not a HH:MM time") from e
    if not 0 <= minutes <= 24 * 60:
        raise ConfigError(f"{where}: '{value}' is not a time of day")
    return minutes


def _ausrasp(d: dict[str, Any], where: str) -> AusraspConfig:
    """The optional [ausrasp] section. Absent means the source is off."""
    a = d.get("ausrasp")
    if a is None:
        return AusraspConfig(enabled=False)
    base = str(a.get("base_url", "https://ausrasp.com/VIC/"))
    if not base.startswith("https://"):
        raise ConfigError(f"{where}: ausrasp.base_url must be https")
    if not base.endswith("/"):
        base += "/"
    windows = []
    for i, w in enumerate(a.get("poll", [])):
        here = f"{where}: ausrasp.poll[{i}]"
        lo, hi = _clock_min(w.get("from"), here), _clock_min(w.get("to"), here)
        every = int(w.get("every_min", 0))
        if every < 5:
            raise ConfigError(f"{here}: every_min must be at least 5")
        if lo >= hi:
            raise ConfigError(f"{here}: 'from' must be before 'to'")
        windows.append(PollWindow(lo, hi, every))
    default_every = int(a.get("poll_default", {}).get("every_min", 180))
    if default_every < 5:
        raise ConfigError(f"{where}: ausrasp.poll_default.every_min must be at least 5")
    radius = int(a.get("cell_radius", 1))
    if not 0 <= radius <= 3:
        raise ConfigError(f"{where}: ausrasp.cell_radius must be from 0 to 3")
    max_cell = float(a.get("max_cell_km", 3.0))
    max_age = float(a.get("max_age_h", 36.0))
    if max_cell <= 0 or max_age <= 0:
        raise ConfigError(f"{where}: ausrasp.max_cell_km and max_age_h must be above 0")
    return AusraspConfig(
        enabled=bool(a.get("enabled", True)),
        base_url=base,
        contact=str(a.get("contact", "")).strip(),
        max_cell_km=max_cell,
        cell_radius=radius,
        max_age_h=max_age,
        windows=tuple(windows),
        default_every_min=default_every,
    )


def load_site(path: Path) -> Site:
    d = _read(path)
    w = str(path)
    lat = float(_need(d, "lat", w))
    lon = float(_need(d, "lon", w))
    if not -90 <= lat <= 90 or not -180 <= lon <= 180:
        raise ConfigError(f"{w}: lat/lon out of range")
    return Site(
        id=str(_need(d, "id", w)),
        name=str(_need(d, "name", w)),
        lat=lat,
        lon=lon,
        elevation_m=float(_need(d, "elevation_m", w)),
        timezone=str(_need(d, "timezone", w)),
        links={k: str(v) for k, v in d.get("links", {}).items()},
        domain={k: dict(v) for k, v in d.get("domain", {}).items()},
        ausrasp=_ausrasp(d, w),
        weather_tabs=_weather_tabs(d, lat, lon, w),
        **_station(d, w),
    )


def _weather(section: dict[str, Any], where: str) -> dict[str, float]:
    keys = (
        "rain_light_mm_h",
        "rain_heavy_mm_h",
        "cape_overdevelop_j_kg",
        "cape_storm_j_kg",
        "gust_orange_from_mph",
        "gust_red_from_mph",
    )
    out = {k: float(section[k]) for k in keys if k in section}
    if out.get("rain_light_mm_h", 0.1) > out.get("rain_heavy_mm_h", 1.0):
        raise ConfigError(f"{where}: rain_light_mm_h must not exceed rain_heavy_mm_h")
    if out.get("cape_overdevelop_j_kg", 400) > out.get("cape_storm_j_kg", 1000):
        raise ConfigError(f"{where}: cape_overdevelop_j_kg must not exceed cape_storm_j_kg")
    if out.get("gust_orange_from_mph", 16) > out.get("gust_red_from_mph", 20):
        raise ConfigError(f"{where}: gust orange must not exceed gust red")
    return out


def _thermal_calibration(section: dict[str, Any], where: str) -> dict[str, float]:
    """Optional thermal calibration values (see research.md section 21), validated."""
    keys = (
        "critical_updraft_ms",
        "usable_depth_fraction",
        "quality_full_updraft_ms",
        "quality_wind_threshold_kph",
        "quality_wind_penalty_per_kph",
    )
    out = {k: float(section[k]) for k in keys if k in section}
    if out.get("critical_updraft_ms", 1.0) <= 0:
        raise ConfigError(f"{where}: critical_updraft_ms must be above 0")
    if not 0 < out.get("usable_depth_fraction", 0.5) <= 1:
        raise ConfigError(f"{where}: usable_depth_fraction must be above 0 and at most 1")
    if out.get("quality_full_updraft_ms", 1.0) <= 0:
        raise ConfigError(f"{where}: quality_full_updraft_ms must be above 0")
    if (
        out.get("quality_wind_penalty_per_kph", 0.0) < 0
        or out.get("quality_wind_threshold_kph", 0.0) < 0
    ):
        raise ConfigError(f"{where}: the quality wind threshold and penalty must not be negative")
    return out


def _tiers(
    thermal: dict[str, Any], wind: dict[str, Any], ausrasp: dict[str, Any], where: str
) -> dict[str, float]:
    """The Ok / Good / Strong thresholds (all optional), checked to be in a sensible order."""
    keys = {
        "good_quality_pct": "thermal_good_quality_pct",
        "good_updraft_ms": "thermal_good_updraft_ms",
        "strong_updraft_ms": "thermal_strong_updraft_ms",
        "strong_wind_from_mph": "strong_wind_from_mph",
        "hg_strong_wind_from_mph": "hg_strong_wind_from_mph",
    }
    out = {field: float(thermal[key]) for key, field in keys.items() if key in thermal}
    ok = float(thermal.get("ok_quality_pct", 40))
    good_q = out.get("thermal_good_quality_pct", 70.0)
    if not ok <= good_q <= 100:
        raise ConfigError(f"{where}: good_quality_pct must be between ok_quality_pct and 100")
    good_u = out.get("thermal_good_updraft_ms", 2.5)
    pump_u = out.get("thermal_strong_updraft_ms", 3.5)
    if not 0 < good_u < pump_u:
        raise ConfigError(f"{where}: good_updraft_ms must be above 0 and below strong_updraft_ms")
    a_good = float(ausrasp.get("good_updraft_ms", 3.0))
    a_pump = float(ausrasp.get("strong_updraft_ms", 4.0))
    if not 0 < a_good < a_pump:
        raise ConfigError(
            f"{where}: [thermal_ausrasp] good_updraft_ms must be above 0 and below strong_updraft_ms"
        )
    out["ausrasp_good_updraft_ms"] = a_good
    out["ausrasp_strong_updraft_ms"] = a_pump
    orange = float(wind.get("speed_orange_from_mph", 12))
    hg_orange = float(wind.get("hg_speed_orange_from_mph", orange))
    pw = out.get("strong_wind_from_mph", 9.0)
    hpw = out.get("hg_strong_wind_from_mph", 11.0)
    if not 0 < pw < orange:
        raise ConfigError(
            f"{where}: strong_wind_from_mph must be above 0 and below the orange band"
        )
    if not 0 < hpw < hg_orange:
        raise ConfigError(
            f"{where}: hg_strong_wind_from_mph must be above 0 and below the hang glider orange band"
        )
    return out


def load_rules(path: Path) -> Rules:
    d = _read(path)
    w = str(path)
    version = _need(d, "version", w)
    if not isinstance(version, int) or version < 1:
        raise ConfigError(f"{w}: 'version' must be a positive integer")
    source = str(_need(d, "source", w)).strip()
    if not source:
        raise ConfigError(f"{w}: 'source' must be non-empty")
    wind = _need(d, "wind", w)
    direction = _need(d, "direction", w)
    shear = _need(d, "shear", w)
    thermal = _need(d, "thermal", w)
    for section_name, section in (("wind", wind), ("shear", shear)):
        for key in section:
            if not key.endswith(("_mph", "_kph")):
                raise ConfigError(f"{w}: [{section_name}] key '{key}' must end in _mph or _kph")
    g = float(_need(wind, "speed_green_from_mph", w))
    o = float(_need(wind, "speed_orange_from_mph", w))
    r = float(_need(wind, "speed_red_from_mph", w))
    if not g <= o <= r:
        raise ConfigError(f"{w}: wind bands must satisfy green <= orange <= red")
    hw = float(_need(direction, "sector_half_width_deg", w))
    if not 0 < hw <= 180:
        raise ConfigError(f"{w}: sector_half_width_deg must be in (0, 180]")
    return Rules(
        version=version,
        source=source,
        speed_green_from_mph=g,
        speed_orange_from_mph=o,
        speed_red_from_mph=r,
        hg_speed_orange_from_mph=float(wind.get("hg_speed_orange_from_mph", o)),
        hg_speed_red_from_mph=float(wind.get("hg_speed_red_from_mph", r)),
        sector_center_deg=float(_need(direction, "sector_center_deg", w)),
        sector_half_width_deg=hw,
        marginal_margin_deg=float(direction.get("marginal_margin_deg", 30)),
        shear_moderate_from_kph=float(_need(shear, "moderate_from_kph", w)),
        shear_strong_from_kph=float(_need(shear, "strong_from_kph", w)),
        thermal_ok_quality_pct=float(_need(thermal, "ok_quality_pct", w)),
        thermal_min_height_m=float(_need(thermal, "min_height_m", w)),
        **_weather(d.get("weather", {}), w),
        **_thermal_calibration(thermal, w),
        **_tiers(thermal, wind, d.get("thermal_ausrasp", {}), w),
    )
