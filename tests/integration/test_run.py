from ffforecast.pipeline import EXIT_FAILED, EXIT_NO_DATA, EXIT_OK, Stage, run_pipeline
from ffforecast.state import State


def make_stage(name, text=None, fail=False):
    def fn(staging):
        if fail:
            raise RuntimeError("boom")
        (staging / "index.html").write_text(text or name)

    return Stage(name, fn)


def setup(tmp_path, old="OLD PAGE"):
    pub = tmp_path / "out"
    pub.mkdir()
    (pub / "index.html").write_text(old)
    return State(tmp_path / "state"), pub, tmp_path / "work"


def nosleep(_: float) -> None:
    return None


def go(tmp_path, stages, finder=lambda: "c2", retries=6):
    st, pub, work = setup(tmp_path)
    code, rec = run_pipeline(finder, stages, st, pub, work, retries=retries, sleep=nosleep)
    return code, rec, st, pub


def test_success_publishes_and_records(tmp_path):
    code, rec, st, pub = go(tmp_path, [make_stage("render", "NEW")])
    assert code == EXIT_OK and rec.outcome == "published"
    assert (pub / "index.html").read_text() == "NEW"
    assert st.last_published_cycle() == "c2"


def test_failed_stage_keeps_last_ok_page(tmp_path):
    code, rec, st, pub = go(tmp_path, [make_stage("a"), make_stage("wrf", fail=True)])
    assert code == EXIT_FAILED and rec.failed_stage == "wrf"
    assert (pub / "index.html").read_text() == "OLD PAGE"
    assert st.last_published_cycle() is None


def test_late_data_retries_then_gives_up(tmp_path):
    calls = []
    code, rec, _, pub = go(tmp_path, [make_stage("a")], finder=lambda: calls.append(1), retries=3)
    assert code == EXIT_NO_DATA and rec.outcome == "no_data"
    assert len(calls) == 4  # first try plus 3 retries
    assert (pub / "index.html").read_text() == "OLD PAGE"


def test_late_data_arrives_on_retry(tmp_path):
    answers = iter([None, None, "c9"])
    code, rec, *_ = go(tmp_path, [make_stage("a")], finder=lambda: next(answers), retries=3)
    assert code == EXIT_OK and rec.cycle == "c9"


def test_duplicate_cycle_skipped_then_forced(tmp_path):
    st, pub, work = setup(tmp_path)
    run_pipeline(lambda: "c2", [make_stage("a", "NEW")], st, pub, work, sleep=nosleep)
    code, rec = run_pipeline(lambda: "c2", [make_stage("a", "NEWER")], st, pub, work, sleep=nosleep)
    assert code == EXIT_OK and rec.outcome == "skipped_duplicate"
    assert (pub / "index.html").read_text() == "NEW"
    run_pipeline(lambda: "c2", [make_stage("a", "NEWER")], st, pub, work, force=True, sleep=nosleep)
    assert (pub / "index.html").read_text() == "NEWER"
