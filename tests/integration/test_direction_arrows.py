import json
import re

import pytest

from ffforecast.models import Forecast
from ffforecast.render import direction_class, render_page


@pytest.mark.parametrize(
    "deg,expected",
    [
        (0, "ok"),
        (40, "ok"),
        (320, "ok"),
        (41, "marginal"),
        (70, "marginal"),
        (319, "marginal"),
        (71, "off"),
        (180, "off"),
        (260, "off"),
    ],
)
def test_arrow_colour_follows_the_green_sector(rules, deg, expected):
    assert direction_class(deg, rules) == expected


def test_arrow_agrees_with_the_grading_sector(rules):
    from ffforecast.grading import grade_direction

    mapping = {"ok": "ok", "marginal": "ok"}  # a crossed launch is amber but still graded ok
    for deg in range(0, 360, 5):
        cls = direction_class(deg, rules)
        state = grade_direction(deg, 10, rules)[0]
        assert mapping.get(cls, state) == state or (cls == "off" and state in ("poor", "dangerous"))


def render(fixture_path, site, rules):
    return render_page(Forecast.from_dict(json.loads(fixture_path.read_text())), site, rules)


def test_arrows_are_coloured_on_a_white_circle(fixture_path, site, rules):
    html = render(fixture_path, site, rules)
    assert ".dir{" in html and "border-radius:50%" in html and "background:#fff" in html
    for cls in ("ok", "marginal", "off"):
        assert f".dir.{cls}{{color:" in html
    assert 'class="dir ok"' in html and 'class="dir off"' in html  # fixture covers both


def test_arrow_is_a_solid_triangle_pointing_downwind(fixture_path, site, rules):
    html = render(fixture_path, site, rules)
    m = re.search(
        r'<span class="dir ok"[^>]*><svg[^>]*style="transform:rotate\((\d+)deg\)"[^>]*><path d="([^"]+)" fill="currentColor"/>',
        html,
    )
    assert m is not None
    assert m.group(2).count("L") + m.group(2).count("h") + m.group(2).count("z") >= 1
    assert 'aria-hidden="true"' in m.group(0)  # decorative: the direction is also written out
    assert "&darr;" not in html  # the old text arrow is gone


def test_arrow_is_not_the_only_direction_cue(fixture_path, site, rules):
    html = render(fixture_path, site, rules)
    assert re.search(
        r"</span> (NNW|N|NNE|NE|ENE|E|ESE|SE|SSE|S|SSW|SW|WSW|W|WNW|NW) <span class=\"u s-kts\">\d",
        html,
    )


def test_arrow_colour_is_explained(fixture_path, site, rules):
    html = render(fixture_path, site, rules)
    assert (
        "green inside the flyable direction, amber just outside it (marginally crossed: noted, but it does not lower the grade), red outside it"
        in html
    )
