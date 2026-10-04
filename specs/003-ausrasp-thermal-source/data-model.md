# Data Model: AUSRASP Thermal Source

## Stored under `<cache>/ausrasp/`

**cell.json** (Mystic Cell): `{ "region": "VIC", "grid": "d2", "shape": [144, 144], "row": 59, "col": 100, "lat": -36.7605, "lon": 146.9571, "distance_km": 0.81, "found_at": "<iso>" }`

**days/OUT+N.json** (AUSRASP Day Set; values are the highest in the block of `radius` cells around the Mystic Cell): `{ "key": "OUT+1", "stamp": "20261002T1739Z", "model_start": "2026-10-02T12:00:00Z", "fetched_at": "<iso>", "radius": 1, "values": { "<UTC iso of valid hour>": { "height_m": 1844, "updraft_ms": 2 } } }`. Written only when complete; replaced atomically; never replaced by an older `model_start`.

**stamps.jsonl** (Stamp Log): one line per change: `{ "seen_at": "<iso>", "key": "OUT+1", "old": "...", "new": "...", "model_start": "..." }`

**status.json** (Source Status): `{ "enabled": true, "last_check": "<iso>", "last_success": "<iso>", "fallback": null | { "since": "<iso>", "reason": "..." }, "days": { "OUT+1": { "stamp": "...", "model_start": "...", "fetched_at": "..." } }, "requests_today": 12, "bytes_today": 480000 }`

**backoff.json**: `{ "until": "<iso>", "reason": "HTTP 429" }`

**budget.json**: `{ "day": "2026-10-03", "bytes": 0, "requests": [<unix times>] }`

## In forecast.json (additions, schema stays 1)

`ForecastBlock.thermal_source`: `"ausrasp"` or `"gfs"` (default `"gfs"`). `ForecastBlock.thermal_run`: model start of the AUSRASP run as ISO UTC, empty for `"gfs"`. `DailyOutlook.thermal_source` likewise. Older files without them read as `"gfs"`.

## In memory

`Thermal(height_m: float, updraft_ms: float, run: str)`; a lookup is `dict[datetime (UTC, whole hour), Thermal]`.
