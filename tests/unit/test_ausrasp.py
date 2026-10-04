import dataclasses
import json
from datetime import UTC, date, datetime, timedelta

import pytest

from fake_ausrasp import BASE, World, grid_text
from ffforecast import ausrasp
from ffforecast.ausrasp import (
    AusraspError,
    parse_grid,
    refresh,
    store_dir,
    thermal_lookup,
    wanted_hours,
)

HOURS = 9  # the page's hourly blocks, 10:00 to 18:00
EXPECTED_4TH = [
    "2026-10-03T23:00:00Z",
    *(f"2026-10-04T{h:02d}:00:00Z" for h in range(0, 8)),
]
NOW = datetime(
    2026, 10, 3, 6, 0, tzinfo=UTC
)  # Saturday afternoon in Victoria, before daylight saving


@pytest.fixture
def cfg(site):
    return dataclasses.replace(
        site.ausrasp, base_url=BASE, contact="https://example.test/ffforecast"
    )


@pytest.fixture
def world(site):
    return World(NOW, site.lat, site.lon)


LATER = NOW + timedelta(hours=2)  # the first refresh of seven days uses most of an hour's allowance


def run_refresh(cfg, site, tmp_path, world, now=NOW):
    return refresh(cfg, site, tmp_path, world, now=lambda: now, sleep=lambda s: None)


# ---- reading a grid file


def valid_text(
    param: str = "hglider",
    special: tuple[int, int, float] = (3, 4, 1844.0),
    unit: str = "m",
    mult: int = 1,
) -> str:
    t = datetime(2026, 10, 4, 5, tzinfo=UTC)  # 15:00 AES
    return grid_text(param, t, t - timedelta(hours=41), 100, special, unit, mult)


def test_parse_reads_header_valid_time_and_run():
    g = parse_grid(valid_text(), "hglider", (12, 12))
    assert g.valid_utc == datetime(2026, 10, 4, 5, tzinfo=UTC)
    assert g.run == datetime(2026, 10, 2, 12, tzinfo=UTC)  # 05Z less 41 hours
    assert g.values[3, 4] == 1844 and g.values[0, 0] == 100


def test_parse_divides_by_the_scale_factor():
    """The file holds scaled integers (Mult is 1 in every file seen so far)."""
    g = parse_grid(valid_text(mult=10, special=(3, 4, 18440.0)), "hglider", (12, 12))
    assert g.values[3, 4] == 1844


@pytest.mark.parametrize(
    "text, param, shape, fragment",
    [
        (valid_text(), "wstar", (12, 12), "expected quantity"),
        (valid_text(unit="ft"), "hglider", (12, 12), "unit"),
        (valid_text(), "hglider", (144, 144), "grid shape"),
        (valid_text(special=(1, 1, 9000.0)), "hglider", (12, 12), "outside"),
        (valid_text(special=(1, 1, -5.0)), "hglider", (12, 12), "outside"),
        ("not a grid\n", "hglider", (12, 12), "Day="),
    ],
)
def test_parse_rejects_what_is_not_expected(text, param, shape, fragment):
    with pytest.raises(AusraspError, match=fragment):
        parse_grid(text, param, shape)


# ---- the cell and the hours


def test_the_nearest_cell_is_found_and_its_distance_recorded(world):
    assert world.cell["shape"] == [12, 12]
    assert world.cell["distance_km"] < 3


def test_a_site_outside_the_grid_is_too_far(site, cfg, tmp_path):
    far = dataclasses.replace(site, lat=-30.0)
    w = World(NOW, far.lat, far.lon)
    r = refresh(cfg, far, tmp_path, w, now=lambda: NOW, sleep=lambda s: None)
    assert "km from the launch" in r.reason and not r.changed


