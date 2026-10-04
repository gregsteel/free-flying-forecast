"""Recovering the true hourly surface heating from GFS's window averages."""

import random
from datetime import UTC, datetime, timedelta

import pytest

from ffforecast import gfs
from ffforecast.outlook import _window, deaccumulate_flux

# Real values read from the GFS cycle 2026-10-02T18Z at the Mystic grid point for 5 Oct 2026:
# valid hour (UTC) -> (window in forecast hours, average W/m2 over that window). GFS restarts the
# average every 6 hours, so 06Z averages 00Z to 06Z and 07Z starts again.
REAL = {
    1: ((54, 55), 308.283),
    2: ((54, 56), 332.503),
    3: ((54, 57), 308.926),
    4: ((54, 58), 313.777),
    5: ((54, 59), 298.072),
    6: ((54, 60), 266.954),
    7: ((60, 61), 1.585),
}
DAY = datetime(2026, 10, 5, tzinfo=UTC)


def t(h: int) -> datetime:
    return DAY + timedelta(hours=h)


def samples_for(hours):
    return [{"time": t(h), "shtfl_wm2": REAL[h][1], "shtfl_window": REAL[h][0]} for h in hours]


def previous_for(hours):
    return {t(h): (REAL[h][1], REAL[h][0]) for h in hours}


def test_window_parsing():
    assert _window("54-57") == (54, 57)
    assert _window("33") == (33, 33)


def test_recovers_each_hour_from_real_gfs_values():
    expected = {1: 308.283, 2: 356.723, 3: 261.772, 4: 328.330, 5: 235.252, 6: 111.364, 7: 1.585}
    for h, want in expected.items():
        s = samples_for([h])
        out = deaccumulate_flux(s, previous_for([h - 1]) if h - 1 in REAL else {})
        # hour 1 and 7 are 1-hour windows (nothing to do); the others need the hour before
        assert out[0]["shtfl_wm2"] == pytest.approx(want, abs=0.01), h


def test_the_late_afternoon_error_this_fixes():
    # 06Z is 17:00 AEDT. The average over 00Z-06Z is 267 W/m2; the heating at that hour is 111.
    s = deaccumulate_flux(samples_for([6]), previous_for([5]))[0]
    assert s["shtfl_avg_wm2"] == pytest.approx(266.954)
    assert s["shtfl_wm2"] < 0.5 * s["shtfl_avg_wm2"]
    # and 00Z-02Z: the morning average understated the heating the other way
    s2 = deaccumulate_flux(samples_for([2]), previous_for([1]))[0]
    assert s2["shtfl_wm2"] > s2["shtfl_avg_wm2"]


def test_one_hour_windows_are_left_alone():
    s = deaccumulate_flux(samples_for([1, 7]), {})
    assert [x["shtfl_wm2"] for x in s] == [308.283, 1.585]


def test_without_the_hour_before_the_average_is_kept():
    s = deaccumulate_flux(samples_for([5]), {})[0]
    assert s["shtfl_wm2"] == pytest.approx(298.072)


def test_a_previous_hour_from_a_different_window_is_ignored():
    wrong = {t(4): (313.777, (48, 52))}  # not the same window: must not be used
    s = deaccumulate_flux(samples_for([5]), wrong)[0]
    assert s["shtfl_wm2"] == pytest.approx(298.072)


def test_exact_recovery_for_any_hourly_series():
    rng = random.Random(7)
    hourly = {h: rng.uniform(-30, 450) for h in range(0, 24)}  # true heating each hour

    # GFS reports, at each hour, the mean of the hours since the last multiple of 6
    def avg_at(h):
        start = h - ((h - 1) % 6)
        vals = [hourly[x] for x in range(start, h + 1)]
        return sum(vals) / len(vals), (start - 1, h)

    for h in range(1, 24):
        value, window = avg_at(h)
        s = [{"time": t(h), "shtfl_wm2": value, "shtfl_window": window}]
        prev = {}
        if h > 1:
            pv, pw = avg_at(h - 1)
            prev = {t(h - 1): (pv, pw)}
        out = deaccumulate_flux(s, prev)[0]["shtfl_wm2"]
        n = window[1] - window[0]
        if n > 1:
            assert out == pytest.approx(hourly[h], abs=1e-6), h


def test_hours_to_fetch_before_the_blocks():
    # forecast hours 1, 7, 13... already hold a single hour: nothing to fetch for them
    assert gfs.flux_prev_hours([1, 7, 13]) == []
    # the others need the hour before: 03Z needs 02Z and 05Z needs 04Z
    assert gfs.flux_prev_hours([1, 3, 5, 7]) == [2, 4]
    # blocks at 00Z, 02Z, 04Z and 06Z (the 11:00 to 17:00 AEDT blocks) need 23Z, 01Z, 03Z, 05Z
    assert gfs.flux_prev_hours([24, 26, 28, 30]) == [23, 25, 27, 29]
    # a block hour that is already a neighbour is not fetched twice
    assert gfs.flux_prev_hours([2, 3, 5]) == [1, 4]
    assert gfs.flux_prev_hours([1, 2, 3]) == []
    # forecast hour 0 has no heating field at all and is never asked for
    assert 0 not in gfs.flux_prev_hours([1, 2, 3])
    assert gfs.flux_prev_hours([]) == []


def test_the_extra_download_is_one_small_field():
    assert gfs.FLUX_FIELDS == (("SHTFL", "surface"),)
    assert gfs.fields_key(gfs.FLUX_FIELDS) != gfs.fields_key(gfs.BLOCK_FIELDS)  # cached separately
