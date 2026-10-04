"""The page says where thermal figures come from and states the rules for that source."""

import json
import re

from ffforecast.models import Forecast
from ffforecast.render import render_page

RUN = "2026-10-02T12:00:00Z"  # 22:00 AEST on the 2nd


def page(fixture_path, site, rules, mutate=None):
    d = json.loads(fixture_path.read_text())
    if mutate:
        mutate(d)
    return render_page(Forecast.from_dict(d), site, rules)


def all_ausrasp(d):
    for b in d["blocks"]:
        b.update(thermal_source="ausrasp", thermal_run=RUN, updraft_ms=3.0)


def some_ausrasp(d):
    for n, b in enumerate(d["blocks"]):
        if n % 2 == 0:
            b.update(thermal_source="ausrasp", thermal_run=RUN, updraft_ms=2.0)


def text(h):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", h))


def guide(html, glider="pg"):
    m = re.search(rf'<ul class="guide g g-{glider}">(.*?)</ul>', html, flags=re.S)
    assert m is not None
    return text(m.group(1))


def header(html):
    start = html.index('<div class="sticky" id="sticky">')
    return text(html[start : html.index('<div class="top">')])


def test_the_header_names_the_thermal_source_and_the_run(fixture_path, site, rules):
    h = header(page(fixture_path, site, rules, all_ausrasp))
    assert "Updated " in h and "Model: " in h and ", run " in h
    assert "Thermals: AUSRASP, run Fri 2 Oct 22:00 AEST." in h
    assert "estimate" not in h


def test_the_header_says_estimate_when_there_is_no_ausrasp(fixture_path, site, rules):
    h = header(page(fixture_path, site, rules))
    assert "Thermals: estimate from the global model." in h


def test_a_mixed_page_names_the_days_that_use_the_estimate(fixture_path, site, rules):
    def mixed(d):
        for b in d["blocks"]:
            if b["start"][:10] != d["blocks"][0]["start"][:10]:  # every day but the first
                continue
            b.update(thermal_source="ausrasp", thermal_run=RUN, updraft_ms=2.0)

    h = header(page(fixture_path, site, rules, mixed))
    assert "Thermals: AUSRASP, run Fri 2 Oct 22:00 AEST; estimate from the global model for " in h
    assert re.search(r"for [A-Z][a-z]{2}(, [A-Z][a-z]{2})+\.", h)  # the days, e.g. "Sun, Mon, Tue."


def test_several_runs_are_all_named(fixture_path, site, rules):
    def two(d):
        for n, b in enumerate(d["blocks"]):
            run = RUN if n % 2 else "2026-10-03T00:00:00Z"
            b.update(thermal_source="ausrasp", thermal_run=run, updraft_ms=2.0)

    h = header(page(fixture_path, site, rules, two))
    assert "AUSRASP, runs Fri 2 Oct 22:00 AEST, Sat 3 Oct 10:00 AEST." in h


def test_the_detail_table_has_no_per_block_source_row(fixture_path, site, rules):
    assert "Thermal figures from" not in page(fixture_path, site, rules, all_ausrasp)


def test_ausrasp_updraft_is_shown_as_a_whole_number_of_m_per_s(fixture_path, site, rules):
    html = page(fixture_path, site, rules, all_ausrasp)
    row = re.search(r'<th scope="row">Updraft .*?</th>(.*?)</tr>', html, flags=re.S)
    assert row is not None
    assert '<span class="u a-m">3</span>' in row.group(1)  # the unit is in the row label
    assert '<span class="u a-ft">9.8</span>' in row.group(1)  # ft/sec to one decimal
    assert "3.0" not in row.group(1)


def test_the_guide_quotes_the_whole_number_limits_when_ausrasp_is_the_source(
    fixture_path, site, rules
):
    pg = guide(page(fixture_path, site, rules, all_ausrasp))
    assert "an updraft of 3 m/s" in pg  # Good
    assert "an updraft of 4 m/s" in pg  # Strong
    assert "2.5 m/s" not in pg and "3.5 m/s" not in pg


def test_the_guide_keeps_the_estimate_limits_when_there_is_no_ausrasp(fixture_path, site, rules):
    pg = guide(page(fixture_path, site, rules))
    assert "2.5 m/s" in pg and "3.5 m/s" in pg


def test_a_mixed_page_explains_both_sets_of_limits(fixture_path, site, rules):
    t = text(page(fixture_path, site, rules, some_ausrasp))
    assert "Where AUSRASP's figures are not available a block uses the page's own estimate" in t
    assert "uses 2.5 m/s" in t and "whole metres per second" in t


def test_the_method_section_describes_the_ausrasp_source(fixture_path, site, rules):
    html = page(fixture_path, site, rules, all_ausrasp)
    m = re.search(r'<details class="guide" id="method">(.*?)</details>', html, flags=re.S)
    assert m is not None
    t = text(m.group(1))
    assert "Thermal height and updraft. From AUSRASP" in t
    assert "thermalling height" in t and "whole metres per second" in t
    assert "valid at its start time" in t and "AUSRASP is not used for wind or rain" in t
    assert "Fri 2 Oct 22:00 AEST" in t
    assert "The estimate's constants" not in t  # nothing in this page is an estimate


def test_the_footer_credits_ausrasp_and_the_vhpa_in_either_case(fixture_path, site, rules):
    for mutate in (None, all_ausrasp):
        html = page(fixture_path, site, rules, mutate)
        foot = text(html[html.index("<footer>") :])
        assert "VHPA" in foot and "run on donations" in foot and "AUSRASP" in foot
    foot = text(page(fixture_path, site, rules, all_ausrasp).split("<footer>")[1])
    assert "Thermal height and updraft are AUSRASP 's forecast" in foot


def test_arrows_and_grades_are_unchanged_by_the_source_label(fixture_path, site, rules):
    base = page(fixture_path, site, rules)
    ausrasp = page(fixture_path, site, rules, lambda d: all_ausrasp(d))
    assert base.count('class="cell ') == ausrasp.count('class="cell ')


def test_the_page_says_the_highest_cell_in_the_block_is_used(fixture_path, site, rules):
    html = page(fixture_path, site, rules, all_ausrasp)
    t = text(html)
    assert "the highest value in the block of 3 by 3 grid cells (4 km each) around the launch" in t
    assert "the highest of the cells around the launch" in t  # the limits note


def test_with_a_radius_of_zero_the_page_says_nearest_cell(fixture_path, site, rules):
    import dataclasses

    one = dataclasses.replace(site, ausrasp=dataclasses.replace(site.ausrasp, cell_radius=0))
    d = json.loads(fixture_path.read_text())
    all_ausrasp(d)
    t = text(render_page(Forecast.from_dict(d), one, rules))
    assert "for the grid cell nearest the launch" in t and "highest of the cells" not in t


def test_the_25_km_grid_is_only_blamed_for_what_comes_from_it(fixture_path, site, rules):
    t = text(page(fixture_path, site, rules, all_ausrasp))
    assert (
        "The wind, gust, rain and temperature figures come from a global model with a grid of about 25 km"
        in t
    )
    assert "and thermals less detailed" not in t  # the thermals are AUSRASP's 4 km figures
    estimate = text(page(fixture_path, site, rules))
    assert (
        "A 25 km grid cannot see individual ridges" in estimate
        and "and thermals less detailed" in estimate
    )
