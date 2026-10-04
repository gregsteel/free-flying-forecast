"""The extra heating download improves the forecast but must never be able to stop it."""

from datetime import UTC, datetime
from pathlib import Path

import requests

from ffforecast import gfs, runner


def make_stages(site, rules, tmp_path):
    cfg = runner.RunConfig(
        site=site, rules=rules, cache_dir=tmp_path, now=datetime(2026, 10, 3, 1, 0, tzinfo=UTC)
    )
    return runner.gfs_stages(cfg, "2026-10-02T18Z", requests.Session())


def test_a_missing_heating_hour_does_not_fail_the_fetch(site, rules, tmp_path, monkeypatch, capsys):
    calls = []

    def fake(session, cycle, fhour, dest_dir, fields=gfs.DEFAULT_FIELDS):
        calls.append((fhour, fields))
        if fields == gfs.FLUX_FIELDS:
            raise RuntimeError("no wanted fields found")  # what NOAA's hour 0 gave on 2026-10-03
        return Path(dest_dir) / f"f{fhour}.grib2"

    monkeypatch.setattr(runner.gfs, "fetch_forecast_hour", fake)
    stages = make_stages(site, rules, tmp_path)
    stages[0].fn(tmp_path)  # the fetch stage: must not raise
    assert any(f == gfs.FLUX_FIELDS for _, f in calls)  # it did try to fetch the heating hours
    assert "using the window average" in capsys.readouterr().out


def test_heating_hours_are_fetched_with_only_the_heating_field(site, rules, tmp_path, monkeypatch):
    seen = []

    def fake(session, cycle, fhour, dest_dir, fields=gfs.DEFAULT_FIELDS):
        seen.append((fhour, fields))
        return Path(dest_dir) / f"f{fhour}.grib2"

    monkeypatch.setattr(runner.gfs, "fetch_forecast_hour", fake)
    make_stages(site, rules, tmp_path)[0].fn(tmp_path)
    flux = [(h, f) for h, f in seen if f == gfs.FLUX_FIELDS]
    assert flux and all(f == (("SHTFL", "surface"),) for _, f in flux)  # one small field each
    assert all(h >= 1 for h, _ in flux)  # forecast hour 0 holds no heating and is never requested
    assert len({h for h, _ in flux}) == len(flux)  # none twice
