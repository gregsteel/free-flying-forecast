# Implementation Plan: AUSRASP Thermal Source

**Branch**: `003-ausrasp-thermal-source` | **Date**: 2026-10-03 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/003-ausrasp-thermal-source/spec.md`

## Summary

Take thermal height and updraft for Mystic straight from AUSRASP's published grids, keep everything
else (wind, gusts, rain, storms, temperature) from GFS, and keep the GFS thermal estimate as the
labelled fallback. A small poller reads AUSRASP's per-day manifest on a schedule, fetches only the
changed days and only the hours the page uses, stores the Mystic cell values locally, and triggers a
rebuild of the page from the stored GFS data plus the new values. The `run` command also refreshes
AUSRASP first, so a normal run is always current.

## Technical Context

**Language/Version**: Python 3.13 (uv), as 001

**Primary Dependencies**: no new ones. `requests` (already used) for HTTP with gzip; `numpy` (already present) for the grid; standard library `json`, `datetime`

**Storage**: files under the cache directory: `ausrasp/cell.json`, `ausrasp/latlon2d.json`, `ausrasp/days/OUT+N.json` (the Mystic values per hour, the stamp, the model start time, fetched time), `ausrasp/stamps.jsonl` (every stamp change), `ausrasp/status.json` (the owner-only status), `ausrasp/backoff.json`. Writes are atomic (temp file then rename).

**Testing**: pytest with recorded AUSRASP sample files (small synthetic grids built in the tests, plus one trimmed real header) and a fake HTTP session; the existing page tests updated; a live test (needs `FFF_NETWORK=1`) that reads real files.

**Target Platform**: as 001 (macOS host, container); the poller is a second launchd job that runs the CLI every 20 minutes and exits at once when no check is due

**Project Type**: CLI pipeline that outputs a static site (unchanged)

**Performance Goals**: a check with no change is one small request; a full refresh of all seven days is 126 data requests of about 35 KB compressed (about 5.7 MB), spread over time; page rebuild from stored values under 15 seconds

**Constraints**: spec FR-024 (at most 150 requests an hour, 25 MB a day, one at a time, 1 s pause, descriptive user agent with the owner's contact, one switch to turn it off, back off 6 hours after a refusal)

**Scale/Scope**: one site, one region (VIC), seven days, nine hourly blocks a day, two quantities

## Constitution Check

| Principle | Status | How the plan meets it |
|---|---|---|
| I. Free and Open Inputs | Pass, with a note | Free and public, but not openly licensed and not a published interface: recorded as a risk, mitigated by the fallback and the off switch (spec Assumptions) |
| II. Reproducible in Docker | Pass | No new dependencies; the poller runs the same image |
| III. Fits the Hardware | Pass | A few KB of files and one small rebuild |
| IV. Unattended and Resilient | Pass | Every failure falls back to GFS; the last complete set per day is kept; atomic writes; missed polls lose nothing |
| V. Simple, Pilot-First Output | Pass | The page keeps its layout; it only labels the source |
| VI. Honest, Configurable Forecasts | Pass | The source is shown per block, the Guide states the whole-number thresholds from the rules file, the method section is updated |
| VII. Incremental, Verified Delivery | Pass | Built in small tested steps (tasks.md) |

## Project Structure

New and changed files:

```text
src/ffforecast/
├── ausrasp.py       # NEW: manifest, grid parsing, cell lookup, fetch with limits, local store, selection by time
├── schedule.py      # NEW: when a poll is due (windows and intervals), pure functions
├── config.py        # CHANGED: [ausrasp] section in the site file, [thermal_ausrasp] tiers in the rules file
├── models.py        # CHANGED: ForecastBlock/DailyOutlook gain thermal_source and thermal_run (optional)
├── diagnostics.py   # CHANGED: build_block accepts AUSRASP thermal values
├── grading.py       # CHANGED: the Good/Strong updraft thresholds can be overridden per source
├── gfsmode.py       # CHANGED: blocks and outlook take the AUSRASP lookup
├── outlook.py       # CHANGED: outlook takes the lookup
├── runner.py        # CHANGED: an "ausrasp" stage before "diagnose"; a rebuild helper for the poller
├── cli.py           # CHANGED: new `poll` command; `run` prints the thermal source
└── render.py        # CHANGED: source row, legend values, footer and method text
templates/page.html.j2                     # CHANGED: source row, Guide and method text, footer
config/site.mystic.toml                    # CHANGED: [ausrasp]
config/rules.toml                          # CHANGED: [thermal_ausrasp]
scripts/ffforecast-poll-launchd.plist      # NEW: every 20 minutes
tests/unit/test_ausrasp.py, test_schedule.py, test_thermal_override.py
tests/integration/test_ausrasp_run.py, test_ausrasp_ui.py, test_poll.py, ausrasp_gfs_live (optional)
tests/make_fixture.py                      # CHANGED: some fixture blocks carry the source
```

**Structure Decision**: two new modules and small changes elsewhere. AUSRASP code lives only in
`ausrasp.py` and `schedule.py`; the rest of the pipeline sees a plain lookup
`{utc datetime: Thermal(height_m, updraft_ms, run)}` and does not know where it came from.

## Design decisions

1. **Cell**: found once from `latlon2d.json` (cell centres are the midpoints of the corner points it lists), nearest by distance, stored in `cell.json` with its distance; the file is fetched again only if `cell.json` is missing or the grid shape changes.
2. **Grid reading**: the header line `Day=... Param=... Unit=... Mult=...` is parsed and checked (parameter, unit, shape 144 by 144, value range); values are multiplied by `Mult`; only row and column of the cell are kept. The source files are whole numbers, so nothing is lost.
3. **Which hours**: the hourly block times (10:00 to 18:00 local) converted to UTC, then to the `lst` hour on the clock the run used. The clock (UTC+10 or +11) is guessed from the manifest stamp (Melbourne's offset at that moment), checked against the first file's header (its local and UTC hours), and the other clock is tried if the guess was wrong; every later file must be valid at the expected UTC time. Stored days carry `format: 2`; days stored by the first reading (which assumed a fixed UTC+10 clock and so mislabelled daylight-time runs by an hour) are ignored and fetched again. For each of the seven day keys (OUT+0 to OUT+6) the wanted AUSRASP date is known from the manifest key position and today's AES date; the data header's `Day=` line is checked against it (a mismatch rejects the file).
4. **Complete day**: all wanted hours for both quantities fetched, valid, the same model start time (derived from the header: valid time minus forecast hours). Otherwise the stored day is untouched.
5. **Model start time**: from the header `Valid ... ValidZ= 500 Fcst= 41.0` as valid UTC minus the forecast hours; older than the stored one for that day is never accepted.
6. **Updraft thresholds**: `[thermal_ausrasp] good_updraft_ms = 3`, `strong_updraft_ms = 4` in the rules file; `grade_block` takes optional overrides; the same quality threshold and wind rules apply.
7. **Quality**: existing formula, from the AUSRASP updraft and the larger of GFS 10 m and launch wind (as now).
8. **Height at or below launch**: shown as the launch altitude with the updraft as published; the existing "poor if below min_height_m" rule then applies.
9. **Polling**: `ffforecast poll --if-due` is run by launchd every 20 minutes. `schedule.due()` returns whether a check is due from the configured windows (default: every 20 min from 04:30Z to 09:00Z and 16:00Z to 21:00Z, every 3 hours otherwise) and the time of the last check. A check reads the manifest, compares stamps, fetches changed days, logs stamp changes and, if any day was stored, rebuilds once and publishes through the normal stage.
10. **Rebuild without new GFS**: the rebuild runs the same stages with `force=True` and the cycle in `state.json`; `gfs.fetch_forecast_hour` already skips files in the cache, so only AUSRASP data changes. If the cache for that cycle was pruned, the rebuild falls back to a full run.
11. **Budgets**: a counter file records requests (time) and bytes per day; the client refuses to send once a limit is reached and says so in the status.
12. **Back-off**: a 403, 429 or 5xx on a manifest or data request writes `backoff.json` with a time 6 hours ahead; nothing is requested before then.
13. **Switch**: `[ausrasp] enabled = false` makes every function return "unavailable" with no network use.
14. **Status**: `status.json` holds per day the stamp, model start time and fetched time, the last success and attempt, the fallback reason, request and byte counts. A `status` line is also printed by `poll`.

## Complexity Tracking

No constitution violations. One deliberate addition: a second scheduled job (the poller), because the AUSRASP days change at times unrelated to the GFS schedule.
