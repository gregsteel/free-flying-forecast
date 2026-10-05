"""Thermal and wind diagnostics derived from model output (replaces RASP's NCL scripts)."""

from __future__ import annotations

import math
from datetime import datetime
from pathlib import Path

import numpy as np

from .config import Rules
from .grading import grade_block
from .models import ForecastBlock, Wind
from .thermal import Thermal
from .units import wind_from_uv

G = 9.80665
CP = 1004.0
RHO = 1.1  # near-surface air density at Alpine altitudes, kg/m3
DRY_LAPSE_C_PER_M = 0.0098


def wstar(hfx_wm2: float, zi_m: float, theta_k: float, rho: float = RHO) -> float:
    """Deardorff convective velocity scale in m/s. Zero when there is no upward heat flux."""
    if hfx_wm2 <= 0 or zi_m <= 0:
        return 0.0
    buoyancy = (G / theta_k) * (hfx_wm2 / (rho * CP)) * zi_m
    return buoyancy ** (1 / 3)


def thermal_height_asl(pblh_agl_m: float, terrain_m: float) -> float:
    return terrain_m + pblh_agl_m


def usable_thermal_height_asl(
    pblh_agl_m: float, updraft_ms: float, launch_m: float, rules: Rules
) -> float:
    """Height (m above sea level) that usable thermals reach.

    This is not the top of the boundary layer: RASP's "height of critical updraft strength" is
    where the thermal updraft falls below a critical value, which is lower. Observed against the
    AUSRASP-based figures it is about half the boundary layer depth above the ground, and the ground
    itself when the updraft never reaches the critical value (no usable thermals)."""
    if updraft_ms < rules.critical_updraft_ms or pblh_agl_m <= 0:
        return launch_m
    return launch_m + rules.usable_depth_fraction * pblh_agl_m


def thermal_quality_pct(
    updraft_ms: float,
    wind_kph: float,
    full_updraft_ms: float = 1.6,
    wind_threshold_kph: float = 12.0,
    penalty_per_kph: float = 2.5,
) -> int:
    """Percent quality: updraft strength scaled so `full_updraft_ms` is 100%, reduced by wind
    above a threshold that breaks thermals up. Rounded to the nearest 10 like the forecast this
    replaces. Defaults are the values calibrated against AUSRASP forecast figures."""
    base = min(updraft_ms / full_updraft_ms, 1.0) * 100
    penalty = max(0.0, wind_kph - wind_threshold_kph) * penalty_per_kph
    return int(round(max(0.0, base - penalty) / 10) * 10)


def estimate_gusts(
    gust10_kph: float, launch_kph: float, top_kph: float, rules: Rules
) -> tuple[float, float]:
    """(gust at launch, gust at the top of the thermals) in kph, both estimates.

    The global model gives a gust only 10 m above the ground. At launch the gusts are at least that,
    and thermals mix some of the faster air from the top of the boundary layer down: so the launch
    gust is the launch wind plus a fraction of the difference, and never less than a fixed multiple of
    the launch wind (daytime gusts run well above the average). At the top of the thermals the gust
    is the mean wind there times a gust factor. These are rules of thumb, not model output."""
    mix = max(top_kph - launch_kph, 0.0) * rules.gust_mix_fraction
    floor = launch_kph * rules.gust_factor_floor
    return max(gust10_kph, launch_kph + mix, floor), top_kph * rules.gust_aloft_factor


def sun_from_cloud(low: float, mid: float, high: float, rules: Rules) -> float:
    """Percent of possible sunshine reaching the ground from GFS cloud cover (each 0 to 100 %),
    treating the layers as stopping a fixed share of the sun where they are overcast."""
    return 100.0 * (
        (1 - rules.cloud_low_blocks * low / 100)
        * (1 - rules.cloud_mid_blocks * mid / 100)
        * (1 - rules.cloud_high_blocks * high / 100)
    )


def shear_class(ground: Wind, aloft: Wind, rules: Rules) -> str:
    gu = -ground.kph * math.sin(math.radians(ground.dir_deg))
    gv = -ground.kph * math.cos(math.radians(ground.dir_deg))
    au = -aloft.kph * math.sin(math.radians(aloft.dir_deg))
    av = -aloft.kph * math.cos(math.radians(aloft.dir_deg))
    diff = math.hypot(au - gu, av - gv)
    if diff >= rules.shear_strong_from_kph:
        return "strong"
    if diff >= rules.shear_moderate_from_kph:
        return "moderate"
    return "light"


