"""Interpolate wind to a given height above sea level from a vertical profile."""

from __future__ import annotations

from .units import wind_from_uv

LEVELS_HPA = (950, 925, 900, 850)


def usable_profile(
    surface_height_m: float,
    surface_pressure_pa: float,
    u10: float,
    v10: float,
    levels: dict[int, tuple[float, float, float]],
) -> list[tuple[float, float, float]]:
    """Build (height_m, u, v) points, lowest first.

    `levels` maps a pressure in hPa to (height_m, u, v). Levels at or below the model surface
    (pressure at least the surface pressure) hold extrapolated values and are dropped. The 10 m
    wind sits 10 m above the model surface.
    """
    pts = [(surface_height_m + 10.0, u10, v10)]
    for hpa, (z, u, v) in sorted(levels.items(), reverse=True):
        if hpa * 100.0 < surface_pressure_pa - 500.0 and z > pts[-1][0]:
            pts.append((z, u, v))
    return pts


def wind_at(height_m: float, points: list[tuple[float, float, float]]) -> tuple[float, float]:
    """(direction the wind blows FROM in degrees, speed in m/s) at `height_m`.

    u and v are interpolated linearly in height. Outside the profile the nearest end is used.
    """
    if not points:
        raise ValueError("empty profile")
    pts = sorted(points)
    if height_m <= pts[0][0]:
        return wind_from_uv(pts[0][1], pts[0][2])
    if height_m >= pts[-1][0]:
        return wind_from_uv(pts[-1][1], pts[-1][2])
    for (z0, u0, v0), (z1, u1, v1) in zip(pts, pts[1:], strict=False):
        if z0 <= height_m <= z1:
            f = (height_m - z0) / (z1 - z0)
            return wind_from_uv(u0 + f * (u1 - u0), v0 + f * (v1 - v0))
    raise AssertionError("unreachable")
