import json
import re

from ffforecast.models import Forecast
from ffforecast.render import render_page

GRADES = ("ok", "good", "strong", "poor", "turbulent", "dangerous")


def load(fixture_path):
    return json.loads(fixture_path.read_text())


def page(fixture_path, site, rules, mutate=None):
    d = load(fixture_path)
    if mutate:
        mutate(d)
    return render_page(Forecast.from_dict(d), site, rules)


def days(html):
    return re.findall(r'<details class="day"[^>]*>.*?</details>', html, flags=re.S)


def test_glider_toggle_is_in_the_header_left_of_the_hamburger(fixture_path, site, rules):
    html = page(fixture_path, site, rules)
    bar = html[html.index('<header class="bar">') : html.index("</header>")]
    assert '<input type="radio" name="gl" id="gl-pg" checked>' in bar  # PG is the default
    assert '<input type="radio" name="gl" id="gl-hg">' in bar
    assert bar.index('id="gl-hg"') < bar.index('<details class="menu"')  # left of the hamburger
    assert '<legend class="sr">Glider type</legend>' in bar
    assert 'title="Paraglider">PG</label>' in bar and 'title="Hang glider">HG</label>' in bar
    # not in the menu: it is always visible
    menu = html[
        html.index('<details class="menu"') : html.index(
            "</details>", html.index('<details class="menu"')
        )
    ]
    assert "gl-pg" not in menu and "gl-hg" not in menu


def test_only_the_chosen_glider_is_shown_by_css(fixture_path, site, rules):
    html = page(fixture_path, site, rules)
    assert "body:has(#gl-hg:checked) .g-pg{display:none}" in html
    assert "body:not(:has(#gl-hg:checked)) .g-hg{display:none}" in html  # PG is the default


def test_every_header_cell_has_a_labelled_icon_for_each_glider(fixture_path, site, rules):
    row = days(page(fixture_path, site, rules))[0]
    summary = re.search(r"<summary>(.*?)</summary>", row, flags=re.S)
    assert summary is not None
    s = summary.group(1)
    assert (
        len(re.findall(r'class="cicon g g-pg"', s)) == 9
        and len(re.findall(r'class="cicon g g-hg"', s)) == 9
    )
    assert 'aria-label="Paraglider: ' in s and 'aria-label="Hang glider: ' in s


def test_expanded_view_has_one_pill_and_reasons_per_glider(fixture_path, site, rules):
    row = days(page(fixture_path, site, rules))[0]
    assert row.count("g g-pg ") >= 9 and row.count("g g-hg ") >= 9
    assert len(re.findall(r'<ul class="reasons g g-pg">', row)) == 9
    assert len(re.findall(r'<ul class="reasons g g-hg">', row)) == 9
    assert "PG: " not in row and "HG: " not in row  # the pill is just the grade


def test_a_block_graded_differently_for_each_glider(fixture_path, site, rules):
    # the fixture's third slot is 20 kph: orange for paragliders; for hang gliders it is a brisk but
    # green wind with strong thermals, so powerful: Strong
    html = page(fixture_path, site, rules)
    assert (
        '<th scope="col" class="pg-turbulent hg-strong">' in html
    )  # the column carries both grades
    cells = re.findall(r'<div class="why">(.*?)</div>', html, flags=re.S)
    mine = [c for c in cells if "novice pilots" in c]
    assert mine, "the paraglider reasons should mention the novice limit"
    for c in mine:
        pg = re.search(r'<ul class="reasons g g-pg">(.*?)</ul>', c, flags=re.S)
        hg = re.search(r'<ul class="reasons g g-hg">(.*?)</ul>', c, flags=re.S)
        assert pg is not None and hg is not None
        assert "novice pilots" in pg.group(1)  # the paraglider limit
        assert "novice pilots" not in hg.group(1)  # does not apply to hang gliders
    col = re.search(r'<th scope="col" class="pg-turbulent hg-strong">(.*?)</th>', html, flags=re.S)
    assert col is not None
    assert re.search(r'g g-pg turbulent"[^>]*>.*?Turbulent</a>', col.group(1), flags=re.S)
    assert re.search(r'g g-hg strong"[^>]*>.*?Strong</a>', col.group(1), flags=re.S)


