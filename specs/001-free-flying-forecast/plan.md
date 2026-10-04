# Implementation Plan: Free Flying Forecast

**Branch**: `001-free-flying-forecast` | **Date**: 2026-10-03 (last reviewed against the build the same day) | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/001-free-flying-forecast/spec.md`

## Summary

A scheduled, containerised pipeline on the owner's iMac. Each run finds the newest NOAA GFS cycle,
downloads the fields it needs, builds a forecast for Mystic (4 detailed days in hourly blocks, 10:00 to 18:00, plus a
3-day outlook), grades every block for paragliders and hang gliders against configurable rules
seeded from the NEVHGC FreeFlightWx Mystic settings, renders one static HTML page, and publishes it.
Two forecast sources exist:

- **GFS-only mode** (built and verified against live data): point values from the 25 km global
  model, including wind interpolated to launch altitude. It is also the fallback.
- **WRF mode** (written but not verified): a 12 km outer and 4 km inner WRF domain over north-east
  Victoria for days 1 to 4, with thermal and wind diagnostics derived from its output; days 5 to 7
  still come from GFS.

Publishing goes to GitHub Pages: `publish.py` force-pushes the site to a `gh-pages` branch as one commit
(Firebase Hosting, [002](../002-firebase-hosting-deploy/spec.md), was specified and then set aside on 2026-10-04). launchd triggers the run and catches up
after sleep; a state file prevents repeat runs for a cycle.

## Current state

| Part | State |
|---|---|
| Page, grading, Guide, glider and unit settings, cookie, pinned header, station chart periods, today panel | Built and tested; behaviour checked in a real browser |
| GFS fetch, launch-altitude wind, GFS-only forecast, run pipeline with retries and last-ok safety | Built; ran end to end against live NOAA data (143 s) |
| Run state, duplicate-cycle skip, pruning of old runs and cached weather data | Built and tested |
| Git publisher (interim) | Built and tested against a local repository; to be replaced by 002 |
| WRF image, namelists, orchestration, benchmark | Dockerfile and namelists written, **not built or run**; `wrf.py` not written |
| launchd schedule and host wrapper | Written, **not tried** on the iMac |
| GitHub Pages deployment | The git publisher is built and tested against a local repository; not yet pointed at the real repository (Firebase, 002, set aside) |
| AUSRASP thermal height and updraft as the thermal source, with polling | Built ([003](../003-ausrasp-thermal-source/spec.md)): AUSRASP supplies thermal height and updraft, polled by `ffforecast poll`; GFS stays the fallback and the source of wind, rain, gusts and storms |

## Technical Context

**Language/Version**: Python 3.13 (managed with `uv`); WRF/WPS 4.6.x in Fortran inside the same image (not yet built)

**Primary Dependencies**: numpy, xarray, netCDF4, eccodes (with `eccodeslib` for the binary library; reads GFS GRIB2), requests, Jinja2, tomllib (stdlib). No front-end framework: the page is one template with inline CSS and two small inline scripts. WRF, WPS, netCDF-Fortran and OpenMPI in the image.

**Storage**: Files only: a cache directory for GFS (the newest two cycles kept, about 400 MB each), a `state.json` and run log, a work directory, and an `out/` directory holding the published site (`index.html`, `forecast.json`)

**Testing**: pytest (about 210 tests) for grading, units, profile interpolation, diagnostics, GFS parsing and downloads, state, publishing, configuration and the rendered page (structure, accessibility, settings, cookie, Guide claims against real grading). Behaviour that needs a browser (clicks, cookies, downloads, alignment) was checked with headless Chrome and the findings turned into tests where possible. `ruff` and `pyright` are clean.

**Target Platform**: Linux arm64 container under Colima on macOS (Apple M4, 16 GB); launchd on the host

**Project Type**: CLI pipeline that outputs a static site

**Performance Goals**: Daily run under 3 hours (SC-005; GFS-only mode measured at about 2 minutes, WRF not yet measured); page document under 200 KB (SC-002; currently about 92 KB)

**Constraints**: Colima VM at most 8 CPUs and 10 GB RAM (constitution III); no inbound network access to the iMac; the forecast readable without scripting

**Scale/Scope**: One site (Mystic); 96 hours of detailed forecast (days 1 to 4), 9 hourly blocks a day, plus 3 outlook days (5 to 7); one glider type shown at a time, both rendered

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | How the plan meets it |
|---|---|---|
| I. Free and Open Inputs | Pass | WRF/WPS, NOAA GFS on AWS open data, Open-Meteo (free, attributed), GitHub Pages' free plan |
| II. Reproducible in Docker | Pass, to verify | One Dockerfile builds WRF and the Python tools; the host only runs `docker run` via launchd. The image has not been built yet |
| III. Fits the Hardware | To verify | Domain sizes chosen small; the first WRF task is a timed, memory-measured benchmark of a 96-hour run |
| IV. Unattended and Resilient | Pass in code, to verify on the iMac | Cycle-aware retry, last-ok retention, atomic swap and duplicate-cycle skip are tested; launchd catch-up is untried |
| V. Simple, Pilot-First Output | Pass | Static HTML with inline CSS; the forecast works without scripting; the only external elements are the optional weather station chart and the current-conditions panel, each failing soft |
| VI. Honest, Configurable Forecasts | Pass | Rules in TOML, versioned, source recorded; the Guide is generated from the rules and every claim is tested against the grading; footer shows model, run time and the advisory notice |
| VII. Incremental, Verified Delivery | Pass | Built in verifiable steps; each user-facing behaviour has tests and, where it needs a browser, a recorded browser check |

Risks recorded: principles II, III and the schedule part of IV cannot be confirmed until the WRF
image is built and a benchmark and a sleep-and-wake test are run on the iMac.

## Project Structure

### Documentation

```text
specs/001-free-flying-forecast/
├── spec.md
├── plan.md
├── research.md          # decisions and what was verified (sections 1 to 20)
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── cli.md
│   ├── config-schema.md
│   └── forecast-json.md
├── checklists/requirements.md
└── tasks.md
specs/002-firebase-hosting-deploy/     # Firebase deployment: set aside (GitHub Pages is used)
```

### Source Code (repository root)

```text
docker/
├── Dockerfile                 # WRF + WPS + Python 3.13/uv, arm64 (unverified)
└── namelists/                 # namelist.wps and namelist.input templates
config/
├── site.mystic.toml           # coordinates, launch altitude, domain, time zone, station chart periods, links
└── rules.toml                 # wind bands, direction sector, gust/rain/storm and thermal limits
src/ffforecast/
├── cli.py                     # check, render, run (fetch/wrf/diagnose/publish are placeholders)
├── config.py                  # loads and validates site and rules
├── models.py                  # forecast data classes and the detailed/outlook day split
├── units.py                   # conversions, compass, wind from u/v
├── gfs.py                     # cycle discovery, idx parsing, ranged download with retries, hour planning
├── profile.py                 # interpolate wind to launch altitude from the vertical profile
├── outlook.py                 # reads GFS GRIB values; days 5 to 7
├── gfsmode.py                 # blocks from GFS values (GFS-only mode)
├── diagnostics.py             # thermal height, w*, shear, temperatures, blocks; reads WRF output
├── grading.py                 # rules engine: grades and reasons per glider type
├── render.py                  # forecast.json to HTML context and page
├── pipeline.py                # stages, retry for late data, last-ok safety
├── runner.py                  # assembles the stages for `run`
├── state.py                   # state.json, run log, duplicate-cycle check, pruning
└── publish.py                 # interim git publisher (replaced by 002)
templates/
└── page.html.j2               # the whole page: markup, CSS, two small scripts
tests/
├── unit/  integration/  fixtures/  make_fixture.py
scripts/
├── ffforecast-launchd.plist   # host schedule (untried)
└── run-on-host.sh             # starts Colima if needed, then docker run
docs/benchmarks.md
pyproject.toml  uv.lock
```

`src/ffforecast/wrf.py` (WPS and WRF orchestration) does not exist yet.

**Structure Decision**: Single Python project plus a Docker build context. All forecast code runs
in the container; only a thin shell script and a launchd plist live on the host.

## Complexity Tracking

No constitution violations to justify. Two choices add complexity on purpose and are recorded in
research: rendering both glider types and showing one with CSS (section 20), and rendering every
unit and showing one with CSS (section 13), which keeps the page working without scripting at the
cost of a larger document.