def test_the_planned_hours_are_the_block_starts_in_utc_through_daylight_saving(site):
    before = wanted_hours(date(2026, 10, 3), site.timezone)  # still standard time (UTC+10)
    after = wanted_hours(date(2026, 10, 4), site.timezone)  # daylight time (UTC+11)
    assert [t.hour for t in before] == list(range(0, 9))  # 10:00 to 18:00 AEST
    assert [t.hour for t in after] == [
        23,
        *range(0, 8),
    ]  # 10:00 to 18:00 AEDT, from the evening before
    assert before[0] == datetime(2026, 10, 3, 0, tzinfo=UTC)
    assert after[0] == datetime(2026, 10, 3, 23, tzinfo=UTC)


# ---- fetching, storing, and following the manifest


def test_first_refresh_stores_every_day_and_the_lookup_returns_the_cell_values(
    site, cfg, tmp_path, world
):
    r = run_refresh(cfg, site, tmp_path, world)
    assert r.changed == [f"OUT+{n}" for n in range(7)] and not r.reason
    paths = [p for p, _ in world.requests]
    assert paths[:2] == ["latlon2d.json", "version.json"]
    assert len(paths) == 2 + 7 * 2 * HOURS  # nine hours, two quantities, seven days
    lookup, notes = thermal_lookup(tmp_path, cfg, NOW)
    t = lookup[datetime(2026, 10, 4, 4, tzinfo=UTC)]  # local 15:00 on the 4th
    assert (t.height_m, t.updraft_ms) == (1800, 2) and t.run == "2026-10-02T12:00:00Z"
    assert len(lookup) == 7 * HOURS and not notes


def test_an_unchanged_manifest_costs_one_small_request(site, cfg, tmp_path, world):
    run_refresh(cfg, site, tmp_path, world)
    world.requests.clear()
    r = run_refresh(cfg, site, tmp_path, world, LATER)
    assert r.changed == [] and [p for p, _ in world.requests] == ["version.json"]


def test_only_the_day_whose_stamp_changed_is_fetched(site, cfg, tmp_path, world):
    run_refresh(cfg, site, tmp_path, world)
    world.requests.clear()
    world.runs["OUT+2"] += timedelta(hours=12)
    world.stamps["OUT+2"] = "20261003T1700Z"
    world.height = lambda key, hhmm: 1500.0 if key == "OUT+2" else 1800.0
    r = run_refresh(cfg, site, tmp_path, world, LATER)
    assert r.changed == ["OUT+2"]
    paths = [p for p, _ in world.requests]
    assert len(paths) == 1 + 2 * HOURS and all(p.startswith("OUT+2/") for p in paths[1:])
    lookup, _ = thermal_lookup(tmp_path, cfg, NOW)
    assert lookup[datetime(2026, 10, 5, 4, tzinfo=UTC)].height_m == 1500


def test_every_stamp_change_is_logged_once(site, cfg, tmp_path, world):
    run_refresh(cfg, site, tmp_path, world)
    run_refresh(cfg, site, tmp_path, world, LATER)  # no change: nothing added
    world.stamps["OUT+3"] = "20261003T1900Z"
    world.runs["OUT+3"] += timedelta(hours=12)
    run_refresh(cfg, site, tmp_path, world, LATER)
    lines = [json.loads(x) for x in (store_dir(tmp_path) / "stamps.jsonl").read_text().splitlines()]
    assert len(lines) == 7 + 1
    assert lines[-1]["key"] == "OUT+3" and lines[-1]["new"] == "20261003T1900Z"
    assert lines[-1]["old"] is not None


def test_a_day_with_a_missing_file_is_not_used_and_the_old_set_stays(site, cfg, tmp_path, world):
    run_refresh(cfg, site, tmp_path, world)
    world.stamps["OUT+1"] = "20261003T1700Z"
    world.runs["OUT+1"] += timedelta(hours=12)
    world.fail["OUT+1/FCST/wstar.curr"] = 404
    r = run_refresh(cfg, site, tmp_path, world, LATER)
    assert r.changed == [] and any("OUT+1" in p for p in r.problems)
    held = ausrasp.read_day(store_dir(tmp_path), "OUT+1")
    assert held is not None and held["model_start"] == "2026-10-02T12:00:00Z"
    world.fail.clear()  # it is tried again at the next check
    assert run_refresh(cfg, site, tmp_path, world, LATER + timedelta(hours=2)).changed == ["OUT+1"]