def build_block(
    start: datetime,
    ground: Wind,
    aloft: Wind,
    pblh_agl_m: float,
    hfx_wm2: float,
    t2_c: float,
    terrain_m: float,
    rules: Rules,
    rain_mm_h: float = 0.0,
    cape_j_kg: float = 0.0,
    gust_kph: float = 0.0,
    launch: Wind | None = None,
    thermal: Thermal | None = None,
    sun_pct_gfs: float | None = None,
) -> ForecastBlock:
    """One graded block. With `thermal` (AUSRASP's height and updraft) those replace the figures
    estimated from the global model's boundary layer and heating; wind, rain, gusts and storms
    always come from the arguments."""
    theta = t2_c + 273.15
    if thermal is not None:
        up = thermal.updraft_ms
        height = max(thermal.height_m, terrain_m)  # at or below launch: no usable thermals
        limits = {
            "good_updraft_ms": rules.ausrasp_good_updraft_ms,
            "strong_updraft_ms": rules.ausrasp_strong_updraft_ms,
        }
    else:
        up = wstar(hfx_wm2, pblh_agl_m, theta)
        height = usable_thermal_height_asl(pblh_agl_m, up, terrain_m, rules)
        limits = {}
    rasp_ground = thermal.sfc_wind_ms * 3.6 if thermal and thermal.sfc_wind_ms is not None else None
    rasp_top = thermal.top_wind_ms * 3.6 if thermal and thermal.top_wind_ms is not None else None
    if thermal is not None and thermal.sun_pct is not None:
        # AUSRASP's sunshine leaves out the cumulus it forecasts in the thermals: take that shade off
        cover = (thermal.bl_cloud_pct or 0.0) / 100
        sun, sun_source = thermal.sun_pct * (1 - rules.cumulus_shade * cover), "ausrasp"
    elif sun_pct_gfs is not None:
        sun, sun_source = sun_pct_gfs, "gfs"
    else:
        sun, sun_source = None, ""
    quality = thermal_quality_pct(
        up,
        max(ground.kph, aloft.kph),
        rules.quality_full_updraft_ms,
        rules.quality_wind_threshold_kph,
        rules.quality_wind_penalty_per_kph,
    )
    if sun is not None and sun < rules.sun_full_pct:  # cloud shading weakens the thermals
        quality = int(round(quality * sun / rules.sun_full_pct / 10) * 10)
    # The verdict is judged on the wind at launch altitude when we have it (it is what a pilot
    # meets at take-off); otherwise on the 10 m wind. The stronger of the lower winds counts for
    # speed, so a windier surface or 850 hPa flow still shows. AUSRASP's regional 10 m wind joins
    # them when it is stronger (it resolves the ridge the global model smooths away).
    judged = launch or ground
    extra_reasons: list[str] = []
    if rules.ausrasp_wind_counts and rasp_ground is not None and rasp_ground > judged.kph:
        extra_reasons.append(
            f"AUSRASP's regional model has a stronger wind here ({rasp_ground:.0f} kph at 10 m); "
            "graded on that."
        )
        judged = Wind(judged.dir_deg, rasp_ground)
    speed_aloft = max(aloft.kph, ground.kph, judged.kph)
    # the wind at the top of the thermals: AUSRASP's, or the 850 hPa wind (about 1,500 m) without it
    top_kph = rasp_top if rasp_top is not None else aloft.kph
    gust_launch, gust_aloft = estimate_gusts(gust_kph, judged.kph, top_kph, rules)
    verdict_pg, reasons = grade_block(
        judged.dir_deg, judged.kph, speed_aloft, quality, height, rules, "pg",
        rain_mm_h, cape_j_kg, gust_launch, up, **limits,
        gust_aloft_kph=gust_aloft, sun_pct=sun,
    )  # fmt: skip
    verdict_hg, reasons_hg = grade_block(
        judged.dir_deg, judged.kph, speed_aloft, quality, height, rules, "hg",
        rain_mm_h, cape_j_kg, gust_launch, up, **limits,
        gust_aloft_kph=gust_aloft, sun_pct=sun,
    )  # fmt: skip
    reasons = [*extra_reasons, *reasons]
    reasons_hg = [*extra_reasons, *reasons_hg]
    return ForecastBlock(
        start=start.isoformat(),
        wind_ground=Wind(round(ground.dir_deg), round(ground.kph)),
        wind_aloft=Wind(round(aloft.dir_deg), round(aloft.kph)),
        shear=shear_class(ground, aloft, rules),
        thermal_height_m=round(height),
        thermal_quality_pct=quality,
        updraft_ms=round(up, 2),
        temp_ground_c=round(t2_c),
        temp_air_c=round(
            t2_c - DRY_LAPSE_C_PER_M * max(height - terrain_m, 0.0), 1
        ),  # at the height shown
        verdict_pg=verdict_pg,
        verdict_hg=verdict_hg,
        reasons=reasons,
        reasons_hg=reasons_hg,
        rain_mm_h=round(rain_mm_h, 2),
        cape_j_kg=round(cape_j_kg),
        gust_kph=round(gust_kph),
        wind_launch=Wind(round(launch.dir_deg), round(launch.kph)) if launch else None,
        thermal_source="ausrasp" if thermal else "gfs",
        thermal_run=thermal.run if thermal else "",
        gust_launch_kph=round(gust_launch),
        gust_aloft_kph=round(gust_aloft),
        wind_ausrasp_kph=round(rasp_ground) if rasp_ground is not None else None,
        wind_top_kph=round(rasp_top) if rasp_top is not None else None,
        sun_pct=round(sun) if sun is not None else None,
        sun_source=sun_source,
    )


