import dataclasses
import json
from datetime import UTC, datetime, timedelta

import pytest

from ffforecast import observations as obs
from ffforecast.config import ObservationsConfig

TZ = "Australia/Melbourne"
HEADER = (
    "PowerOnIndex,Date_Time,Windspeedmph,WindspeedmphMax,WindspeedmphMin,Winddir,QNH,realQNH,"
    "Tempc,Humidity,DewPoint,CloudbaseAGLft_AMSL,Battery,CSQ"
)
CFG = ObservationsConfig(enabled=True, url="https://station.test/table.php")


def csv_text(rows):
    """rows: (local time, avg mph, max, min, dir) oldest first; the file is newest first."""
    lines = [
        f'{i},"{t}",{a},{mx},{mn},{d},92600,101860,18.8,64,11.9,5445,13.4,26'
        for i, (t, a, mx, mn, d) in enumerate(rows)
    ]
    return "\n".join([HEADER, *reversed(lines)]) + "\n"


def test_readings_are_in_utc_oldest_first_and_in_kph():
    text = csv_text([("2026-10-05 10:00:00", 10, 14, 6, 350), ("2026-10-05 10:00:11", 5, 8, 3, 10)])
    readings, skipped = obs.parse_csv(text, TZ)
    assert skipped == 0 and [r.time for r in readings] == [
        datetime(2026, 10, 4, 23, 0, 0, tzinfo=UTC),  # 10:00 AEDT
        datetime(2026, 10, 4, 23, 0, 11, tzinfo=UTC),
    ]
    assert (readings[0].avg_kph, readings[0].gust_kph, readings[0].lull_kph) == (16.1, 22.5, 9.7)
    assert readings[0].cloudbase_m == 1660 and readings[0].dew_c == 11.9


def test_the_hour_that_repeats_when_daylight_saving_ends_is_told_apart():
    text = csv_text(
        [
            ("2026-04-05 02:55:00", 5, 6, 4, 0),  # first time round (still AEDT, +11)
            ("2026-04-05 02:15:00", 5, 6, 4, 0),  # the clocks went back: AEST, +10
            ("2026-04-05 03:05:00", 5, 6, 4, 0),
        ]
    )
    times = [r.time for r in obs.parse_csv(text, TZ)[0]]
    assert times == [
        datetime(2026, 4, 4, 15, 55, tzinfo=UTC),
        datetime(2026, 4, 4, 16, 15, tzinfo=UTC),
        datetime(2026, 4, 4, 17, 5, tzinfo=UTC),
    ]
    assert times == sorted(times)


def test_bad_rows_are_skipped_and_a_wrong_file_is_refused():
    good = csv_text([("2026-10-05 10:00:00", 5, 6, 4, 0)])
    bad = (
        good
        + '9,"not a time",1,2,3,4,5,6,7,8,9,10,11,12\n10,"2026-10-05 10:01:00",,2,3,4,5,6,7,8,9,10,11,12\n'
    )
    readings, skipped = obs.parse_csv(bad, TZ)
    assert len(readings) == 1 and skipped == 2
    with pytest.raises(ValueError, match="station's log"):
        obs.parse_csv("<html>login</html>\nx\n", TZ)


def test_a_bucket_holds_the_average_strongest_gust_and_lightest_lull():
    text = csv_text(
        [("2026-10-05 10:00:00", 10, 14, 6, 350), ("2026-10-05 10:01:00", 10, 20, 2, 10)]
    )
    (b,) = obs.bucketize(obs.parse_csv(text, TZ)[0]).values()
    assert b["n"] == 2 and b["avg_kph"] == 16.1
    assert b["gust_kph"] == 32.2 and b["lull_kph"] == 3.2
    assert b["dir_deg"] in (0, 360)  # 350 and 10 average to north, not south


def test_calm_air_has_no_direction():
    text = csv_text([("2026-10-05 10:00:00", 0, 0, 0, 120)])
    (b,) = obs.bucketize(obs.parse_csv(text, TZ)[0]).values()
    assert b["dir_deg"] is None


def test_buckets_are_five_minutes_apart():
    text = csv_text([("2026-10-05 10:00:00", 5, 6, 4, 0), ("2026-10-05 10:06:00", 5, 6, 4, 0)])
    assert list(obs.bucketize(obs.parse_csv(text, TZ)[0])) == [
        "2026-10-04T23:00:00Z",
        "2026-10-04T23:05:00Z",
    ]


# ---- the store


def test_buckets_go_in_the_file_of_their_local_date(tmp_path):
    text = csv_text([("2026-10-05 10:00:00", 5, 6, 4, 0), ("2026-10-06 00:30:00", 5, 6, 4, 0)])
    assert obs.store_buckets(tmp_path, obs.bucketize(obs.parse_csv(text, TZ)[0]), TZ) == 2
    assert len(obs.read_day(tmp_path, "2026-10-05")) == 1
    assert len(obs.read_day(tmp_path, "2026-10-06")) == 1


