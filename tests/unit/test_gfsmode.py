from datetime import UTC, datetime

from ffforecast import gfs
from ffforecast.gfsmode import blocks_from_samples, outlook_after_blocks

TZ = "Australia/Melbourne"
CYCLE = gfs.Cycle("20261003", 0)


def test_plan_hours_blocks_and_outlook_across_dst_start():
    now = datetime(2026, 10, 3, 1, 0, tzinfo=UTC)  # 11:00 AEST on 3 Oct
    blocks, outlook, first = gfs.plan_hours(CYCLE, now, TZ)
    assert first == "2026-10-03"
    # 3 Oct is still AEST (+10): 10:00 local is f0 (no heating then, so it is left out), 11:00 to 18:00
    # = 01Z to 08Z = f1 to f8
    assert blocks[:8] == [1, 2, 3, 4, 5, 6, 7, 8]
    # 4 Oct is AEDT (+11): 10:00 to 18:00 local = 23Z (3 Oct) to 07Z = f23 to f31
    assert blocks[8:17] == list(range(23, 32))
    assert len(blocks) == 8 + 3 * 9  # today from 11:00, then three full days of nine hourly blocks
    assert all(h % 3 == 0 for h in outlook) and outlook and min(outlook) > max(blocks)


def test_plan_hours_late_in_day_starts_tomorrow():
    now = datetime(2026, 10, 3, 8, 30, tzinfo=UTC)  # 18:30 AEST: after the last block hour
    _, _, first = gfs.plan_hours(gfs.Cycle("20261003", 6), now, TZ)
    assert first == "2026-10-04"


def sample(day, hour_utc, **kw):
    s = {
        "time": datetime(2026, 10, day, hour_utc, tzinfo=UTC),
        "u10": 0.0, "v10": -3.0, "u850": 0.0, "v850": -4.0,
        "hpbl_m": 1500.0, "shtfl_wm2": 250.0, "t2_c": 16.0,
    }  # fmt: skip
    s.update(kw)
    return s


def test_blocks_only_at_block_hours_and_in_range(rules, site):
    # 23Z (3 Oct) and 00Z to 07Z on 4 Oct = 10:00 to 18:00 AEDT; 08Z = 19:00 is not a block hour
    samples = [sample(3, 23)] + [sample(4, h) for h in range(0, 9)] + [sample(9, 0)]
    blocks = blocks_from_samples(samples, rules, site, "2026-10-04")
    assert [b.start[11:16] for b in blocks] == [f"{h}:00" for h in range(10, 19)]
    # updraft about 2.3 m/s: decent thermals but under the 2.5 m/s that Good needs
    assert blocks[0].wind_ground.kph == 11 and blocks[0].verdict_pg == "ok"


def test_negative_flux_does_not_create_updraft(rules, site):
    b = blocks_from_samples([sample(4, 0, shtfl_wm2=-30.0)], rules, site, "2026-10-04")[0]
    assert b.updraft_ms == 0 and b.verdict_pg == "poor"


def test_outlook_starts_after_the_detailed_days(rules, site):
    samples = [sample(d, 2) for d in range(4, 10)]
    out = outlook_after_blocks(samples, rules, site, "2026-10-04")
    # the outlook starts the day after the last detailed day: 4 Oct + 4 days = 8 Oct
    assert [o.date for o in out] == ["2026-10-08", "2026-10-09"]


def sample_with_profile(**kw):
    s = sample(4, 0, **kw)
    # surface 697 m (northerly 2 m/s) rising to 1030 m (northerly 6 m/s): 800 m is about 31% up
    s["profile"] = [(697.0, 0.0, -2.0), (1030.0, 0.0, -6.0)]
    return s


def test_launch_wind_is_interpolated_at_site_elevation(rules, site):
    b = blocks_from_samples([sample_with_profile()], rules, site, "2026-10-04")[0]
    assert b.wind_launch is not None
    assert b.wind_launch.dir_deg in (0, 360)
    assert 11 <= b.wind_launch.kph <= 13  # (2 + 0.31*4) m/s = 3.2 m/s = 11.7 kph


def test_verdict_is_judged_on_launch_wind(rules, site):
    # light 10 m wind from the south (outside the sector) but a northerly at launch altitude
    s = sample_with_profile(u10=0.0, v10=2.0)
    s["profile"] = [(697.0, 0.0, -2.0), (1030.0, 0.0, -2.5)]
    b = blocks_from_samples([s], rules, site, "2026-10-04")[0]
    assert b.verdict_pg in ("ok", "good", "poor") and not any("outside" in r for r in b.reasons)


def test_without_a_profile_launch_wind_is_absent(rules, site):
    b = blocks_from_samples([sample(4, 0)], rules, site, "2026-10-04")[0]
    assert b.wind_launch is None


def test_outlook_uses_launch_wind_when_available(rules, site):
    s = sample_with_profile()
    out = outlook_after_blocks([s], rules, site, "2026-09-30")
    assert out and out[0].wind.dir_deg in (0, 360) and out[0].wind.kph < 20


def test_a_run_reaches_day_four_blocks_and_day_seven_outlook():
    now = datetime(2026, 10, 3, 1, 0, tzinfo=UTC)
    blocks, outlook, first = gfs.plan_hours(CYCLE, now, TZ)
    assert first == "2026-10-03"
    # day 4 (6 Oct) 18:00 AEDT = 07Z = f79: inside GFS's hourly range, so blocks are available
    assert max(blocks) == 79 and max(blocks) <= 120
    # day 7 (9 Oct) outlook steps reach about f150, well inside what a cycle publishes
    assert 140 <= max(outlook) <= 160 and all(h % 3 == 0 for h in outlook)
    # outlook covers exactly days 5, 6 and 7 (three days, three steps each: 11-17h local)
    assert len(outlook) >= 3


def test_late_in_the_day_the_first_day_moves_on_and_the_horizon_with_it():
    now = datetime(2026, 10, 3, 8, 0, tzinfo=UTC)  # 19:00 AEDT
    _, outlook, first = gfs.plan_hours(gfs.Cycle("20261003", 6), now, TZ)
    assert first == "2026-10-04"
    assert max(outlook) <= 192  # the cycle-availability check (runner.last_hour) covers it
