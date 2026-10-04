"""AUSRASP in the run: stages, fallback block by block, and the stored values on rebuild."""

import dataclasses
import json
from datetime import UTC, datetime, timedelta

import pytest

from fake_ausrasp import BASE, World
from ffforecast import ausrasp, runner

NOW = datetime(
    2026, 10, 3, 6, 0, tzinfo=UTC
)  # 16:00 AEST on the 3rd; the cycle is 00Z the same day
CYCLE = "2026-10-03T00Z"


def sample(day, hour_utc):
    return {
        "time": datetime(2026, 10, day, hour_utc, tzinfo=UTC),
        "u10": 0.0, "v10": -3.0, "u850": 0.0, "v850": -4.0,
        "hpbl_m": 1500.0, "shtfl_wm2": 250.0, "t2_c": 16.0,
    }  # fmt: skip


@pytest.fixture
def setup(site, rules, tmp_path, monkeypatch):
    s = dataclasses.replace(site, ausrasp=dataclasses.replace(site.ausrasp, base_url=BASE))
    world = World(NOW, site.lat, site.lon)
    samples = [sample(3, h) for h in (1, 3, 5, 7)] + [sample(4, h) for h in (0, 2, 4, 6)]
    monkeypatch.setattr(runner.gfs, "fetch_forecast_hour", lambda *a, **k: tmp_path / "f.grib2")
    monkeypatch.setattr(runner, "read_gfs_samples", lambda *a, **k: [dict(x) for x in samples])
    monkeypatch.setattr(runner, "read_flux_samples", lambda *a, **k: {})
    sleeps = []
    monkeypatch.setattr(ausrasp.time, "sleep", sleeps.append)

    def build(refresh=True, cfg_site=s):
        cfg = runner.RunConfig(site=cfg_site, rules=rules, cache_dir=tmp_path / "cache", now=NOW)
        built = runner.gfs_stages(cfg, CYCLE, world, refresh)  # type: ignore[arg-type]
        return {st.name: st.fn for st in built}

    return world, build, tmp_path


def run_all(stages, staging):
    staging.mkdir(exist_ok=True)
    for name in ("ausrasp", "diagnose", "render"):
        stages[name](staging)
    return json.loads((staging / "forecast.json").read_text())


def test_stage_order_keeps_fetch_first_and_ausrasp_before_diagnose(setup):
    _, build, _ = setup
    assert list(build()) == ["fetch", "ausrasp", "diagnose", "render"]


def test_blocks_take_ausrasp_thermals_and_the_page_names_the_source(setup, capsys):
    world, build, tmp = setup
    world.height = lambda key, hhmm: 1844.0
    world.updraft = lambda key, hhmm: 3.0
    fc = run_all(build(), tmp / "staging")
    assert len(fc["blocks"]) == 8
    assert {b["thermal_source"] for b in fc["blocks"]} == {"ausrasp"}
    assert all(b["thermal_height_m"] == 1844 and b["updraft_ms"] == 3.0 for b in fc["blocks"])
    assert {b["thermal_run"] for b in fc["blocks"]} == {"2026-10-02T12:00:00Z"}
    assert "thermal: ausrasp (8 of 8 blocks)" in capsys.readouterr().out
    assert "AUSRASP" in (tmp / "staging" / "index.html").read_text()


def test_wind_and_rain_are_not_taken_from_ausrasp(setup):
    world, build, tmp = setup
    run_all(build(), tmp / "staging")
    asked = {p.split("/FCST/")[1].split(".")[0] for p, _ in world.requests if "/FCST/" in p}
    assert asked == {"hglider", "wstar"}  # nothing about wind, rain, cape or temperature


def test_when_ausrasp_is_down_the_run_still_works_on_the_estimate(setup, capsys):
    world, build, tmp = setup
    world.fail[""] = 503  # everything
    fc = run_all(build(), tmp / "staging")
    assert {b["thermal_source"] for b in fc["blocks"]} == {"gfs"}
    out = capsys.readouterr().out
    assert "AUSRASP unavailable" in out and "thermal: gfs estimate" in out


def test_one_missing_day_falls_back_for_that_day_only(setup):
    world, build, tmp = setup
    world.fail["OUT+1/"] = 404  # the 4th has no files
    fc = run_all(build(), tmp / "staging")
    by_day = {}
    for b in fc["blocks"]:
        by_day.setdefault(b["start"][:10], set()).add(b["thermal_source"])
    assert by_day == {"2026-10-03": {"ausrasp"}, "2026-10-04": {"gfs"}}


def test_turned_off_means_no_requests_and_the_estimate(setup, site):
    world, build, tmp = setup
    off = dataclasses.replace(site, ausrasp=dataclasses.replace(site.ausrasp, enabled=False))
    fc = run_all(build(cfg_site=off), tmp / "staging")
    assert world.requests == [] and {b["thermal_source"] for b in fc["blocks"]} == {"gfs"}


def test_a_rebuild_uses_stored_values_without_any_request(setup, site):
    world, build, tmp = setup
    ausrasp.refresh(
        dataclasses.replace(site.ausrasp, base_url=BASE), site, tmp / "cache", world,
        now=lambda: NOW, sleep=lambda s: None,
    )  # fmt: skip
    world.requests.clear()
    fc = run_all(build(refresh=False), tmp / "staging")
    assert world.requests == []
    assert {b["thermal_source"] for b in fc["blocks"]} == {"ausrasp"}


def test_stored_values_that_have_become_too_old_are_not_used(setup, site):
    world, build, tmp = setup
    world.runs = {k: r - timedelta(hours=24) for k, r in world.runs.items()}  # 42 hours old at NOW
    ausrasp.refresh(
        dataclasses.replace(site.ausrasp, base_url=BASE), site, tmp / "cache", world,
        now=lambda: NOW, sleep=lambda s: None,
    )  # fmt: skip
    fc = run_all(build(refresh=False), tmp / "staging")
    assert {b["thermal_source"] for b in fc["blocks"]} == {"gfs"}
