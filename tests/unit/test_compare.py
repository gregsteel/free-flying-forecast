import json
from datetime import UTC, datetime, timedelta

from ffforecast import cli, compare, history, observations

TZ = "Australia/Melbourne"
DATE = "2026-10-06"
BLOCK_UTC = datetime(2026, 10, 6, 2, 0, tzinfo=UTC)  # 13:00 AEDT


def buckets(avg=20.0, gust=30.0, direction=350, n=26, start=None, count=12, cloudbase=1700):
    start = start or BLOCK_UTC - timedelta(minutes=30)
    out = {}
    for i in range(count):
        t = start + timedelta(minutes=5 * i)
        out[t.isoformat().replace("+00:00", "Z")] = {
            "n": n, "avg_kph": avg, "gust_kph": gust, "lull_kph": 5.0, "dir_deg": direction,
            "temp_c": 16.0, "humidity": 60.0, "qnh_pa": 101800, "dew_c": 8.0, "cloudbase_m": cloudbase,
        }  # fmt: skip
    return out


def block(**kw):
    b = {
        "start": "2026-10-06T13:00:00+11:00",
        "wind_ground": {"dir_deg": 340, "kph": 8},
        "wind_launch": {"dir_deg": 330, "kph": 10},
        "wind_ausrasp_kph": 22,
        "gust_kph": 12,
        "gust_launch_kph": 28,
        "temp_ground_c": 18,
        "thermal_height_m": 1650,
        "verdict_pg": "turbulent",
    }
    b.update(kw)
    return b


def snapshot(issued, blocks=None):
    return {"issued": issued, "cycle": "c", "blocks": blocks or [block()]}


def setup(tmp_path, snaps, bks=None):
    h, o = tmp_path / "history", tmp_path / "obs"
    h.mkdir(parents=True, exist_ok=True)
    (h / f"{DATE}.jsonl").write_text("\n".join(json.dumps(s) for s in snaps) + "\n")
    observations.store_buckets(o, bks if bks is not None else buckets(), TZ)
    return h, o


# ---- the measured hour


def test_the_hour_is_centred_on_the_block_start():
    m = compare.measured_hour(buckets(), BLOCK_UTC)
    assert m is not None and m["avg_kph"] == 20 and m["gust_kph"] == 30 and m["buckets"] == 12
    assert m["cloudbase_m"] == 1700 and not m["coarse"]


def test_too_few_buckets_means_no_measurement():
    assert compare.measured_hour(buckets(count=5), BLOCK_UTC) is None
    assert compare.measured_hour(buckets(count=6), BLOCK_UTC) is not None


def test_buckets_from_a_thinned_log_are_marked_coarse():
    m = compare.measured_hour(buckets(n=5), BLOCK_UTC)
    assert m is not None and m["coarse"] is True


def test_the_strongest_gust_in_the_hour_is_used():
    b = buckets()
    b[next(iter(b))]["gust_kph"] = 55.0
    m = compare.measured_hour(b, BLOCK_UTC)
    assert m is not None and m["gust_kph"] == 55.0


# ---- which forecast stood when


def test_the_forecast_that_stood_the_evening_before_and_that_morning_are_picked():
    snaps = [
        snapshot("2026-10-04T20:00:00+11:00"),
        snapshot("2026-10-05T22:00:00+11:00"),  # the last before midnight
        snapshot("2026-10-06T06:00:00+11:00"),  # the last before 08:00
        snapshot("2026-10-06T12:00:00+11:00"),  # after the day has begun: never used
    ]
    picked = compare.pick_snapshots(snaps, DATE, TZ)
    assert picked["day_before"]["issued"] == "2026-10-05T22:00:00+11:00"
    assert picked["morning"]["issued"] == "2026-10-06T06:00:00+11:00"


def test_a_kind_with_no_forecast_in_time_is_left_out():
    assert compare.pick_snapshots([snapshot("2026-10-06T09:00:00+11:00")], DATE, TZ) == {}


# ---- the scores


def test_bias_and_error_are_forecast_minus_measured(tmp_path, rules):
    h, o = setup(tmp_path, [snapshot("2026-10-06T06:00:00+11:00")])
    s = compare.compare_dates(h, o, [DATE], rules, TZ)["summary"]["morning"]
    assert s["blocks"] == 1
    assert s["wind"]["launch"]["bias"] == -10.0  # 10 forecast against 20 measured
    assert s["wind"]["ausrasp_10m"]["bias"] == 2.0
    assert s["wind"]["judged"]["bias"] == 2.0  # the stronger of launch and AUSRASP
    assert s["gust"]["model_10m"]["bias"] == -18.0
    assert s["gust"]["estimate_at_launch"]["bias"] == -2.0
    assert s["temperature_c"]["bias"] == 2.0
    assert s["thermal_height_vs_cumulus_base_m"]["bias"] == -50.0
    assert s["direction_mae_deg"] == {"n": 1, "mae": 20}