def test_files_from_different_runs_are_rejected(site, cfg, tmp_path, world):
    calls = {"n": 0}
    real = world.get

    def mixed(url, headers=None, timeout=0):
        resp = real(url, headers, timeout)
        if "OUT+4/FCST/wstar.curr.1400" in url:
            world.runs["OUT+4"] += timedelta(hours=12)
            resp = real(url, headers, timeout)
            world.runs["OUT+4"] -= timedelta(hours=12)
            calls["n"] += 1
        return resp

    world.get = mixed  # type: ignore[method-assign]
    r = run_refresh(cfg, site, tmp_path, world)
    assert "OUT+4" not in r.changed and any("different model runs" in p for p in r.problems)


def test_an_older_run_never_replaces_a_newer_one(site, cfg, tmp_path, world):
    world.runs["OUT+2"] += timedelta(hours=12)
    run_refresh(cfg, site, tmp_path, world)
    world.runs["OUT+2"] -= timedelta(hours=12)
    world.stamps["OUT+2"] = "20261003T0100Z"
    r = run_refresh(cfg, site, tmp_path, world, LATER)
    assert "OUT+2" not in r.changed
    day = ausrasp.read_day(store_dir(tmp_path), "OUT+2")
    assert day is not None and day["model_start"] == "2026-10-03T00:00:00Z"


def test_a_grid_of_the_wrong_size_is_rejected(site, cfg, tmp_path, world):
    run_refresh(cfg, site, tmp_path, world)
    (store_dir(tmp_path) / "cell.json").write_text(
        json.dumps({**world.cell, "shape": [144, 144], "site_lat": site.lat, "site_lon": site.lon})
    )
    world.stamps["OUT+0"] = "20261003T0900Z"
    r = run_refresh(cfg, site, tmp_path, world, LATER)
    assert any("grid shape" in p for p in r.problems)


# ---- politeness and the off switch


def test_every_request_identifies_the_project_and_the_owner(site, cfg, tmp_path, world):
    run_refresh(cfg, site, tmp_path, world)
    agents = {h["User-Agent"] for _, h in world.requests}
    assert len(agents) == 1
    assert next(iter(agents)).startswith("FreeFlyingForecast/") and "https://example.test" in next(
        iter(agents)
    )


def test_requests_are_spaced_by_at_least_a_second(site, cfg, tmp_path, world):
    sleeps = []
    refresh(cfg, site, tmp_path, world, now=lambda: NOW, sleep=sleeps.append)
    assert len(sleeps) > 40 and all(s > 0 for s in sleeps)


def test_the_off_switch_means_no_requests(site, cfg, tmp_path, world):
    off = dataclasses.replace(cfg, enabled=False)
    r = run_refresh(off, site, tmp_path, world)
    assert world.requests == [] and "turned off" in r.reason
    lookup, notes = thermal_lookup(tmp_path, off, NOW)
    assert lookup == {} and "turned off" in notes[0]


@pytest.mark.parametrize("status", [403, 429, 503])
def test_a_refusal_holds_off_for_six_hours(site, cfg, tmp_path, world, status):
    world.fail["version.json"] = status
    r = run_refresh(cfg, site, tmp_path, world)
    assert f"HTTP {status}" in r.reason
    n = len(world.requests)
    again = run_refresh(cfg, site, tmp_path, world, NOW + timedelta(hours=5))
    assert len(world.requests) == n and "holding off" in again.reason
    world.fail.clear()
    assert run_refresh(cfg, site, tmp_path, world, NOW + timedelta(hours=7)).changed


def test_the_hourly_request_limit_is_respected(site, cfg, tmp_path, world):
    store = store_dir(tmp_path)
    store.mkdir(parents=True)
    (store / "budget.json").write_text(
        json.dumps(
            {
                "day": NOW.date().isoformat(),
                "bytes": 0,
                "requests": [NOW.timestamp() - 60] * ausrasp.REQUESTS_PER_HOUR,
            }
        )
    )
    r = run_refresh(cfg, site, tmp_path, world)
    assert "request limit" in r.reason and world.requests == []


