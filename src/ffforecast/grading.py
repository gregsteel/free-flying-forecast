"""Rules engine: turn weather values into verdicts with plain-text reasons."""

from __future__ import annotations

from .config import Rules
from .units import angle_diff, deg_to_compass, kph_to_mph, mph_to_kph

# Worse problems have higher rank. "ok" means no problem was found; the thermals then decide
# between Ok, Good and Strong (or Poor).
_RANK = {"ok": 0, "poor": 1, "turbulent": 2, "dangerous": 3}


def _ms(v: float) -> str:
    """An updraft for a sentence: whole numbers (AUSRASP's) without a false decimal."""
    return f"{v:.0f}" if float(v).is_integer() else f"{v:.1f}"


def worst(a: str, b: str) -> str:
    return a if _RANK[a] >= _RANK[b] else b


def _bands(rules: Rules, glider: str) -> tuple[float, float, float]:
    if glider == "hg":
        return (
            rules.speed_green_from_mph,
            rules.hg_speed_orange_from_mph,
            rules.hg_speed_red_from_mph,
        )
    return (rules.speed_green_from_mph, rules.speed_orange_from_mph, rules.speed_red_from_mph)


def grade_speed(kph: float, rules: Rules, glider: str = "pg") -> tuple[str, str]:
    """Return (state, reason). State is 'ok', 'poor', 'turbulent' or 'dangerous'."""
    green, orange, red = _bands(rules, glider)
    mph = kph_to_mph(kph)
    if mph >= red:
        return (
            "dangerous",
            f"Wind {kph:.0f} kph is at or above {mph_to_kph(red):.0f} kph: likely unsuitable for flying.",
        )
    if mph >= orange:
        return (
            "turbulent",
            f"Wind {kph:.0f} kph is above {mph_to_kph(orange):.0f} kph: may not suit novice pilots.",
        )
    if mph < green:
        return "poor", f"Wind {kph:.0f} kph is too light for soaring."
    return "ok", f"Wind {kph:.0f} kph is in the green band."


def grade_direction(
    dir_deg: float, kph: float, rules: Rules, glider: str = "pg"
) -> tuple[str, str]:
    """Direction state: 'ok' inside the sector and when marginally outside it (a marginally crossed
    launch, which a pilot can still get off in, so it does not limit the grade: owner decision 2026-10-04),
    or 'poor'/'dangerous' further outside."""
    off = angle_diff(dir_deg, rules.sector_center_deg)
    name = deg_to_compass(dir_deg)
    if off <= rules.sector_half_width_deg:
        return "ok", f"Wind from the {name} is inside the green sector."
    if off <= rules.sector_half_width_deg + rules.marginal_margin_deg:
        return (
            "ok",
            f"Wind from the {name} is marginally crossed (just outside the green sector): "
            "noted, but it can still be flown.",
        )
    _, orange, _ = _bands(rules, glider)
    if kph_to_mph(kph) >= orange:
        return "dangerous", f"Strong wind from the {name} is well outside the green sector."
    return "poor", f"Wind from the {name} is outside the green sector."


def grade_weather(
    rain_mm_h: float,
    cape_j_kg: float,
    gust_kph: float,
    rules: Rules,
    gust_aloft_kph: float = 0.0,
) -> list[tuple[str, str]]:
    """Rain, storm and gust states as (state, reason) pairs; only problems are reported.
    States use the same vocabulary as the wind grades ('poor', 'turbulent', 'dangerous')."""
    out: list[tuple[str, str]] = []
    raining = rain_mm_h >= rules.rain_light_mm_h
    if rain_mm_h >= rules.rain_heavy_mm_h:
        out.append(("dangerous", f"Heavy rain expected ({rain_mm_h:.1f} mm/h)."))
    elif raining:
        out.append(("poor", f"Rain expected ({rain_mm_h:.1f} mm/h)."))
    if cape_j_kg >= rules.cape_storm_j_kg or (raining and cape_j_kg >= rules.cape_overdevelop_j_kg):
        out.append(("dangerous", f"Thunderstorm risk (storm energy {cape_j_kg:.0f} J/kg)."))
    elif cape_j_kg >= rules.cape_overdevelop_j_kg:
        out.append(("turbulent", f"Overdevelopment risk (storm energy {cape_j_kg:.0f} J/kg)."))
    gust_mph = kph_to_mph(gust_kph)
    if gust_mph >= rules.gust_red_from_mph:
        out.append(("dangerous", f"Gusts to {gust_kph:.0f} kph: likely unsuitable for flying."))
    elif gust_mph >= rules.gust_orange_from_mph:
        out.append(("turbulent", f"Gusts to {gust_kph:.0f} kph: rough air likely."))
    aloft_mph = kph_to_mph(gust_aloft_kph)
    if aloft_mph >= rules.gust_aloft_red_from_mph:
        out.append(
            (
                "dangerous",
                f"Gusts to {gust_aloft_kph:.0f} kph at thermal height: violent air aloft.",
            )
        )
    elif aloft_mph >= rules.gust_aloft_orange_from_mph:
        out.append(
            ("turbulent", f"Gusts to {gust_aloft_kph:.0f} kph at thermal height: rough air aloft.")
        )
    return out


