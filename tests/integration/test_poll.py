"""`ffforecast poll`: the check, the schedule, the rebuild and the lock."""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from fake_ausrasp import BASE, World
from ffforecast import ausrasp, cli
from ffforecast.state import RunRecord, State

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def env(tmp_path, monkeypatch):
    site_file = tmp_path / "site.toml"
    text = (ROOT / "config/site.mystic.toml").read_text()
    site_file.write_text(text.replace("https://ausrasp.com/VIC/", BASE))
    from ffforecast.config import load_site

    site = load_site(site_file)
    world = World(datetime.now(UTC), site.lat, site.lon)
    monkeypatch.setattr("requests.Session", lambda: world)
    monkeypatch.setattr(ausrasp.time, "sleep", lambda s: None)
    calls = []

    def fake_pipeline(find, stages, state, out, work, **kw):
        calls.append({"cycle": find(), "stages": stages, **kw})
        return 0, RunRecord(cycle=find() or "", started_at="", outcome="published", duration_s=1.0)

    monkeypatch.setattr(cli, "run_pipeline", fake_pipeline)

    def poll(*extra):
        argv = ["--site", str(site_file), "--rules", str(ROOT / "config/rules.toml"), "poll",
                "--cache", str(tmp_path / "cache"), "--state", str(tmp_path / "state"),
                "--out", str(tmp_path / "out"), "--work", str(tmp_path / "work"), *extra]  # fmt: skip
        return cli.main(argv)

    return world, poll, calls, tmp_path


def publish_a_cycle(tmp_path, cycle="2026-10-03T00Z"):
    State(tmp_path / "state").record(RunRecord(cycle=cycle, started_at="", outcome="published"))


def test_first_poll_stores_all_days(env, capsys):
    world, poll, calls, tmp = env
    assert poll("--no-rebuild") == 0
    assert "poll: 7 changed" in capsys.readouterr().out and calls == []
    assert len(list((ausrasp.store_dir(tmp / "cache") / "days").glob("*.json"))) == 7


def test_nothing_changed_means_no_rebuild(env, capsys):
    world, poll, calls, tmp = env
    publish_a_cycle(tmp)
    poll()
    capsys.readouterr()
    assert poll() == 0
    assert "poll: no change" in capsys.readouterr().out and len(calls) == 1  # only the first


def test_a_change_rebuilds_once_from_the_last_published_cycle_with_force(env, capsys):
    world, poll, calls, tmp = env
    publish_a_cycle(tmp)
    assert poll() == 0
    assert len(calls) == 1
    assert calls[0]["cycle"] == "2026-10-03T00Z" and calls[0]["force"] is True
    assert calls[0]["retries"] == 0
    assert "rebuild published" in capsys.readouterr().out


def test_the_rebuild_does_not_refresh_ausrasp_a_second_time(env, monkeypatch):
    world, poll, calls, tmp = env
    publish_a_cycle(tmp)
    seen = []
    real = cli.gfs_stages
    monkeypatch.setattr(
        cli,
        "gfs_stages",
        lambda cfg, c, s, refresh_ausrasp=True: (
            seen.append(refresh_ausrasp) or real(cfg, c, s, refresh_ausrasp)
        ),
    )
    poll()
    calls[0]["stages"]("2026-10-03T00Z")
    assert seen == [False]


def test_several_changed_days_are_one_rebuild(env):
    world, poll, calls, tmp = env
    publish_a_cycle(tmp)
    poll()
    assert len(calls) == 1  # seven days changed on the first check


def test_without_a_published_run_there_is_nothing_to_rebuild(env, capsys):
    world, poll, calls, tmp = env
    assert poll() == 0
    assert "no published run to rebuild" in capsys.readouterr().out and calls == []


def test_not_due_does_nothing_and_asks_nothing(env, capsys):
    world, poll, calls, tmp = env
    poll("--no-rebuild")
    world.requests.clear()
    capsys.readouterr()
    assert poll("--if-due", "--no-rebuild") == 0
    assert "poll: not due" in capsys.readouterr().out and world.requests == []


def test_a_first_check_is_always_due(env, capsys):
    world, poll, calls, tmp = env
    assert poll("--if-due", "--no-rebuild") == 0
    assert "poll: 7 changed" in capsys.readouterr().out


def test_an_unreachable_ausrasp_is_not_a_failure(env, capsys):
    world, poll, calls, tmp = env
    world.fail["version.json"] = 503
    publish_a_cycle(tmp)
    assert poll() == 0
    out = capsys.readouterr().out
    assert "AUSRASP unavailable" in out and calls == []
    status = ausrasp.read_status(ausrasp.store_dir(tmp / "cache"))
    assert "503" in status["fallback"]["reason"]


def test_turned_off_does_nothing(env, capsys, monkeypatch):
    world, poll, calls, tmp = env
    site_file = tmp / "site.toml"
    site_file.write_text(site_file.read_text().replace("enabled = true", "enabled = false"))
    assert poll() == 0
    assert "turned off" in capsys.readouterr().out and world.requests == []


def test_a_run_in_progress_picks_the_new_values_up_itself(env, capsys):
    world, poll, calls, tmp = env
    publish_a_cycle(tmp)
    with State(tmp / "state").lock():
        assert poll() == 0
    assert "a run is in progress" in capsys.readouterr().out and calls == []


def test_the_manifest_and_stamp_log_are_kept(env):
    world, poll, calls, tmp = env
    poll("--no-rebuild")
    log = (ausrasp.store_dir(tmp / "cache") / "stamps.jsonl").read_text().splitlines()
    assert len(log) == 7 and json.loads(log[0])["key"] == "OUT+0"