def test_the_daily_transfer_limit_is_respected(site, cfg, tmp_path, world):
    store = store_dir(tmp_path)
    store.mkdir(parents=True)
    (store / "budget.json").write_text(
        json.dumps({"day": NOW.date().isoformat(), "bytes": ausrasp.BYTES_PER_DAY, "requests": []})
    )
    assert "transfer limit" in run_refresh(cfg, site, tmp_path, world).reason


def test_the_first_full_refresh_of_seven_days_stays_within_the_budget(site, cfg, tmp_path, world):
    run_refresh(cfg, site, tmp_path, world)
    budget = json.loads((store_dir(tmp_path) / "budget.json").read_text())
    assert len(budget["requests"]) <= ausrasp.REQUESTS_PER_HOUR
    assert budget["bytes"] < ausrasp.BYTES_PER_DAY


# ---- the lookup


def test_old_runs_are_left_out_with_a_reason(site, cfg, tmp_path, world):
    run_refresh(cfg, site, tmp_path, world)
    lookup, notes = thermal_lookup(tmp_path, cfg, NOW + timedelta(hours=40))
    assert lookup == {} and all("older than 36 hours" in n for n in notes) and len(notes) == 7


def test_status_records_success_days_and_fallback(site, cfg, tmp_path, world):
    run_refresh(cfg, site, tmp_path, world)
    st = ausrasp.read_status(store_dir(tmp_path))
    assert st["fallback"] is None and st["last_success"] and len(st["days"]) == 7
    world.fail["version.json"] = 503
    run_refresh(cfg, site, tmp_path, world, LATER)
    st = ausrasp.read_status(store_dir(tmp_path))
    assert "503" in st["fallback"]["reason"] and st["fallback"]["since"]


def test_nothing_fetched_yet_says_so(cfg, tmp_path):
    lookup, notes = thermal_lookup(tmp_path, cfg, NOW)
    assert lookup == {} and "no AUSRASP data" in notes[0]


def test_the_directory_labelled_for_another_day_is_planned_from_the_file(
    site, cfg, tmp_path, world
):
    """If AUSRASP rolls its days over at a different moment than we assume, the file's own date wins."""
    real = world.date_of
    world.date_of = lambda key: real(key) + timedelta(days=1) if key == "OUT+0" else real(key)  # type: ignore[method-assign]
    r = run_refresh(cfg, site, tmp_path, world)
    assert "OUT+0" in r.changed
    day = ausrasp.read_day(store_dir(tmp_path), "OUT+0")
    assert day is not None
    keys = sorted(day["values"])  # local 10:00 to 18:00 on the 4th (AEDT)
    assert keys[0] == "2026-10-03T23:00:00Z" and keys[-1] == "2026-10-04T07:00:00Z"


# ---- the block of cells around the launch


def test_the_highest_value_in_the_block_around_the_launch_is_used(site, cfg, tmp_path, world):
    world.height = lambda key, hhmm: 1500.0  # the nearest cell, low on the mountain
    world.updraft = lambda key, hhmm: 1.0
    world.around = {(1, 0): (1900.0, 2.0), (-1, -1): (1700.0, 3.0), (0, 1): (1200.0, 0.0)}
    run_refresh(cfg, site, tmp_path, world)
    t = thermal_lookup(tmp_path, cfg, NOW)[0][datetime(2026, 10, 4, 4, tzinfo=UTC)]
    assert (t.height_m, t.updraft_ms) == (1900, 3)  # each quantity takes its own highest cell


def test_a_cell_outside_the_block_is_ignored(site, cfg, tmp_path, world):
    world.around = {(2, 0): (2400.0, 4.0), (0, -2): (2300.0, 4.0)}
    run_refresh(cfg, site, tmp_path, world)
    t = thermal_lookup(tmp_path, cfg, NOW)[0][datetime(2026, 10, 4, 4, tzinfo=UTC)]
    assert (t.height_m, t.updraft_ms) == (1800, 2)