def test_storing_the_same_download_again_changes_nothing(tmp_path):
    b = obs.bucketize(obs.parse_csv(csv_text([("2026-10-05 10:00:00", 5, 6, 4, 0)]), TZ)[0])
    obs.store_buckets(tmp_path, b, TZ)
    assert obs.store_buckets(tmp_path, b, TZ) == 0


def test_a_fuller_bucket_replaces_a_part_one_but_not_the_other_way(tmp_path):
    part = obs.bucketize(obs.parse_csv(csv_text([("2026-10-05 10:00:00", 5, 6, 4, 0)]), TZ)[0])
    full = obs.bucketize(
        obs.parse_csv(
            csv_text([("2026-10-05 10:00:00", 5, 6, 4, 0), ("2026-10-05 10:00:11", 9, 9, 9, 0)]), TZ
        )[0]
    )
    obs.store_buckets(tmp_path, part, TZ)
    assert obs.store_buckets(tmp_path, full, TZ) == 1
    assert obs.store_buckets(tmp_path, part, TZ) == 0
    assert next(iter(obs.read_day(tmp_path, "2026-10-05").values()))["n"] == 2


# ---- how much to download


NOW = datetime(2026, 10, 5, 11, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    ("gap_h", "hours"),
    [(10, 24), (24, 48), (40, 48), (50, 168), (6 * 24, 168), (8 * 24, 720), (29 * 24, 720)],
)
def test_the_log_is_long_enough_to_reach_the_last_reading(gap_h, hours):
    assert obs.plan_hours(NOW - timedelta(hours=gap_h), NOW)[0] == hours


def test_the_first_ever_download_takes_the_longest_log():
    hours, note = obs.plan_hours(None, NOW)
    assert hours == 720 and "30 days" in note


def test_a_normal_daily_gap_needs_no_note_and_a_long_one_says_so():
    assert obs.plan_hours(NOW - timedelta(hours=24), NOW)[1] == ""
    assert "catching up after 4.0 days" in obs.plan_hours(NOW - timedelta(days=4), NOW)[1]


def test_a_gap_beyond_thirty_days_is_reported_as_lost():
    hours, note = obs.plan_hours(NOW - timedelta(days=40), NOW)
    assert hours == 720 and "lost" in note


# ---- when to download


def status(tmp_path, **kw):
    obs.obs_dir(tmp_path).mkdir(parents=True)
    (obs.obs_dir(tmp_path) / "status.json").write_text(json.dumps(kw))
    return obs.obs_dir(tmp_path)


LOCAL_EVENING = datetime(2026, 10, 5, 11, 0, tzinfo=UTC)  # 22:00 AEDT, after the 21:30 run time


def test_nothing_is_due_when_it_is_turned_off(tmp_path):
    off = dataclasses.replace(CFG, enabled=False)
    assert not obs.due(off, tmp_path, LOCAL_EVENING, TZ)


def test_the_first_download_is_due_at_once(tmp_path):
    assert obs.due(CFG, tmp_path, LOCAL_EVENING - timedelta(hours=8), TZ)


def test_a_day_is_downloaded_once_after_the_run_time(tmp_path):
    last = (LOCAL_EVENING - timedelta(hours=1)).isoformat()
    d = status(tmp_path, last_reading=last, last_fetch_date="2026-10-04")
    assert obs.due(CFG, d, LOCAL_EVENING, TZ)  # not yet fetched for the 5th
    (d / "status.json").write_text(
        json.dumps({"last_reading": last, "last_fetch_date": "2026-10-05"})
    )
    assert not obs.due(CFG, d, LOCAL_EVENING, TZ)


def test_nothing_is_due_before_the_run_time(tmp_path):
    morning = datetime(2026, 10, 5, 0, 0, tzinfo=UTC)  # 11:00 AEDT
    d = status(
        tmp_path,
        last_reading=(morning - timedelta(hours=12)).isoformat(),
        last_fetch_date="2026-10-04",
    )
    assert not obs.due(CFG, d, morning, TZ)


def test_a_missed_day_is_caught_up_at_once_even_before_the_run_time(tmp_path):
    morning = datetime(2026, 10, 5, 0, 0, tzinfo=UTC)
    d = status(
        tmp_path,
        last_reading=(morning - timedelta(hours=40)).isoformat(),
        last_fetch_date="2026-10-03",
    )
    assert obs.due(CFG, d, morning, TZ)


# ---- the whole refresh


class Resp:
    def __init__(self, status_code=200, text=""):
        self.status_code, self.text = status_code, text


class Session:
    def __init__(self, text="", status_code=200):
        self.text, self.status_code, self.calls = text, status_code, []

    def get(self, url, params=None, headers=None, timeout=0):
        self.calls.append((url, params, headers))
        return Resp(self.status_code, self.text)


