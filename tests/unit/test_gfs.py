from datetime import UTC, datetime

from ffforecast import gfs

IDX = """\
1:0:d=2026100212:HGT:surface:3 hour fcst:
2:1000:d=2026100212:LAND:surface:3 hour fcst:
3:2000:d=2026100212:UGRD:10 m above ground:3 hour fcst:
4:3500:d=2026100212:VGRD:10 m above ground:3 hour fcst:
5:5000:d=2026100212:CAPE:surface:3 hour fcst:
6:9000:d=2026100212:HPBL:surface:3 hour fcst:
"""


def test_parse_idx_byte_ranges():
    e = gfs.parse_idx(IDX)
    assert e[0].start == 0 and e[0].end == 999
    assert e[-1].end is None
    assert e[3].variable == "VGRD" and e[3].level == "10 m above ground"


def test_select_and_merge_adjacent():
    chosen = gfs.select(gfs.parse_idx(IDX))
    assert [e.variable for e in chosen] == ["HGT", "UGRD", "VGRD", "CAPE", "HPBL"]
    # LAND (1000-1999) is not wanted, so there is a gap; the rest is contiguous to the end
    assert gfs.merge_ranges(chosen) == [(0, 999), (2000, None)]


def test_prate_average_is_not_downloaded():
    idx = (
        "1:0:d=2026100212:PRATE:surface:6 hour fcst:\n"
        "2:500:d=2026100212:PRATE:surface:0-6 hour ave fcst:\n"
        "3:900:d=2026100212:HPBL:surface:6 hour fcst:\n"
    )
    chosen = gfs.select(gfs.parse_idx(idx))
    assert [(e.variable, e.forecast) for e in chosen] == [
        ("PRATE", "6 hour fcst"),
        ("HPBL", "6 hour fcst"),
    ]


def test_merge_keeps_gaps():
    e = gfs.parse_idx(IDX)
    picked = [e[0], e[2]]
    assert gfs.merge_ranges(picked) == [(0, 999), (2000, 3499)]


def test_cycle_urls():
    c = gfs.Cycle("20261002", 6)
    assert c.file_url(24, ".idx").endswith("gfs.20261002/06/atmos/gfs.t06z.pgrb2.0p25.f024.idx")
    assert c.label == "2026-10-02T06Z"


def test_candidate_cycles_newest_first_and_not_future():
    now = datetime(2026, 10, 3, 7, 0, tzinfo=UTC)
    cs = gfs.candidate_cycles(now, days=1)
    assert cs[0] == gfs.Cycle("20261003", 6)
    assert gfs.Cycle("20261003", 12) not in cs


class FakeSession:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = 0

    def get(self, url, headers=None, timeout=None):
        self.calls += 1
        o = self.outcomes.pop(0)
        if isinstance(o, Exception):
            raise o
        return o


class Resp:
    def __init__(self, code, content=b""):
        self.status_code, self.content = code, content


def test_download_retries_then_succeeds(tmp_path, monkeypatch):
    import requests

    monkeypatch.setattr(gfs.time, "sleep", lambda s: None)
    s = FakeSession([requests.ReadTimeout("slow"), Resp(503), Resp(206, b"abc")])
    n = gfs.download_ranges(s, "u", [(0, 2)], tmp_path / "f.grib2")
    assert n == 3 and s.calls == 3 and (tmp_path / "f.grib2").read_bytes() == b"abc"


def test_download_gives_up_and_leaves_no_final_file(tmp_path, monkeypatch):
    import pytest
    import requests

    monkeypatch.setattr(gfs.time, "sleep", lambda s: None)
    s = FakeSession([requests.ConnectionError("x")] * 4)
    with pytest.raises(RuntimeError):
        gfs.download_ranges(s, "u", [(0, 2)], tmp_path / "f.grib2")
    assert not (tmp_path / "f.grib2").exists()


def test_cache_key_changes_with_fields():
    a = gfs.fields_key(gfs.OUTLOOK_FIELDS)
    b = gfs.fields_key(gfs.BLOCK_FIELDS)
    assert a != b and a == gfs.fields_key(tuple(reversed(gfs.OUTLOOK_FIELDS)))