def test_a_radius_of_zero_uses_the_nearest_cell_alone(site, cfg, tmp_path, world):
    world.around = {(1, 0): (1900.0, 4.0)}
    one = dataclasses.replace(cfg, cell_radius=0)
    run_refresh(one, site, tmp_path, world)
    t = thermal_lookup(tmp_path, one, NOW)[0][datetime(2026, 10, 4, 4, tzinfo=UTC)]
    assert (t.height_m, t.updraft_ms) == (1800, 2)


def test_a_larger_radius_reaches_further(site, cfg, tmp_path, world):
    world.around = {(2, 0): (2400.0, 4.0)}
    wide = dataclasses.replace(cfg, cell_radius=2)
    run_refresh(wide, site, tmp_path, world)
    t = thermal_lookup(tmp_path, wide, NOW)[0][datetime(2026, 10, 4, 4, tzinfo=UTC)]
    assert (t.height_m, t.updraft_ms) == (2400, 4)


def test_the_block_is_clipped_at_the_edge_of_the_grid():
    import numpy as np

    v = np.arange(144.0).reshape(12, 12)
    assert ausrasp.block_max(v, 0, 0, 1) == v[1, 1]
    assert ausrasp.block_max(v, 11, 11, 1) == v[11, 11]
    assert ausrasp.block_max(v, 5, 5, 0) == v[5, 5]


def test_changing_the_radius_fetches_the_days_again(site, cfg, tmp_path, world):
    run_refresh(cfg, site, tmp_path, world)
    world.requests.clear()
    wide = dataclasses.replace(cfg, cell_radius=2)
    r = run_refresh(wide, site, tmp_path, world, LATER)
    assert len(r.changed) == 7 and any(p.startswith("OUT+0/") for p, _ in world.requests)
    lookup, notes = thermal_lookup(
        tmp_path, cfg, NOW
    )  # the old setting no longer matches the store
    assert lookup == {} and all("different cell block" in n for n in notes)


def test_the_radius_is_checked_in_the_site_file(site):
    from ffforecast.config import ConfigError, _ausrasp

    assert _ausrasp({"ausrasp": {"cell_radius": 2}}, "x").cell_radius == 2
    assert _ausrasp({"ausrasp": {}}, "x").cell_radius == 1
    for bad in (-1, 4):
        with pytest.raises(ConfigError, match="cell_radius"):
            _ausrasp({"ausrasp": {"cell_radius": bad}}, "x")


# ---- AUSRASP's clock: standard or daylight time depending on when the run was made


def aed_text(**kw):
    """15:00 AEDT on the 4th is 04:00Z; AUSRASP labels it '1500 AED'."""
    t = datetime(2026, 10, 4, 4, tzinfo=UTC)
    return grid_text("hglider", t, t - timedelta(hours=16), 100, (3, 4, 1700.0), offset=11)


def test_a_daylight_time_file_is_read_by_its_own_clock():
    g = parse_grid(aed_text(), "hglider", (12, 12))
    assert g.valid_utc == datetime(
        2026, 10, 4, 4, tzinfo=UTC
    )  # not 05:00Z, as an AES reading gives
    assert g.offset_h == 11 and g.run == datetime(2026, 10, 3, 12, tzinfo=UTC)


def test_a_standard_time_file_is_still_read_as_ten_hours():
    assert parse_grid(valid_text(), "hglider", (12, 12)).offset_h == 10


def test_an_impossible_clock_is_rejected():
    bad = aed_text().replace("ValidZ= 400", "ValidZ= 600")
    with pytest.raises(AusraspError, match="clock offset"):
        parse_grid(bad, "hglider", (12, 12))


AFTER_DST = datetime(2026, 10, 3, 21, 0, tzinfo=UTC)  # 08:00 AEDT on the 4th


