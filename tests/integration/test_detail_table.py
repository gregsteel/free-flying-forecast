import json
import re

from ffforecast.models import Forecast
from ffforecast.render import render_page

LABELS = [
    "Ground wind",
    "Gusts at 10 m",
    "Gusts at launch",
    "Wind aloft",
    "Gusts at thermal height",
    "Wind shear",
    "Thermal height",
    "Thermal quality",
    "Updraft",
    "Sun reaching the ground",
    "Temperature, ground",
    "Temperature, at thermal height",
    "Rain",
]


def page(fixture_path, site, rules, mutate=None):
    d = json.loads(fixture_path.read_text())
    if mutate:
        mutate(d)
    return render_page(Forecast.from_dict(d), site, rules)


def tables(html):
    return re.findall(r'<table class="dt">.*?</table>', html, flags=re.S)


def row_labels(table):
    return [
        re.sub(r"<[^>]+>", "", t).strip()
        for t in re.findall(r'<th scope="row">(.*?)</th>', table, flags=re.S)
    ]


def base(label):
    """A row label without its unit, e.g. 'Ground wind (ktskph)' -> 'Ground wind'."""
    return label.split(" (")[0]


def test_one_table_per_detailed_day(fixture_path, site, rules):
    assert len(tables(page(fixture_path, site, rules))) == 4


def test_row_headings_are_in_the_left_column_once_per_day(fixture_path, site, rules):
    for t in tables(page(fixture_path, site, rules)):
        labels = row_labels(t)
        assert labels[0].startswith("Wind at launch (") and "800 m" in labels[0]
        assert [base(x) for x in labels[1:]] == LABELS
        assert len(set(labels)) == len(
            labels
        )  # each heading appears once, not once per time column


def test_headings_are_real_row_headers(fixture_path, site, rules):
    for t in tables(page(fixture_path, site, rules)):
        assert t.count('<th scope="row">') == 14
        assert t.count('<th scope="col"') == 9
        # every body row is a heading plus one value cell per time
        body = re.search(r"<tbody>(.*?)</tbody>", t, flags=re.S)
        assert body is not None
        for tr in re.findall(r"<tr>(.*?)</tr>", body.group(1), flags=re.S):
            assert tr.count("<td") == 9


def test_values_sit_in_the_time_columns_in_order(fixture_path, site, rules):
    t = tables(page(fixture_path, site, rules))[0]
    ground = re.search(r'<th scope="row">Ground wind .*?</th>(.*?)</tr>', t, flags=re.S)
    assert ground is not None
    cells = re.findall(r"<td>(.*?)</td>", ground.group(1), flags=re.S)
    assert len(cells) == 9 and all("s-kts" in c for c in cells)
    height = re.search(r'<th scope="row">Thermal height .*?</th>(.*?)</tr>', t, flags=re.S)
    assert height is not None and [
        c for c in re.findall(r"<td>(.*?)</td>", height.group(1), flags=re.S)
    ]


def test_launch_wind_row_has_the_coloured_triangle(fixture_path, site, rules):
    t = tables(page(fixture_path, site, rules))[0]
    row = re.search(r'<th scope="row">Wind at launch.*?</tr>', t, flags=re.S)
    assert row is not None
    assert row.group(0).count('class="dir ') == 9 and row.group(0).count("<svg") == 9


def test_table_lines_up_with_the_header_row_above_it(fixture_path, site, rules):
    html = page(fixture_path, site, rules)
    # one shared first-column width drives the header row, the table and the reasons grid
    assert (
        "details.day>summary{list-style:none;cursor:pointer;display:grid;grid-template-columns:var(--lw) repeat(9,minmax(0,1fr))"
        in html
    )
    assert "table.dt col.dt-first{width:var(--lw)}" in html
    assert "details.day{--lw:3.4rem" in html and "details.day{--lw:9.5rem}" in html
    assert (
        "details.day{--lw:5rem}" in html
    )  # narrow screens: five columns leave room for longer headings
    assert '<colgroup><col class="dt-first">' + "<col>" * 9 + "</colgroup>" in html


