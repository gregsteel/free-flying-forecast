from datetime import UTC, datetime

from ffforecast.outlook import outlook_from_samples


def sample(hour_utc, day=7, u=0.0, v=-3.0):
    return {
        "time": datetime(2026, 10, day, hour_utc, tzinfo=UTC),
        "u10": u, "v10": v, "hpbl_m": 1500, "shtfl_wm2": 200, "t2_c": 15,
    }  # fmt: skip


def test_one_outlook_per_local_day_low_confidence(rules):
    # 02:00-06:00 UTC is 13:00-17:00 AEDT
    samples = [sample(h, day=d) for d in (7, 8) for h in (2, 5)]
    out = outlook_from_samples(samples, rules, "Australia/Melbourne", 785, "2026-10-07")
    assert [o.date for o in out] == ["2026-10-07", "2026-10-08"]
    assert all(o.confidence == "low" for o in out)


def test_night_samples_ignored(rules):
    out = outlook_from_samples([sample(15)], rules, "Australia/Melbourne", 785, "2026-10-07")
    assert out == []


def test_strong_wind_is_not_good(rules):
    out = outlook_from_samples(
        [sample(2, v=-12.0)], rules, "Australia/Melbourne", 785, "2026-10-07"
    )  # 43 kph northerly
    assert out[0].verdict == "bad"
