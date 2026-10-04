from pathlib import Path

import pytest

from ffforecast.config import ConfigError, load_rules, load_site


def test_loads_real_files(rules, site):
    assert rules.version == 2
    assert rules.speed_orange_from_mph == 12 and rules.speed_red_from_mph == 14
    assert rules.sector_center_deg == 0 and rules.sector_half_width_deg == 40
    assert site.lat == pytest.approx(-36.7584099)
    assert "freeflightwx" in site.links["gauge"]


def write(tmp_path: Path, text: str) -> Path:
    p = tmp_path / "r.toml"
    p.write_text(text)
    return p


OK = Path(__file__).resolve().parents[2].joinpath("config/rules.toml").read_text()


def test_empty_source_rejected(tmp_path):
    bad = OK.replace(OK.split("\n")[1], 'source = "  "')
    with pytest.raises(ConfigError, match="source"):
        load_rules(write(tmp_path, bad))


def test_unit_suffix_required(tmp_path):
    bad = OK.replace("speed_green_from_mph", "speed_green_from")
    with pytest.raises(ConfigError):
        load_rules(write(tmp_path, bad))


def test_band_order_enforced(tmp_path):
    bad = OK.replace("speed_red_from_mph = 14", "speed_red_from_mph = 5")
    with pytest.raises(ConfigError, match="bands"):
        load_rules(write(tmp_path, bad))


def test_missing_file(tmp_path):
    with pytest.raises(ConfigError):
        load_site(tmp_path / "nope.toml")


def test_thermal_calibration_loaded(rules):
    assert rules.critical_updraft_ms == pytest.approx(1.143)
    assert rules.usable_depth_fraction == 0.48
    assert rules.quality_full_updraft_ms == 1.6
    assert rules.quality_wind_threshold_kph == 12 and rules.quality_wind_penalty_per_kph == 2.5
    assert rules.thermal_min_height_m == 900


@pytest.mark.parametrize(
    "old,new,match",
    [
        ("critical_updraft_ms = 1.143", "critical_updraft_ms = 0", "critical_updraft"),
        ("usable_depth_fraction = 0.48", "usable_depth_fraction = 1.5", "usable_depth"),
        ("quality_full_updraft_ms = 1.6", "quality_full_updraft_ms = 0", "quality_full"),
        ("quality_wind_penalty_per_kph = 2.5", "quality_wind_penalty_per_kph = -1", "penalty"),
    ],
)
def test_bad_thermal_calibration_is_rejected(tmp_path, old, new, match):
    text = Path(__file__).resolve().parents[2].joinpath("config/rules.toml").read_text()
    assert old in text
    p = tmp_path / "r.toml"
    p.write_text(text.replace(old, new))
    with pytest.raises(ConfigError, match=match):
        load_rules(p)


def test_old_rules_without_the_calibration_still_load(tmp_path):
    text = Path(__file__).resolve().parents[2].joinpath("config/rules.toml").read_text()
    text = "\n".join(
        line
        for line in text.splitlines()
        if not line.startswith(("critical_updraft", "usable_depth", "quality_"))
    )
    p = tmp_path / "r.toml"
    p.write_text(text)
    r = load_rules(p)
    assert r.critical_updraft_ms == pytest.approx(1.143) and r.quality_full_updraft_ms == 1.6


def test_tier_thresholds_loaded(rules):
    assert rules.thermal_ok_quality_pct == 40 and rules.thermal_good_quality_pct == 70
    assert rules.thermal_good_updraft_ms == 2.5 and rules.thermal_strong_updraft_ms == 3.5
    assert rules.strong_wind_from_mph == 9 and rules.hg_strong_wind_from_mph == 11


@pytest.mark.parametrize(
    "old,new,match",
    [
        ("good_quality_pct = 70", "good_quality_pct = 30", "good_quality_pct"),
        ("good_quality_pct = 70", "good_quality_pct = 120", "good_quality_pct"),
        ("good_updraft_ms = 2.5", "good_updraft_ms = 4.0", "good_updraft_ms"),
        ("strong_updraft_ms = 3.5", "strong_updraft_ms = 1.0", "strong_updraft_ms"),
        ("\nstrong_wind_from_mph = 9", "\nstrong_wind_from_mph = 13", "strong_wind_from_mph"),
        ("hg_strong_wind_from_mph = 11", "hg_strong_wind_from_mph = 15", "hg_strong_wind"),
    ],
)
def test_tier_thresholds_must_be_in_a_sensible_order(tmp_path, old, new, match):
    text = Path(__file__).resolve().parents[2].joinpath("config/rules.toml").read_text()
    assert old in text
    p = tmp_path / "r.toml"
    p.write_text(text.replace(old, new, 1))
    with pytest.raises(ConfigError, match=match):
        load_rules(p)


def test_rules_without_the_tier_thresholds_use_the_defaults(tmp_path):
    text = Path(__file__).resolve().parents[2].joinpath("config/rules.toml").read_text()
    text = "\n".join(
        line
        for line in text.splitlines()
        if not line.startswith(("good_", "strong_updraft", "strong_wind", "hg_strong_"))
    )
    p = tmp_path / "r.toml"
    p.write_text(text)
    r = load_rules(p)
    assert r.thermal_good_quality_pct == 70 and r.thermal_strong_updraft_ms == 3.5


SITE = Path(__file__).resolve().parents[2].joinpath("config/site.mystic.toml")


def test_project_and_contact_come_from_the_environment(monkeypatch):
    monkeypatch.delenv("FFFORECAST_PROJECT", raising=False)
    monkeypatch.delenv("FFFORECAST_CONTACT", raising=False)
    plain = load_site(SITE)
    assert "github" not in plain.links and plain.ausrasp.contact == ""

    monkeypatch.setenv("FFFORECAST_PROJECT", "https://github.com/example/project")
    monkeypatch.setenv("FFFORECAST_CONTACT", " me@example.test ")
    site = load_site(SITE)
    assert site.links["github"] == "https://github.com/example/project"
    assert site.ausrasp.contact == "me@example.test"
