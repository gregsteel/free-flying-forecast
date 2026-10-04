from datetime import UTC, datetime

import pytest

from ffforecast.diagnostics import build_block
from ffforecast.gfsmode import blocks_from_samples, outlook_after_blocks
from ffforecast.grading import grade_block
from ffforecast.models import Wind
from ffforecast.thermal import Thermal

RUN = "2026-10-02T12:00:00Z"
START = datetime(2026, 10, 4, 4, tzinfo=UTC)  # 15:00 AEDT


def block(rules, site, thermal, wind=8.0, **kw):
    return build_block(
        START.astimezone(),
        Wind(0, wind),
        Wind(0, wind),
        1500.0,
        250.0,
        16.0,
        site.elevation_m,
        rules,
        thermal=thermal,
        launch=Wind(0, wind),
        **kw,
    )


def test_ausrasp_height_and_updraft_replace_the_estimate(rules, site):
    b = block(rules, site, Thermal(1844.0, 2.0, RUN))
    assert (b.thermal_height_m, b.updraft_ms) == (1844, 2.0)
    assert b.thermal_source == "ausrasp" and b.thermal_run == RUN


def test_without_ausrasp_the_block_says_gfs(rules, site):
    b = block(rules, site, None)
    assert b.thermal_source == "gfs" and b.thermal_run == ""


def test_temperature_at_height_follows_the_ausrasp_height(rules, site):
    b = block(rules, site, Thermal(1800.0, 2.0, RUN))
    assert b.temp_air_c == pytest.approx(b.temp_ground_c - 9.8, abs=1.0)  # 1000 m above launch


def test_a_height_at_or_below_launch_is_launch_height(rules, site):
    b = block(rules, site, Thermal(300.0, 2.0, RUN))
    assert b.thermal_height_m == site.elevation_m and b.verdict_pg == "poor"  # below min height


@pytest.mark.parametrize(
    "updraft, grade",
    [(0, "poor"), (1, "ok"), (2, "ok"), (3, "good"), (4, "strong"), (5, "strong")],
)
def test_whole_number_updrafts_map_to_the_stated_grades(rules, site, updraft, grade):
    b = block(rules, site, Thermal(1900.0, float(updraft), RUN), wind=8.0)
    assert b.verdict_pg == grade, (updraft, b.reasons)


def test_ausrasp_good_needs_three_not_two_and_a_half(rules):
    assert (
        grade_block(0, 8, 8, 100, 1900, rules, updraft_ms=2.5)[0] == "good"
    )  # the estimate's limit
    verdict, _ = grade_block(
        0, 8, 8, 100, 1900, rules, updraft_ms=2.5,
        good_updraft_ms=rules.ausrasp_good_updraft_ms,
        strong_updraft_ms=rules.ausrasp_strong_updraft_ms,
    )  # fmt: skip
    assert verdict == "ok"


def test_wind_still_wins_over_ausrasp_thermals(rules, site):
    b = block(rules, site, Thermal(2200.0, 5.0, RUN), wind=40.0)
    assert b.verdict_pg in ("turbulent", "dangerous")
    r = block(rules, site, Thermal(2200.0, 5.0, RUN), rain_mm_h=2.0)
    assert r.verdict_pg == "dangerous"


def sample(day, hour_utc):
    return {
        "time": datetime(2026, 10, day, hour_utc, tzinfo=UTC),
        "u10": 0.0, "v10": -3.0, "u850": 0.0, "v850": -4.0,
        "hpbl_m": 1500.0, "shtfl_wm2": 250.0, "t2_c": 16.0,
    }  # fmt: skip


def test_blocks_use_the_ausrasp_hour_valid_at_their_start(rules, site):
    samples = [sample(4, h) for h in (0, 2, 4, 6)]
    lookup = {datetime(2026, 10, 4, 4, tzinfo=UTC): Thermal(1844.0, 3.0, RUN)}  # 15:00 only
    blocks = blocks_from_samples(samples, rules, site, "2026-10-04", thermal=lookup)
    assert [b.thermal_source for b in blocks] == ["gfs", "gfs", "ausrasp", "gfs"]
    assert blocks[2].thermal_height_m == 1844 and blocks[2].verdict_pg == "good"


def test_the_outlook_averages_ausrasp_hours_when_at_least_two_are_held(rules, site):
    samples = [sample(8, 2), sample(9, 2)]
    day8 = {  # local 11, 13, 15 on the 8th (UTC 00, 02, 04); the 17:00 hour is missing
        datetime(2026, 10, 8, h, tzinfo=UTC): Thermal(1900.0, u, RUN)
        for h, u in ((0, 3.0), (2, 4.0), (4, 5.0))
    }
    day9 = {datetime(2026, 10, 9, 0, tzinfo=UTC): Thermal(1900.0, 5.0, RUN)}  # only one hour
    out = outlook_after_blocks(samples, rules, site, "2026-10-04", thermal={**day8, **day9})
    assert [o.date for o in out] == ["2026-10-08", "2026-10-09"]
    assert [o.thermal_source for o in out] == ["ausrasp", "gfs"]
