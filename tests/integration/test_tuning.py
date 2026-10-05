import dataclasses
from datetime import datetime, timedelta, timezone

from ffforecast.diagnostics import build_block
from ffforecast.models import Forecast, Wind
from ffforecast.render import render_page


def forecast_with(rules):
    tz = timezone(timedelta(hours=11))
    block = build_block(
        datetime(2026, 10, 4, 11, tzinfo=tz), Wind(350, 12), Wind(10, 14), 1500, 380, 16, 785, rules
    )
    return Forecast("mystic", "m", "c", "2026-10-03T14:00:00+11:00", rules.version, [block], [])


def test_changing_rules_changes_verdict_and_legend(site, rules):
    before = render_page(forecast_with(rules), site, rules)
    assert 'g g-pg good"' in before and '<span class="u s-kph">19 kph</span>' in before
    tuned = dataclasses.replace(rules, speed_orange_from_mph=8, version=2)
    after = render_page(forecast_with(tuned), site, tuned)
    assert 'g g-pg bad"' in after
    assert '<span class="u s-kph">13 kph</span>' in after
    assert "Rules version" not in after
