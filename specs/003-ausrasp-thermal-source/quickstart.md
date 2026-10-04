# Quickstart: AUSRASP Thermal Source

Prerequisites: the 001 setup (`uv sync`).

1. **Unit tests**: `uv run pytest -q` (all offline).
2. **Live read** (optional, needs network): `FFF_NETWORK=1 uv run pytest tests/integration/test_ausrasp_live.py -q` reads the manifest and one grid and checks the Mystic cell.
3. **Poll once, no rebuild**: `uv run ffforecast poll --no-rebuild --cache cache` prints which days changed and stores their values in `cache/ausrasp/`. Run it again: it prints `poll: no change`.
4. **Full run**: `uv run ffforecast run --cache cache --state state --out out --work work` prints `thermal: ausrasp (...)`; open `out/index.html`, expand a day, and check the "Thermal figures" row names the AUSRASP run.
5. **Fallback**: set `enabled = false` in `[ausrasp]` and run again: the page labels thermal figures as the estimate and nothing is fetched.
6. **Schedule check** after a week: read `cache/ausrasp/stamps.jsonl` and compare the times with the poll windows in the site file.