def _to_verdict(state: str) -> str:
    return state


def strong_wind_mph(rules: Rules, glider: str) -> float:
    return rules.hg_strong_wind_from_mph if glider == "hg" else rules.strong_wind_from_mph


def grade_block(
    ground_dir: float,
    ground_kph: float,
    aloft_kph: float,
    thermal_quality_pct: float,
    thermal_height_m: float,
    rules: Rules,
    glider: str = "pg",
    rain_mm_h: float = 0.0,
    cape_j_kg: float = 0.0,
    gust_kph: float = 0.0,
    updraft_ms: float | None = None,
    good_updraft_ms: float | None = None,
    strong_updraft_ms: float | None = None,
    gust_aloft_kph: float = 0.0,
    sun_pct: float | None = None,
) -> tuple[str, list[str]]:
    """Verdict and reasons for one block. Direction is judged on the ground (launch) wind;
    speed is judged on the stronger of ground and aloft wind.

    The worst problem found (wind, direction, gusts, rain, storms) sets Poor, Turbulent or
    Dangerous. With no problem, the thermals decide: Poor if weak or low, otherwise Ok, Good or
    Strong. Without an updraft value only quality is used, so Strong cannot be reached. The
    updraft limits default to the rules' values; AUSRASP's whole-number updraft passes its own.
    `gust_kph` is the gust at launch and `gust_aloft_kph` the gust at the top of the thermals (both
    estimates; see diagnostics.estimate_gusts). `sun_pct` only adds a reason: the caller has already
    scaled the thermal quality by it."""
    good_u = rules.thermal_good_updraft_ms if good_updraft_ms is None else good_updraft_ms
    strong_u = rules.thermal_strong_updraft_ms if strong_updraft_ms is None else strong_updraft_ms
    reasons: list[str] = []
    verdict = "ok"

    s_ground, r_ground = grade_speed(ground_kph, rules, glider)
    s_aloft, r_aloft = grade_speed(aloft_kph, rules, glider)
    # Report the reason belonging to the worse speed state.
    speed_state, speed_reason = (
        (s_ground, r_ground)
        if _RANK[_to_verdict(s_ground)] >= _RANK[_to_verdict(s_aloft)]
        else (s_aloft, "Aloft: " + r_aloft)
    )
    d_state, d_reason = grade_direction(ground_dir, ground_kph, rules, glider)

    for state, reason in ((speed_state, speed_reason), (d_state, d_reason)):
        verdict = worst(verdict, _to_verdict(state))
        reasons.append(reason)

    for state, reason in grade_weather(rain_mm_h, cape_j_kg, gust_kph, rules, gust_aloft_kph):
        verdict = worst(verdict, _to_verdict(state))
        reasons.append(reason)

    # Shading is already in the thermal quality (scaled by the caller); say so when it is marked
    if sun_pct is not None and sun_pct < rules.sun_full_pct:
        reasons.append(
            f"Cloud shading: only {sun_pct:.0f}% of the possible sun reaches the ground, so thermals "
            "are weaker and less reliable."
            if sun_pct < rules.sun_shaded_pct
            else f"Some cloud shading ({sun_pct:.0f}% of the possible sun): thermals are a little weaker."
        )

    if verdict != "ok":
        return verdict, reasons

    if (
        thermal_quality_pct < rules.thermal_ok_quality_pct
        or thermal_height_m < rules.thermal_min_height_m
    ):
        reasons.append(
            f"Thermals are weak or low ({thermal_quality_pct:.0f}% quality, "
            f"{thermal_height_m:.0f} m)."
        )
        return "poor", reasons

    strong = updraft_ms is not None and updraft_ms >= good_u
    brisk = kph_to_mph(ground_kph) >= strong_wind_mph(rules, glider)
    if updraft_ms is not None and updraft_ms >= strong_u:
        reasons.append(
            f"Powerful thermals ({_ms(updraft_ms)} m/s): rewarding but demanding. "
            "Experienced pilots only."
        )
        return "strong", reasons
    if strong and brisk and thermal_quality_pct >= rules.thermal_good_quality_pct:
        reasons.append(
            f"Strong thermals ({_ms(updraft_ms or 0.0)} m/s) with a brisk wind of {ground_kph:.0f} kph: "
            "powerful and demanding. Experienced pilots only."
        )
        return "strong", reasons
    if thermal_quality_pct >= rules.thermal_good_quality_pct and (updraft_ms is None or strong):
        reasons.append("Strong, workable thermals and no problems: a time to go flying.")
        return "good", reasons
    reasons.append("Decent thermals and no problems.")
    return "ok", reasons