def read_wrf_point(path: Path, lat: float, lon: float, aloft_agl_m: float = 500.0):
    """Read one wrfout file at the grid cell nearest (lat, lon).

    Returns a list of dicts, one per time step, with keys: time (naive UTC datetime),
    pblh_m, hfx_wm2, t2_c, terrain_m, ground (dir, kph), aloft (dir, kph).
    """
    import xarray as xr

    ds = xr.open_dataset(path, decode_times=False)
    try:
        xlat = ds["XLAT"].isel(Time=0).values
        xlong = ds["XLONG"].isel(Time=0).values
        j, i = np.unravel_index(np.argmin((xlat - lat) ** 2 + (xlong - lon) ** 2), xlat.shape)
        terrain = float(ds["HGT"].isel(Time=0, south_north=j, west_east=i))
        times = [
            datetime.strptime(b"".join(t).decode(), "%Y-%m-%d_%H:%M:%S") for t in ds["Times"].values
        ]
        out = []
        for n, t in enumerate(times):
            sel = {"Time": n, "south_north": j, "west_east": i}
            u10 = float(ds["U10"].isel(**sel))
            v10 = float(ds["V10"].isel(**sel))
            # Mass-level heights above ground from geopotential on staggered levels.
            ph = (
                ds["PH"].isel(Time=n, south_north=j, west_east=i)
                + ds["PHB"].isel(Time=n, south_north=j, west_east=i)
            ).values / G
            z_mass = (ph[:-1] + ph[1:]) / 2 - terrain
            k = int(np.argmin(np.abs(z_mass - aloft_agl_m)))
            u_st = ds["U"].isel(Time=n, bottom_top=k, south_north=j)
            v_st = ds["V"].isel(Time=n, bottom_top=k, west_east=i)
            ua = float((u_st.isel(west_east_stag=i) + u_st.isel(west_east_stag=i + 1)) / 2)
            va = float((v_st.isel(south_north_stag=j) + v_st.isel(south_north_stag=j + 1)) / 2)
            gd, gs = wind_from_uv(u10, v10)
            ad, as_ = wind_from_uv(ua, va)
            out.append(
                {
                    "time": t,
                    "pblh_m": float(ds["PBLH"].isel(**sel)),
                    "hfx_wm2": float(ds["HFX"].isel(**sel)),
                    "t2_c": float(ds["T2"].isel(**sel)) - 273.15,
                    "terrain_m": terrain,
                    "ground": (gd, gs * 3.6),
                    "aloft": (ad, as_ * 3.6),
                }
            )
        return out
    finally:
        ds.close()
