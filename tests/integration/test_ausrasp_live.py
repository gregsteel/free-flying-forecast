"""Live check against AUSRASP's Victoria files. Skipped unless FFF_NETWORK=1.

Reads the manifest and a handful of files (about 20 requests), so run it sparingly."""

import dataclasses
import os

import pytest
import requests

from ffforecast import ausrasp

pytestmark = pytest.mark.skipif(os.environ.get("FFF_NETWORK") != "1", reason="needs network")


def test_the_real_files_are_readable_for_the_launch(site, tmp_path):
    cfg = dataclasses.replace(site.ausrasp, enabled=True)
    result = ausrasp.refresh(cfg, site, tmp_path, requests.Session())
    assert not result.reason, result.reason
    cell = ausrasp.read_status(ausrasp.store_dir(tmp_path))
    assert cell["fallback"] is None
    lookup, notes = ausrasp.thermal_lookup(tmp_path, cfg)
    assert lookup, notes
    for t in lookup.values():
        assert (
            0 <= t.height_m <= 5000 and 0 <= t.updraft_ms <= 10 and float(t.updraft_ms).is_integer()
        )
    c = ausrasp._read(ausrasp.store_dir(tmp_path) / "cell.json", {})
    assert c["distance_km"] < cfg.max_cell_km and c["shape"] == [144, 144]