def test_column_headers_carry_the_grade_and_keep_the_time_for_screen_readers(
    fixture_path, site, rules
):
    t = tables(page(fixture_path, site, rules))[0]
    heads = re.findall(r'<th scope="col"[^>]*>(.*?)</th>', t, flags=re.S)
    assert len(heads) == 9
    assert re.search(r'<span class="sr">10:00: </span>', heads[0])  # the time is in the row above
    assert 'class="pill g g-pg ' in heads[0] and 'class="pill g g-hg ' in heads[0]
    assert '<span class="ic">' in heads[0]  # phones drop the icon and show just the word


def test_reasons_are_listed_per_time_for_both_gliders(fixture_path, site, rules):
    html = page(fixture_path, site, rules)
    grids = re.findall(r'<div class="whygrid">.*?</div>\s*</div>\s*</div>', html, flags=re.S)
    assert len(re.findall(r"<summary>Why this grade</summary>", html)) == 4
    why = re.findall(r'<div class="why">', html)
    assert len(why) == 36  # nine hours, four days
    assert html.count('<strong class="whytime">') == 36  # a time heading for each
    assert html.count('class="reasons g g-pg"') == 36 and html.count('class="reasons g g-hg"') == 36
    assert grids is not None


def test_reasons_are_listed_below_the_table_one_hour_after_another(fixture_path, site, rules):
    html = page(fixture_path, site, rules)
    assert ".whygrid{display:block;" in html  # nine columns would be far too narrow for sentences
    assert ".whytime{display:none}" not in html  # every hour keeps its time heading


def test_a_missing_time_leaves_an_empty_column_not_a_shifted_one(fixture_path, site, rules):
    def drop(d):
        d["blocks"] = [b for b in d["blocks"] if not b["start"].startswith("2026-10-04T13")]

    t = tables(page(fixture_path, site, rules, drop))[0]
    assert t.count('<th scope="col"') == 9 and '<th scope="col" class="empty"' in t
    ground = re.search(r'<th scope="row">Ground wind .*?</th>(.*?)</tr>', t, flags=re.S)
    assert ground is not None
    cells = re.findall(r"<td>(.*?)</td>", ground.group(1), flags=re.S)
    assert (
        len(cells) == 9 and cells[3].strip() == ""
    )  # 13:00 is the fourth column: blank, others in place


def test_older_forecasts_without_launch_wind_omit_that_row(fixture_path, site, rules):
    def strip(d):
        for b in d["blocks"]:
            b.pop("wind_launch", None)

    for t in tables(page(fixture_path, site, rules, strip)):
        assert not row_labels(t)[0].startswith("Wind at launch")
        assert [base(x) for x in row_labels(t)] == LABELS


def test_old_card_layout_is_gone(fixture_path, site, rules):
    html = page(fixture_path, site, rules)
    assert '<section class="block' not in html and "<dt>Ground wind</dt>" not in html
    assert ".block{" not in html


def test_gusts_sit_directly_under_ground_wind(fixture_path, site, rules):
    for t in tables(page(fixture_path, site, rules)):
        labels = row_labels(t)
        names = [base(x) for x in labels]
        assert names[names.index("Ground wind") + 1] == "Gusts at 10 m"


def test_why_this_grade_is_collapsed_by_default(fixture_path, site, rules):
    html = page(fixture_path, site, rules)
    opens = re.findall(r'<details class="whyd"([^>]*)>', html)
    assert len(opens) == 4 and all(o.strip() == "" for o in opens)  # none has the open attribute
    assert html.count("</details>") >= html.count("<details")  # every one is closed
    for block in re.findall(r'<details class="whyd">(.*?)</details>', html, flags=re.S):
        assert block.startswith("<summary>Why this grade</summary>") and 'class="whygrid"' in block