def test_a_refresh_stores_the_log_and_notes_when_it_ran(tmp_path):
    text = csv_text([("2026-10-05 10:00:00", 5, 6, 4, 0), ("2026-10-05 10:10:00", 8, 9, 7, 0)])
    s = Session(text)
    r = obs.refresh(CFG, tmp_path, TZ, s, "test-agent", NOW)
    assert not r.error and r.readings == 2 and r.buckets_changed == 2
    url, params, headers = s.calls[0]
    assert url == CFG.url and params == {"h": 720, "download": "csv"}  # the first time: 30 days
    assert headers["User-Agent"] == "test-agent"
    st = obs.read_status(obs.obs_dir(tmp_path))
    assert st["last_reading"] == "2026-10-04T23:10:00Z" and st["last_fetch_date"] == "2026-10-05"


def test_the_next_days_refresh_asks_for_two_days(tmp_path):
    first = csv_text([("2026-10-05 10:00:00", 5, 6, 4, 0), ("2026-10-05 21:00:00", 5, 6, 4, 0)])
    obs.refresh(CFG, tmp_path, TZ, Session(first), "a", NOW)
    s = Session(csv_text([("2026-10-06 21:00:00", 5, 6, 4, 0)]))
    obs.refresh(CFG, tmp_path, TZ, s, "a", NOW + timedelta(hours=24))
    assert s.calls[0][1]["h"] == 48


def test_a_gap_the_log_could_not_cover_is_recorded(tmp_path):
    obs.refresh(
        CFG, tmp_path, TZ, Session(csv_text([("2026-10-05 10:00:00", 5, 6, 4, 0)])), "a", NOW
    )
    later = NOW + timedelta(days=40)
    r = obs.refresh(
        CFG, tmp_path, TZ, Session(csv_text([("2026-11-14 10:00:00", 5, 6, 4, 0)])), "a", later
    )
    assert any("lost" in n for n in r.notes) and any("no readings between" in n for n in r.notes)
    assert len(obs.read_status(obs.obs_dir(tmp_path))["gaps"]) == 1


def test_a_failed_download_stores_no_readings_and_does_not_raise(tmp_path):
    r = obs.refresh(CFG, tmp_path, TZ, Session("", 500), "a", NOW)
    assert "HTTP 500" in r.error and not obs.read_day(obs.obs_dir(tmp_path), "2026-10-05")
    r = obs.refresh(CFG, tmp_path, TZ, Session("<html>maintenance</html>"), "a", NOW)
    assert "station's log" in r.error
    assert obs.last_reading(obs.obs_dir(tmp_path)) is None


def test_after_a_failure_it_waits_an_hour_before_trying_again(tmp_path):
    obs.refresh(CFG, tmp_path, TZ, Session("", 500), "a", LOCAL_EVENING)
    d = obs.obs_dir(tmp_path)
    assert not obs.due(CFG, d, LOCAL_EVENING + timedelta(minutes=30), TZ)
    assert obs.due(CFG, d, LOCAL_EVENING + timedelta(minutes=61), TZ)


def test_a_failure_does_not_forget_what_was_already_held(tmp_path):
    ok = csv_text([("2026-10-05 10:00:00", 5, 6, 4, 0)])
    obs.refresh(CFG, tmp_path, TZ, Session(ok), "a", NOW)
    obs.refresh(CFG, tmp_path, TZ, Session("", 503), "a", NOW + timedelta(hours=30))
    st = obs.read_status(obs.obs_dir(tmp_path))
    assert st["last_reading"] == "2026-10-04T23:00:00Z" and "503" in st["last_error"]


def test_it_does_nothing_when_turned_off(tmp_path):
    off = dataclasses.replace(CFG, enabled=False)
    s = Session("x")
    assert obs.refresh(off, tmp_path, TZ, s, "a", NOW).error and not s.calls


# ---- the command


def test_the_command_downloads_and_reports(tmp_path, monkeypatch, capsys):
    import requests

    from ffforecast import cli

    now = datetime.now(UTC).astimezone(__import__("zoneinfo").ZoneInfo(TZ))
    stamp = now.strftime("%Y-%m-%d %H:%M:%S")
    asked = []

    def fake_get(self, url, params=None, headers=None, timeout=0):
        asked.append((url, params))
        return Resp(200, csv_text([(stamp, 5, 6, 4, 0)]))

    monkeypatch.setattr(requests.Session, "get", fake_get)
    assert cli.main(["observe", "--state", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "1 readings from the last 720 hours" in out and "starting with the longest log" in out
    assert asked[0][1] == {"h": 720, "download": "csv"}
    # run again straight away with --if-due: today is done, so it is silent and asks for nothing
    assert cli.main(["observe", "--if-due", "--state", str(tmp_path)]) == 0
    assert capsys.readouterr().out == "" and len(asked) == 1


def test_a_failed_download_is_reported_and_exits_with_an_error(tmp_path, monkeypatch, capsys):
    import requests

    from ffforecast import cli

    monkeypatch.setattr(requests.Session, "get", lambda self, *a, **k: Resp(503, ""))
    assert cli.main(["observe", "--state", str(tmp_path)]) == 3
    assert "HTTP 503" in capsys.readouterr().err
