from ffforecast.state import RunRecord, State


def test_duplicate_detection(tmp_path):
    s = State(tmp_path)
    assert not s.is_duplicate("c1")
    s.record(RunRecord(cycle="c1", started_at="t", finished_at="t", outcome="published"))
    assert s.is_duplicate("c1") and not s.is_duplicate("c2")


def test_failed_run_does_not_change_last_published(tmp_path):
    s = State(tmp_path)
    s.record(RunRecord(cycle="c1", started_at="t", outcome="published"))
    s.record(RunRecord(cycle="c2", started_at="t", outcome="failed", failed_stage="wrf"))
    assert s.last_published_cycle() == "c1"
    assert len(s.log_path.read_text().splitlines()) == 2


def test_prune_keeps_newest(tmp_path):
    runs = tmp_path / "runs"
    for n in range(6):
        (runs / f"2026100{n}").mkdir(parents=True)
    removed = State(tmp_path).prune_runs(runs, keep=4)
    assert len(removed) == 2 and sorted(p.name for p in runs.iterdir())[0] == "20261002"


def test_prune_gfs_cache_keeps_two_newest_cycles(tmp_path):
    cache = tmp_path / "cache" / "gfs"
    for label in ("2026-10-02T12Z", "2026-10-02T18Z", "2026-10-03T00Z", "2026-10-03T06Z"):
        (cache / label).mkdir(parents=True)
        (cache / label / "f006.grib2").write_text("x")
    State(tmp_path).prune_runs(cache, keep=2)
    assert sorted(p.name for p in cache.iterdir()) == ["2026-10-03T00Z", "2026-10-03T06Z"]