def test_runs_made_after_daylight_saving_began_are_asked_for_by_the_daylight_clock(
    site, cfg, tmp_path, world
):
    world.now = AFTER_DST
    world.stamps = {k: "20261003T1700Z" for k in world.stamps}  # made after 16:00Z: AED labels
    world.runs = {k: AFTER_DST.replace(hour=12, minute=0) - timedelta(days=1) for k in world.runs}
    r = run_refresh(cfg, site, tmp_path, world, AFTER_DST)
    assert "OUT+0" in r.changed
    asked = {p.split("curr.")[1][:4] for p, _ in world.requests if p.startswith("OUT+0/FCST/")}
    assert asked == {
        f"{h:02d}00" for h in range(10, 19)
    }  # the page's local hours, on the AED clock
    day = ausrasp.read_day(store_dir(tmp_path), "OUT+0")
    assert day is not None
    assert sorted(day["values"]) == EXPECTED_4TH  # 10:00 to 18:00 AEDT


def test_runs_made_before_it_are_asked_for_by_the_standard_clock(site, cfg, tmp_path, world):
    world.now = AFTER_DST
    world.stamps = {k: "20261003T0453Z" for k in world.stamps}  # AES labels, for the same 4th
    world.runs = {k: AFTER_DST.replace(hour=0, minute=0) - timedelta(hours=24) for k in world.runs}
    run_refresh(cfg, site, tmp_path, world, AFTER_DST)
    asked = {p.split("curr.")[1][:4] for p, _ in world.requests if p.startswith("OUT+0/FCST/")}
    assert asked == {f"{h:02d}00" for h in range(9, 18)}  # the same instants, labelled in AES
    day = ausrasp.read_day(store_dir(tmp_path), "OUT+0")
    assert day is not None
    assert sorted(day["values"]) == EXPECTED_4TH


def test_both_clocks_give_the_same_valid_times(site, cfg, tmp_path, world):
    """The 4th's blocks are 00, 02, 04 and 06Z whichever clock the run was labelled in."""
    got = {}
    for label, stamp in (("aes", "20261003T0453Z"), ("aed", "20261003T1700Z")):
        w = World(AFTER_DST, site.lat, site.lon)
        w.stamps = {k: stamp for k in w.stamps}
        w.runs = {k: AFTER_DST.replace(hour=0, minute=0) - timedelta(hours=12) for k in w.runs}
        d = tmp_path / label
        run_refresh(cfg, site, d, w, AFTER_DST)
        day = ausrasp.read_day(store_dir(d), "OUT+0")
        assert day is not None
        got[label] = sorted(day["values"])
    assert got["aes"] == got["aed"]


def test_a_wrong_guess_of_the_clock_is_corrected_from_the_file(site, cfg, tmp_path, world):
    world.now = AFTER_DST
    world.stamps["OUT+0"] = "20261003T0453Z"  # looks like standard time...
    world.clock["OUT+0"] = 11  # ...but the files are labelled in daylight time
    world.runs = {k: AFTER_DST.replace(hour=0, minute=0) - timedelta(hours=12) for k in world.runs}
    r = run_refresh(cfg, site, tmp_path, world, AFTER_DST)
    assert "OUT+0" in r.changed
    day = ausrasp.read_day(store_dir(tmp_path), "OUT+0")
    assert day is not None and sorted(day["values"]) == EXPECTED_4TH


def test_days_stored_by_an_older_reading_of_the_clock_are_not_trusted(site, cfg, tmp_path, world):
    run_refresh(cfg, site, tmp_path, world)
    path = ausrasp.day_path(store_dir(tmp_path), "OUT+2")
    old = json.loads(path.read_text())
    del old["format"]  # how the first version wrote them
    path.write_text(json.dumps(old))
    assert ausrasp.read_day(store_dir(tmp_path), "OUT+2") is None
    lookup, _ = thermal_lookup(tmp_path, cfg, NOW)
    assert datetime(2026, 10, 5, 4, tzinfo=UTC) not in lookup
    world.requests.clear()
    r = run_refresh(cfg, site, tmp_path, world, LATER)
    assert r.changed == ["OUT+2"]  # fetched again although its stamp did not change
