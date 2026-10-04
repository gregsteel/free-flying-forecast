from pathlib import Path

import pytest

from ffforecast.config import load_rules, load_site

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def rules():
    return load_rules(ROOT / "config/rules.toml")


@pytest.fixture
def site():
    return load_site(ROOT / "config/site.mystic.toml")


@pytest.fixture
def fixture_path():
    return ROOT / "tests/fixtures/forecast.json"