def test_rough_air_hits_and_quiet_hours(tmp_path, rules):
    quiet = block(
        start="2026-10-06T14:00:00+11:00",
        wind_launch={"dir_deg": 330, "kph": 5},
        wind_ausrasp_kph=5,
        gust_launch_kph=8,
    )
    bk = buckets()
    bk.update(buckets(avg=3.0, gust=5.0, start=BLOCK_UTC + timedelta(minutes=30)))
    h, o = setup(tmp_path, [snapshot("2026-10-06T06:00:00+11:00", [block(), quiet])], bk)
    r = compare.compare_dates(h, o, [DATE], rules, TZ)["summary"]["morning"]["rough_air"]
    assert r == {"hit": 1, "false_alarm": 0, "miss": 0, "quiet": 1}


def test_a_quiet_forecast_on_a_rough_day_is_a_miss_and_the_reverse_a_false_alarm(tmp_path, rules):
    calm = block(
        wind_launch={"dir_deg": 330, "kph": 4}, wind_ausrasp_kph=4, gust_launch_kph=6, gust_kph=6
    )
    h, o = setup(tmp_path / "a", [snapshot("2026-10-06T06:00:00+11:00", [calm])])
    miss = compare.compare_dates(h, o, [DATE], rules, TZ)["summary"]["morning"]["rough_air"]
    assert miss["miss"] == 1
    h, o = setup(
        tmp_path / "b", [snapshot("2026-10-06T06:00:00+11:00")], buckets(avg=3.0, gust=5.0)
    )
    alarm = compare.compare_dates(h, o, [DATE], rules, TZ)["summary"]["morning"]["rough_air"]
    assert alarm["false_alarm"] == 1


def test_thermal_height_far_below_the_cumulus_base_is_not_counted(tmp_path, rules):
    # 900 m against a 1,700 m base: limited by the thermals, not by cloud, so it says nothing
    h, o = setup(tmp_path, [snapshot("2026-10-06T06:00:00+11:00", [block(thermal_height_m=900)])])
    s = compare.compare_dates(h, o, [DATE], rules, TZ)["summary"]["morning"]
    assert s["thermal_height_vs_cumulus_base_m"] is None


def test_direction_is_only_scored_when_the_wind_was_blowing(tmp_path, rules):
    h, o = setup(tmp_path, [snapshot("2026-10-06T06:00:00+11:00")], buckets(avg=2.0, gust=3.0))
    s = compare.compare_dates(h, o, [DATE], rules, TZ)["summary"]["morning"]
    assert s["direction_mae_deg"] is None


def test_an_older_forecast_without_the_new_fields_still_scores(tmp_path, rules):
    old = block()
    for k in ("gust_launch_kph", "wind_ausrasp_kph", "wind_launch"):
        old.pop(k)
    h, o = setup(tmp_path, [snapshot("2026-10-06T06:00:00+11:00", [old])])
    s = compare.compare_dates(h, o, [DATE], rules, TZ)["summary"]["morning"]
    assert s["wind"]["ausrasp_10m"] is None and s["gust"]["estimate_at_launch"] is None
    assert s["wind"]["ground_10m"]["n"] == 1


# ---- the report


def test_a_date_without_both_halves_gives_an_explained_empty_report(tmp_path, rules):
    res = compare.compare_dates(tmp_path / "history", tmp_path / "obs", [DATE], rules, TZ)
    assert res["summary"] == {} and "Nothing to compare yet" in compare.format_report(res)


def test_the_report_names_each_score_and_flags_thinned_data(tmp_path, rules):
    h, o = setup(tmp_path, [snapshot("2026-10-06T06:00:00+11:00")], buckets(n=5))
    res = compare.compare_dates(h, o, [DATE], rules, TZ)
    text = compare.format_report(res, show_blocks=True)
    for want in (
        "Forecast made that morning",
        "AUSRASP, 10 m",
        "estimate at launch",
        "Rough air",
        "thinned",
        "2026-10-06  13:00",
    ):
        assert want in text, want


def test_the_last_n_dates_before_today():
    now = datetime(2026, 10, 6, 5, 0, tzinfo=UTC)  # the 6th, 16:00 local
    assert compare.dates_back(now, 3, TZ) == ["2026-10-03", "2026-10-04", "2026-10-05"]


def test_the_command_runs_on_an_empty_state(tmp_path, capsys):
    assert cli.main(["compare", "--state", str(tmp_path)]) == 0
    assert "Nothing to compare yet" in capsys.readouterr().out


def test_a_history_file_written_by_the_run_can_be_compared(fixture_path, tmp_path, rules):
    from ffforecast.models import Forecast

    fc = Forecast.from_dict(json.loads(fixture_path.read_text()))
    history.record(tmp_path / "history", fc, TZ)
    res = compare.compare_dates(tmp_path / "history", tmp_path / "obs", ["2026-10-05"], rules, TZ)
    assert res["summary"] == {}  # no measurements: empty, and nothing fails on the real block shape
