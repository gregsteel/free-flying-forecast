"""Reader test against a tiny synthetic wrfout file (real WRF output is checked on the iMac)."""

from datetime import datetime

import numpy as np
import pytest
import xarray as xr

from ffforecast.diagnostics import read_wrf_point


def make_wrfout(path, ny=4, nx=5, nz=6):
    lat = np.linspace(-37.5, -36.0, ny)[:, None] * np.ones((1, nx))
    lon = np.ones((ny, 1)) * np.linspace(146.0, 147.5, nx)[None, :]
    t = 1
    times = np.array([list("2026-10-04_00:00:00")], dtype="S1")
    ph = np.zeros((t, nz + 1, ny, nx))
    phb = np.arange(nz + 1)[None, :, None, None] * 9.80665 * 300 + np.zeros((t, nz + 1, ny, nx))
    ds = xr.Dataset(
        {
            "Times": (("Time", "DateStrLen"), times),
            "XLAT": (
                ("Time", "south_north", "west_east"),
                np.broadcast_to(lat, (t, ny, nx)).copy(),
            ),
            "XLONG": (
                ("Time", "south_north", "west_east"),
                np.broadcast_to(lon, (t, ny, nx)).copy(),
            ),
            "HGT": (("Time", "south_north", "west_east"), np.full((t, ny, nx), 700.0)),
            "PBLH": (("Time", "south_north", "west_east"), np.full((t, ny, nx), 1200.0)),
            "HFX": (("Time", "south_north", "west_east"), np.full((t, ny, nx), 200.0)),
            "T2": (("Time", "south_north", "west_east"), np.full((t, ny, nx), 288.15)),
            "U10": (("Time", "south_north", "west_east"), np.zeros((t, ny, nx))),
            "V10": (("Time", "south_north", "west_east"), np.full((t, ny, nx), -4.0)),
            "PH": (("Time", "bottom_top_stag", "south_north", "west_east"), ph),
            "PHB": (("Time", "bottom_top_stag", "south_north", "west_east"), phb),
            "U": (
                ("Time", "bottom_top", "south_north", "west_east_stag"),
                np.zeros((t, nz, ny, nx + 1)),
            ),
            "V": (
                ("Time", "bottom_top", "south_north_stag", "west_east"),
                np.full((t, nz, ny + 1, nx), -6.0),
            ),
        }
    )
    ds.to_netcdf(path)


def test_reads_nearest_point(tmp_path):
    p = tmp_path / "wrfout_d02"
    make_wrfout(p)
    rows = read_wrf_point(p, -36.7584, 146.9658)
    assert len(rows) == 1
    r = rows[0]
    assert r["time"] == datetime(2026, 10, 4, 0, 0)
    assert r["pblh_m"] == 1200 and r["hfx_wm2"] == 200
    assert r["t2_c"] == pytest.approx(15.0)
    assert r["terrain_m"] == 700
    d, kph = r["ground"]
    assert d == pytest.approx(0) or d == pytest.approx(360)
    assert kph == pytest.approx(14.4)
    assert r["aloft"][1] == pytest.approx(21.6)
