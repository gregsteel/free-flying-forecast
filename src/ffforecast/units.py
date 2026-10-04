"""Unit conversions and compass helpers."""

MPH_PER_KPH = 0.621371
KPH_PER_MPH = 1.609344
FT_PER_M = 3.28084

_COMPASS = [
    "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
    "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW",
]  # fmt: skip


def mph_to_kph(mph: float) -> float:
    return mph * KPH_PER_MPH


def kph_to_mph(kph: float) -> float:
    return kph / KPH_PER_MPH


def ms_to_kph(ms: float) -> float:
    return ms * 3.6


def ms_to_ftmin(ms: float) -> float:
    return ms * FT_PER_M * 60


def m_to_ft(m: float) -> float:
    return m * FT_PER_M


def deg_to_compass(deg: float) -> str:
    """16-point compass name for a bearing in degrees."""
    return _COMPASS[int((deg % 360) / 22.5 + 0.5) % 16]


def angle_diff(a: float, b: float) -> float:
    """Smallest absolute difference between two bearings, in 0..180 degrees."""
    d = abs(a - b) % 360
    return 360 - d if d > 180 else d


def wind_from_uv(u: float, v: float) -> tuple[float, float]:
    """Return (direction the wind blows FROM in degrees, speed) from u/v components."""
    import math

    speed = math.hypot(u, v)
    direction = (math.degrees(math.atan2(-u, -v)) + 360) % 360
    return direction, speed


KPH_PER_KT = 1.852


def kph_to_kts(kph: float) -> float:
    return kph / KPH_PER_KT


def kph_to_ms(kph: float) -> float:
    return kph / 3.6


def c_to_f(c: float) -> float:
    return c * 9 / 5 + 32
