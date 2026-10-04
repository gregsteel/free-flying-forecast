import json
from dataclasses import replace
from datetime import datetime
from zoneinfo import ZoneInfo

from ffforecast import history
from ffforecast.models import Forecast

TZ = "Australia/Melbourne"


def forecast(fixture_path) -> Forecast:
    return Forecast.from_dict(json.loads(fixture_path.read_text()))


def test_each_local_date_gets_its_own_file_with_that_dates_blocks(fixture_path, tmp_path):
    fc = forecast(fixture_path)
    written = history.record(tmp_path, fc, TZ)
    assert written == ["2026-10-04", "2026-10-05", "2026-10-06", "2026-10-07"]
    snap = history.read_day(tmp_path, "2026-10-05")
    assert len(snap) == 1 and len(snap[0]["blocks"]) == 9
    zone = ZoneInfo(TZ)
    assert {
        datetime.fromisoformat(b["start"]).astimezone(zone).date().isoformat()
        for b in snap[0]["blocks"]
    } == {"2026-10-05"}
    assert snap[0]["cycle"] == fc.cycle and snap[0]["rules_version"] == fc.rules_version
    assert "gust_launch_kph" in snap[0]["blocks"][0]  # the full block is kept


def test_an_unchanged_forecast_is_not_written_twice(fixture_path, tmp_path):
    fc = forecast(fixture_path)
    history.record(tmp_path, fc, TZ)
    assert history.record(tmp_path, fc, TZ) == []
    assert len(history.read_day(tmp_path, "2026-10-04")) == 1


def test_a_changed_day_adds_a_snapshot_and_the_others_stay(fixture_path, tmp_path):
    fc = forecast(fixture_path)
    history.record(tmp_path, fc, TZ)
    blocks = list(fc.blocks)
    blocks[0] = replace(blocks[0], verdict_pg="dangerous")  # a block on the first date
    changed = replace(fc, blocks=blocks, generated_at="2026-10-04T18:00:00+11:00")
    assert history.record(tmp_path, changed, TZ) == ["2026-10-04"]
    first = history.read_day(tmp_path, "2026-10-04")
    assert len(first) == 2 and first[-1]["issued"] == "2026-10-04T18:00:00+11:00"
    assert len(history.read_day(tmp_path, "2026-10-05")) == 1


def test_a_date_with_no_history_reads_as_empty(tmp_path):
    assert history.read_day(tmp_path, "2026-01-01") == []
