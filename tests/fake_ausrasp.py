"""A pretend AUSRASP for tests: a small grid, a manifest and the per-hour files, served through a
fake HTTP session that records every request."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from ffforecast.ausrasp import nearest_cell

MELBOURNE = ZoneInfo("Australia/Melbourne")
BASE = "https://ausrasp.test/VIC/"
LAT0, LON0, STEP, N = -37.0, 146.7, 0.04, 12  # N by N cells


def corners() -> list:
    return [[[LAT0 + i * STEP, LON0 + j * STEP] for j in range(N + 1)] for i in range(N + 1)]


def stamp(t: datetime) -> str:
    return t.strftime("%Y%m%dT%H%MZ")


def grid_text(
    param: str, valid_utc: datetime, run: datetime, base: float,
    special: tuple[int, int, float] | list[tuple[int, int, float]],
    unit: str = "m", mult: int = 1, offset: int = 10,
) -> str:  # fmt: skip
    local = valid_utc + timedelta(hours=offset)
    fcst = (valid_utc - run).total_seconds() / 3600
    head = (
        f"Day= {local.year} {local.month} {local.day} {local.strftime('%a').upper()} "
        f"ValidLST= {local.hour:02d}00 {'AES' if offset == 10 else 'AED'} ValidZ= {valid_utc.hour}00 Fcst= {fcst:.1f} Init= 30 "
        f"Param= {param} Unit= {unit} Mult= {mult} Min= 0 Max= 9"
    )
    cells = {(r, c): v for r, c, v in (special if isinstance(special, list) else [special])}
    rows = []
    for i in range(N):
        rows.append(" ".join(str(int(cells.get((i, j), base))) for j in range(N)))
    return (
        "\n".join(["---", f"Title {param}", "Model= RASP Region= VIC", head, *rows, "---"]) + "\n"
    )


# file name -> (the quantity named inside the file, its unit, the World attribute that supplies it)
EXTRA_FILES = {
    "sfcwindspd": ("sfcwindSpeed", "m/s", "sfc_wind"),
    "bltopwindspd": ("bltopwindSpeed", "m/s", "top_wind"),
    "sfcsunpct": ("sfcsunpct", "%", "sun"),
}


class Resp:
    def __init__(self, status: int, text: str = "", headers: dict | None = None):
        self.status_code = status
        self.text = text
        self.content = text.encode()
        self.headers = headers or {}


class World:
    """Seven days of files. `runs[key]` is the model start of that day's run."""

    def __init__(self, now: datetime, lat: float, lon: float):
        self.now = now
        self.cell = nearest_cell(corners(), lat, lon)
        self.runs = {
            f"OUT+{n}": now.replace(hour=0, minute=0, second=0) - timedelta(hours=12)
            for n in range(7)
        }
        self.stamps = {k: stamp(r + timedelta(hours=5)) for k, r in self.runs.items()}
        self.requests: list[tuple[str, dict]] = []
        self.fail: dict[str, int] = {}  # substring of the path -> status to answer
        self.height = lambda key, hhmm: 1800.0
        self.updraft = lambda key, hhmm: 2.0
        # other cells with their own values: {(row offset, column offset): (height, updraft)}
        self.around: dict[tuple[int, int], tuple[float, float]] = {}
        self.mult = 1
        # the wind (m/s) and sunshine (%) files, as functions of (day key, hhmm)
        self.sfc_wind = lambda key, hhmm: 4.0
        self.top_wind = lambda key, hhmm: 9.0
        self.sun = lambda key, hhmm: 80.0
        self.clock: dict[
            str, int
        ] = {}  # force a day's clock (10 = AES, 11 = AED); default follows the stamp

    def date_of(self, key: str):
        return (self.now.astimezone(MELBOURNE) + timedelta(days=int(key[4:]))).date()

    def offset_of(self, key: str) -> int:
        """The clock the day's files are labelled in: Melbourne's offset when the run was made."""
        if key in self.clock:
            return self.clock[key]
        t = datetime.strptime(self.stamps[key], "%Y%m%dT%H%MZ").replace(tzinfo=UTC)
        return round(
            (t.astimezone(MELBOURNE).utcoffset() or timedelta(hours=10)).total_seconds() / 3600
        )

    def get(self, url: str, headers: dict | None = None, timeout: float = 0) -> Resp:
        path = url.removeprefix(BASE)
        self.requests.append((path, headers or {}))
        for sub, status in self.fail.items():
            if sub in path:
                return Resp(status, "error")
        if path == "version.json":
            return Resp(200, json.dumps({"generated": "x", "region": "VIC", "days": self.stamps}))
        if path == "latlon2d.json":
            return Resp(200, json.dumps(corners()))
        key, _, rest = path.partition("/FCST/")
        param, _, tail = rest.partition(".curr.")
        hhmm = tail[:4]
        d = self.date_of(key)
        offset = self.offset_of(key)
        valid = datetime(d.year, d.month, d.day, int(hhmm[:2]), tzinfo=UTC) - timedelta(
            hours=offset
        )
        if not 8 <= int(hhmm[:2]) <= 18:
            return Resp(404, "not found")
        r, c = self.cell["row"], self.cell["col"]
        if param in EXTRA_FILES:
            header, unit, fn = EXTRA_FILES[param]
            value = getattr(self, fn)(key, hhmm)
            text = grid_text(
                header, valid, self.runs[key], value, (r, c, value), unit, offset=offset
            )
            return Resp(200, text, {"content-length": str(len(text) // 3)})
        pick = 0 if param == "hglider" else 1
        own = self.height(key, hhmm) if pick == 0 else self.updraft(key, hhmm)
        cells = [(r, c, own)] + [(r + dr, c + dc, v[pick]) for (dr, dc), v in self.around.items()]
        if param == "hglider":
            text = grid_text(param, valid, self.runs[key], 100, cells, "m", offset=offset)
        else:
            text = grid_text(param, valid, self.runs[key], 1, cells, "m/sec", offset=offset)
        return Resp(200, text, {"content-length": str(len(text) // 3)})
