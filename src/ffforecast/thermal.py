"""The thermal figures a block can be given from outside the global model."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Thermal:
    """Thermal height (m above sea level) and updraft (m/s) with the run they came from."""

    height_m: float
    updraft_ms: float
    run: str  # model start time of the source run, ISO UTC
