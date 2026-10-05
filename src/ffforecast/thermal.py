"""The thermal figures a block can be given from outside the global model."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Thermal:
    """Thermal height (m above sea level) and updraft (m/s) with the run they came from."""

    height_m: float
    updraft_ms: float
    run: str  # model start time of the source run, ISO UTC
    # Also from AUSRASP when it was read for this hour (None otherwise)
    sfc_wind_ms: float | None = None  # wind 10 m above the ground, the strongest in the cell block
    top_wind_ms: float | None = None  # wind at the top of the thermals (the boundary layer)
    sun_pct: float | None = None  # share of possible sunshine reaching the ground, block average
    bl_cloud_pct: float | None = None  # cumulus cloud cover in the thermals, block average
