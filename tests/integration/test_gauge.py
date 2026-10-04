"""A small, cropped view of the club's live wind gauge sits above the station chart."""

import json
import re

from ffforecast.models import Forecast
from ffforecast.render import render_page


def page(fixture_path, site, rules):
    return render_page(Forecast.from_dict(json.loads(fixture_path.read_text())), site, rules)


def test_the_gauge_is_one_frame_of_the_clubs_gauge_page(fixture_path, site, rules):
    html = page(fixture_path, site, rules)
    assert html.count("<iframe") == 1
    m = re.search(r'<iframe class="gauge" src="([^"]+)"([^>]*)>', html)
    assert m is not None
    assert m.group(1) == "https://www.freeflightwx.com/mystic/gauge.php"
    attrs = m.group(2)
    assert 'title="Live wind gauge at the Mystic launch' in attrs  # named for screen readers
    assert 'loading="lazy"' in attrs and 'referrerpolicy="no-referrer"' in attrs
    # scripts are needed to draw the gauge and to ask its own server for data; nothing else is allowed
    assert 'sandbox="allow-scripts allow-same-origin"' in attrs


def test_the_gauge_sits_above_the_chart_and_the_period_buttons_below_it(fixture_path, site, rules):
    html = page(fixture_path, site, rules)
    section = html[html.index('<section aria-label="Weather station">') :]
    assert section.index('class="gaugewrap"') < section.index('class="history"')
    assert section.rindex('class="history"') < section.index(
        'class="periods"'
    )  # buttons under the chart


def test_the_frame_is_cropped_to_the_circle_and_compressed(fixture_path, site, rules):
    html = page(fixture_path, site, rules)
    assert (
        ".gaugewrap{box-sizing:content-box;position:relative;width:168px;height:168px;overflow:hidden;border-radius:50%"
        in html
    )
    assert "transform:scale(.4) translate(-40px,-154px)" in html
    # the ring was measured at x 40 to 459, y 154 to 573: 420 px square, and 420 at .4 is the 168 px window
    assert 420 * 0.4 == 168
    # content-box: the 1 px border sits outside the 168 px window, so it no longer trims the ring
    assert "margin:0 auto .6rem" in html  # centred


def test_the_stations_own_page_is_one_click_away_if_the_frame_does_not_load(
    fixture_path, site, rules
):
    """The heading links to the station page, which has the gauge as well as everything else."""
    html = page(fixture_path, site, rules)
    assert (
        '<h2><a href="https://www.freeflightwx.com/mystic/index.php">FreeFlight WX</a></h2>' in html
    )


def test_the_page_reads_no_data_from_the_gauge_itself(fixture_path, site, rules):
    """The club's server does not allow other sites to read its data, so the frame is the only way in."""
    html = page(fixture_path, site, rules)
    script = html[html.index("var TABS=") :]
    assert "gauge.php" not in script.split("</script>")[0]