def test_the_guide_says_what_the_gusts_are(fixture_path, site, rules):
    t = re.sub(r"<[^>]+>", " ", page(fixture_path, site, rules))
    assert "near the ground" in t and "not at launch altitude" in t


def cells_of(table, label):
    row = re.search(rf'<th scope="row">{label}.*?</th>(.*?)</tr>', table, flags=re.S)
    assert row is not None, label
    return re.findall(r"<td>(.*?)</td>", row.group(1), flags=re.S)


UNIT_WORDS = ("kts", "kph", "km/h", " m<", " ft<", "m/s", "ft/sec", "mm/h", "in/h", "\u00b0")


def test_the_units_are_in_the_row_labels_and_the_cells_hold_only_numbers(fixture_path, site, rules):
    t = tables(page(fixture_path, site, rules))[0]
    expected = {
        "Wind at launch": ("kts", "kph"),
        "Ground wind": ("kts", "kph"),
        "Gusts at 10 m": ("kts", "kph"),
        "Gusts at launch": ("kts", "kph"),
        "Gusts at thermal height": ("kts", "kph"),
        "Wind aloft": ("kts", "kph"),
        "Thermal height": ("m", "ft"),
        "Updraft": ("m/s", "ft/sec"),
        "Temperature, ground": ("\u00b0C", "\u00b0F"),
        "Temperature, at thermal height": ("\u00b0C", "\u00b0F"),
        "Rain": ("mm/h", "in/h"),
    }
    for label, units in expected.items():
        full = re.search(rf'<th scope="row">({label} .*?)</th>', t, flags=re.S)
        assert full is not None, label
        for unit in units:  # both unit names are in the label; CSS shows the chosen one
            assert f">{unit}</span>" in full.group(1), (label, unit)
    for label in (
        "Ground wind",
        "Gusts at 10 m",
        "Gusts at launch",
        "Gusts at thermal height",
        "Wind aloft",
        "Thermal height",
        "Updraft",
    ):
        for cell in cells_of(t, label):
            visible = re.sub(r"<[^>]+>", " ", cell)
            assert not any(w in visible for w in ("kts", "kph", " m ", " ft", "m/s", "ft/sec")), (
                label,
                cell,
            )


def test_thermal_quality_keeps_its_percent_sign_and_has_no_unit_label(fixture_path, site, rules):
    t = tables(page(fixture_path, site, rules))[0]
    assert '<th scope="row">Thermal quality</th>' in t
    assert all(re.fullmatch(r"\d+%", c) for c in cells_of(t, "Thermal quality"))


def test_words_stay_words_in_the_table(fixture_path, site, rules):
    t = tables(page(fixture_path, site, rules))[0]
    assert set(cells_of(t, "Wind shear")) <= {"light", "moderate", "strong"}
    rain = cells_of(t, "Rain")
    assert "none" in rain  # no rain is the word, not a number with a unit
    assert any("a-m" in c for c in rain)  # a wet hour shows the number
    assert "not available" in "".join(cells_of(t, "Gusts at 10 m")) or any(
        "s-kts" in c for c in cells_of(t, "Gusts at 10 m")
    )


def test_ground_and_aloft_winds_keep_their_compass_direction(fixture_path, site, rules):
    t = tables(page(fixture_path, site, rules))[0]
    assert all(re.match(r"[NSEW]{1,3} <span", c) for c in cells_of(t, "Ground wind"))
    assert all(re.match(r"[NSEW]{1,3} <span", c) for c in cells_of(t, "Wind aloft"))


def test_the_launch_row_label_names_the_altitude_and_the_speed_unit(fixture_path, site, rules):
    t = tables(page(fixture_path, site, rules))[0]
    label = re.search(r'<th scope="row">(Wind at launch.*?)</th>', t, flags=re.S)
    assert label is not None
    assert "800 m" in label.group(1) and ">kts</span>" in label.group(1)
