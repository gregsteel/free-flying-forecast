import json
import re

from ffforecast.models import DETAILED_DAYS, OUTLOOK_DAYS, Forecast
from ffforecast.render import render_page


def page(fixture_path, site, rules):
    return render_page(Forecast.from_dict(json.loads(fixture_path.read_text())), site, rules)


def summary_of(row):
    m = re.search(r"<summary>(.*?)</summary>", row, flags=re.S)
    assert m is not None
    return m.group(1)


def days(html):
    return re.findall(r'<details class="day"[^>]*>.*?</details>', html, flags=re.S)


def test_one_expandable_row_per_day_first_open(fixture_path, site, rules):
    rows = days(page(fixture_path, site, rules))
    assert len(rows) == DETAILED_DAYS == 4
    assert rows[0].startswith('<details class="day" open>')
    assert all(r.startswith('<details class="day">') for r in rows[1:])


def test_row_header_has_nine_hourly_columns_from_ten_to_six(fixture_path, site, rules):
    row = days(page(fixture_path, site, rules))[0]
    summary = summary_of(row)
    assert summary.count('class="cell ') == 9
    assert re.findall(r'<span class="ctime">(\d+)</span>', summary) == [
        str(h % 12 or 12) for h in range(10, 19)  # 12-hour clock: 10, 11, 12, 1, 2 ... 6
    ]


def test_collapsed_header_shows_only_grade_and_thermal_height(fixture_path, site, rules):
    row = days(page(fixture_path, site, rules))[0]
    summary = summary_of(row)
    assert "cicon" in summary and "cht" in summary  # grade icon and thermal height
    first = json.loads(fixture_path.read_text())["blocks"][0]["thermal_height_m"]
    rounded = int(first // 100 * 100)  # heights are shown rounded down to 100 m
    assert (
        f'<span class="u a-m">{rounded}</span>' in summary
    )  # the first hour's height, from the data
    for detail in ("Ground wind", "Gusts", "Rain", "Thermal quality"):
        assert detail not in summary
        assert detail in row  # but they are in the expandable part


def visible_text(html: str) -> str:
    """Header text a sighted user sees: drop screen-reader-only spans and all tags."""
    no_sr = re.sub(r'<span class="sr">.*?</span>', "", html, flags=re.S)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", no_sr))


def test_header_shows_only_the_grade_icon(fixture_path, site, rules):
    row = days(page(fixture_path, site, rules))[0]
    summary = summary_of(row)
    assert summary.count('class="cicon g g-pg"') == 9 and summary.count('class="cicon g g-hg"') == 9
    text = visible_text(summary)
    for word in ("PG", "HG", "Good", "Poor", "Turbulent", "Dangerous"):
        assert word not in text  # no label and no grade word on screen
    # both gliders, labelled, are in the expanded view
    assert len(re.findall(r'class="pill g g-pg ', row)) == 9  # a pill per glider; CSS shows one
    assert len(re.findall(r'class="pill g g-hg ', row)) == 9
    assert "PG: " not in row and "HG: " not in row  # just the grade, no prefix


def test_header_icon_still_has_the_grade_as_text_for_screen_readers(fixture_path, site, rules):
    summary = summary_of(days(page(fixture_path, site, rules))[0])
    for word in ("Good", "Poor", "Turbulent", "Dangerous"):
        assert f"Paraglider: {word}" in summary  # hidden text and tooltip
    assert 'title="Paraglider: ' in summary


def test_missing_block_keeps_columns_aligned(site, rules, fixture_path):
    fc = Forecast.from_dict(json.loads(fixture_path.read_text()))
    fc.blocks = [b for b in fc.blocks if not b.start.startswith("2026-10-04T11")]  # drop one hour
    html = render_page(fc, site, rules)
    row = days(html)[0]
    summary = summary_of(row)
    assert summary.count('class="cell ') == 9 and 'class="cell empty"' in summary


def test_outlook_columns_match_the_number_of_outlook_days(fixture_path, site, rules):
    html = page(fixture_path, site, rules)
    assert OUTLOOK_DAYS == 3  # days 5 to 7
    assert 'class="outlook"' in html
    assert f"grid-template-columns:repeat({OUTLOOK_DAYS},minmax(0,1fr))" in html
    assert html.count('<table class="dt">') == DETAILED_DAYS  # one details table per day
    outlook = html[html.index('<div class="outlook">') : html.index('<details class="guide"')]
    assert outlook.count('<section class="cell ') == OUTLOOK_DAYS


def test_headings_say_which_days_are_detailed_and_which_are_outlook(fixture_path, site, rules):
    html = page(fixture_path, site, rules)
    assert "<h2>Next 4 days</h2>" in html
    assert "<h2>Days 5 to 7 outlook</h2>" in html
    assert "Next 3 days" not in html and "Days 4 to 7" not in html


def test_a_narrow_screen_shows_every_other_hour(fixture_path, site, rules):
    html = page(fixture_path, site, rules)
    narrow = html[html.index("@media (max-width:44rem){") :]
    narrow = narrow[: narrow.index("@media (min-width:44rem)")]
    # five columns instead of nine, and the odd hours (11, 13, 15, 17) are the ones dropped
    assert "details.day>summary{grid-template-columns:var(--lw) repeat(5,minmax(0,1fr))}" in narrow
    assert "details.day>summary>.cell:nth-child(2n+3){display:none}" in narrow
    assert "table.dt tr>:nth-child(2n+3),table.dt col:nth-child(2n+3){display:none}" in narrow
    assert ".whygrid>.why:nth-child(even){display:none}" in narrow
    assert "table.dt{min-width:0}" in narrow  # five columns need no sideways scrolling
    # wide screens are not affected: nothing hides hours outside that query
    assert "nth-child(2n+3){display:none}" not in html.replace(narrow, "")


def test_the_hours_that_stay_are_ten_twelve_fourteen_sixteen_and_eighteen(
    fixture_path, site, rules
):
    """The CSS hides child 3, 5, 7 and 9 of the row (child 1 is the day label or row heading)."""
    row = days(page(fixture_path, site, rules))[0]
    summary = summary_of(row)
    hours = re.findall(r'<span class="ctime">(\d+)</span>', summary)
    assert hours == [str(h % 12 or 12) for h in range(10, 19)]
    children = [hours[i] for i in range(9)]  # the cells are children 2 to 10 of the summary
    hidden = [children[c - 2] for c in (3, 5, 7, 9)]
    assert hidden == ["11", "1", "3", "5"]  # 11:00, 13:00, 15:00 and 17:00
    assert [children[i] for i in (0, 2, 4, 6, 8)] == ["10", "12", "2", "4", "6"]
