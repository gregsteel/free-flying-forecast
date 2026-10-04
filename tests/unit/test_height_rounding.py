import pytest

from ffforecast.render import height_down, unitise


@pytest.mark.parametrize(
    "m, metres, feet",
    [
        (1361, "1,300 m", "4,400 ft"),  # 4465 ft
        (1844, "1,800 m", "6,000 ft"),  # 6050 ft
        (1899.9, "1,800 m", "6,200 ft"),  # 6232 ft: each unit rounds in its own steps
        (1900, "1,900 m", "6,200 ft"),
        (800, "800 m", "2,600 ft"),  # 2625 ft
        (99, "0 m", "300 ft"),  # 325 ft
    ],
)
def test_heights_round_down_to_100_m_and_to_100_ft_separately(m, metres, feet):
    h = str(height_down(m))
    assert (
        f'<span class="u a-m">{metres}</span>' in h and f'<span class="u a-ft">{feet}</span>' in h
    )


def test_the_short_form_is_bare_numbers_rounded_the_same_way():
    assert str(height_down(1361, short=True)) == (
        '<span class="u a-m">1300</span><span class="u a-ft">4400</span>'
    )


def test_a_height_is_never_rounded_up():
    for m in range(0, 3000, 7):
        rounded = int(str(height_down(m, short=True)).split('a-m">')[1].split("<")[0])
        assert rounded <= m and m - rounded < 100


def test_reasons_that_quote_a_thermal_height_use_the_same_rounding():
    out = str(unitise("Thermals are weak or low (20% quality, 785 m)."))
    assert (
        '<span class="u a-m">700 m</span>' in out and '<span class="u a-ft">2,500 ft</span>' in out
    )