def test_colours_follow_the_chosen_glider(fixture_path, site, rules):
    html = page(fixture_path, site, rules)
    assert (
        ".cell{border-top-color:var(--pgc,transparent);background:var(--pgb,transparent)}" in html
    )
    assert "body:has(#gl-hg:checked) .cell{border-top-color:var(--hgc,transparent)" in html
    assert (
        "body:has(#gl-hg:checked) table.dt thead th{border-top-color:var(--hgc,transparent)" in html
    )
    assert 'class="cell pg-turbulent hg-good"' in html  # both grades are carried by the cell


def test_outlook_shows_the_chosen_gliders_grade(fixture_path, site, rules):
    html = page(fixture_path, site, rules)
    out = html[html.index('<div class="outlook">') : html.index('<details class="guide"')]
    # the middle day is Turbulent for paragliders and Good for hang gliders
    cell = re.search(r'<section class="cell pg-turbulent hg-good">.*?</section>', out, flags=re.S)
    assert cell is not None
    assert 'class="cicon g g-pg"' in cell.group(0) and "Paraglider: Turbulent" in cell.group(0)
    assert 'class="cicon g g-hg"' in cell.group(0) and "Hang glider: Good" in cell.group(0)


def test_guide_has_the_right_wind_limits_for_each_glider(fixture_path, site, rules):
    html = page(fixture_path, site, rules)
    pg = re.search(r'<ul class="guide g g-pg">(.*?)</ul>', html, flags=re.S)
    hg = re.search(r'<ul class="guide g g-hg">(.*?)</ul>', html, flags=re.S)
    assert pg is not None and hg is not None
    assert '<span class="u s-kph">19 kph</span>' in pg.group(1)  # 12 mph: paraglider orange
    assert '<span class="u s-kph">23 kph</span>' in pg.group(1)  # 14 mph: paraglider red
    assert '<span class="u s-kph">23 kph</span>' in hg.group(1)  # 14 mph: hang glider orange
    assert '<span class="u s-kph">32 kph</span>' in hg.group(1)  # 20 mph: hang glider red
    assert '<span class="u s-kph">19 kph</span>' not in hg.group(
        1
    )  # no paraglider limits in the HG text


def test_guide_anchors_are_unique_and_per_glider(fixture_path, site, rules):
    html = page(fixture_path, site, rules)
    ids = re.findall(r'<li id="(guide-[a-z-]+)"', html)
    assert sorted(ids) == sorted([f"guide-{g}" for g in GRADES] + [f"guide-hg-{g}" for g in GRADES])
    assert len(ids) == len(set(ids))
    hrefs = set(re.findall(r'href="#(guide-[a-z-]+)"', html))
    assert hrefs <= set(ids)  # every grade link goes somewhere


def test_guide_says_whose_limits_it_shows_and_no_longer_lists_both(fixture_path, site, rules):
    html = page(fixture_path, site, rules)
    assert (
        'The limits below are for <span class="g g-pg">paragliders</span><span class="g g-hg">hang gliders</span>'
        in html
    )
    assert "<strong>Hang gliders</strong> use higher wind limits" not in html
    assert "see both PG and hang glider" not in html and "open a day to see both" not in html


def test_script_picks_the_chosen_glider_and_understands_hg_links(fixture_path, site, rules):
    html = page(fixture_path, site, rules)
    assert "function chosenGlider()" in html and 'gl==="hg"?"hg-":""' in html
    assert "#guide-(hg-)?(ok|good|strong|poor|turbulent|dangerous)" in html


def test_address_keeps_the_glider_when_a_grade_is_clicked(fixture_path, site, rules):
    html = page(fixture_path, site, rules)
    assert (
        'history.replaceState(null,"",a.getAttribute("href"))' in html
    )  # not rebuilt from the grade
    assert 'replaceState(null,"","#guide-"+' not in html


def test_older_forecasts_without_hang_glider_data_still_render(fixture_path, site, rules):
    def strip(d):
        for b in d["blocks"]:
            b.pop("reasons_hg", None)
        for o in d["outlook"]:
            o.pop("verdict_hg", None)

    html = page(fixture_path, site, rules, strip)
    assert 'class="reasons g g-hg"' in html  # falls back to the paraglider reasons
    assert "<summary>" in html
