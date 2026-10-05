import json

from ffforecast.models import SCHEMA_VERSION, Forecast


def test_a_schema_1_forecast_reads_with_the_new_grade_names(fixture_path):
    d = json.loads(fixture_path.read_text())
    d["schema"] = 1
    for b in d["blocks"]:
        b["verdict_pg"] = {"ok": "good", "good": "great", "strong": "pumping"}.get(
            b["verdict_pg"], b["verdict_pg"]
        )
    for o in d["outlook"]:
        o["verdict"] = {"ok": "good", "good": "great", "strong": "pumping"}.get(
            o["verdict"], o["verdict"]
        )
    fc = Forecast.from_dict(d)
    assert fc.schema == SCHEMA_VERSION
    assert {b.verdict_pg for b in fc.blocks} <= {
        "ok",
        "good",
        "strong",
        "poor",
        "bad",
    }


def test_a_current_forecast_is_left_alone(fixture_path):
    d = json.loads(fixture_path.read_text())
    assert d["schema"] == SCHEMA_VERSION
    assert Forecast.from_dict(d).to_dict() == d


def test_the_old_names_become_the_new_ones():
    d = {
        "site": "x", "model": "m", "cycle": "c", "generated_at": "g", "rules_version": 1,
        "blocks": [], "outlook": [], "schema": 1,
    }  # fmt: skip
    from ffforecast.models import _modernise

    d["outlook"] = [
        {"date": "2026-10-08", "wind": {"dir_deg": 0, "kph": 5}, "verdict": v, "verdict_hg": v}
        for v in ("good", "great", "pumping", "poor")
    ]
    out = _modernise(d)["outlook"]
    assert [o["verdict"] for o in out] == ["ok", "good", "strong", "poor"]


def test_the_old_turbulent_and_dangerous_both_read_as_bad(fixture_path):
    d = json.loads(fixture_path.read_text())
    d["schema"] = 3
    d["blocks"][0]["verdict_pg"] = "turbulent"
    d["blocks"][1]["verdict_pg"] = "dangerous"
    d["blocks"][1]["verdict_hg"] = "dangerous"
    d["outlook"][0]["verdict"] = "dangerous"
    fc = Forecast.from_dict(d)
    assert fc.schema == SCHEMA_VERSION
    assert (fc.blocks[0].verdict_pg, fc.blocks[1].verdict_pg, fc.blocks[1].verdict_hg) == (
        "bad",
        "bad",
        "bad",
    )
    assert fc.outlook[0].verdict == "bad"


def test_a_schema_3_good_is_still_good(fixture_path):
    """Only schema 1 used Good for what is now Ok: a newer file's Good must not be moved down."""
    d = json.loads(fixture_path.read_text())
    d["schema"] = 3
    d["blocks"][0]["verdict_pg"] = "good"
    assert Forecast.from_dict(d).blocks[0].verdict_pg == "good"
