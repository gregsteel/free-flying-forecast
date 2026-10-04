"""Live check against NOAA's bucket. Skipped unless FFF_NETWORK=1."""

import os

import pytest
import requests

from ffforecast import gfs
from ffforecast.outlook import read_gfs_samples

pytestmark = pytest.mark.skipif(os.environ.get("FFF_NETWORK") != "1", reason="needs network")


def test_download_and_read_one_hour(tmp_path):
    s = requests.Session()
    cycle = gfs.latest_available_cycle(s, check_fhour=12)
    assert cycle is not None
    f = gfs.fetch_forecast_hour(s, cycle, 6, tmp_path)
    assert f.stat().st_size < 6_000_000  # five global fields only
    rows = read_gfs_samples([f], -36.7584099, 146.965839)
    assert len(rows) == 1
    r = rows[0]
    assert 0 <= r["hpbl_m"] < 5000 and -30 < r["t2_c"] < 50 and abs(r["u10"]) < 60
