---
description: "Task list for Free Flying Forecast"
---

# Tasks: Free Flying Forecast

**Last reviewed against the build**: 2026-10-03. Tasks T001 to T077 were added as the work went on, so later phases appear after the original ones. Where a task was overtaken by a later decision it is marked **superseded** and points to the task that replaced it. Deployment is tracked separately under [002](../002-firebase-hosting-deploy/spec.md); it has no tasks yet.

**Input**: Design documents from `/specs/001-free-flying-forecast/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: Included. The constitution (principle VII) requires automated tests for pure logic such as grading and unit conversion.

**Organization**: Grouped by user story. Tasks marked **[iMac]** can only be verified on the owner's iMac (Colima/Docker); they may be written elsewhere but stay unchecked until verified there.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: US1 (see the forecast), US2 (daily self-refresh), US3 (trust and tuning)

## Phase 1: Setup

- [x] T001 Create the project layout from plan.md: `src/ffforecast/`, `tests/unit/`, `tests/integration/`, `tests/fixtures/`, `config/`, `docker/`, `templates/`, `scripts/`
- [x] T002 Create `pyproject.toml` for Python 3.13 managed by `uv` with numpy, xarray, netCDF4, requests, Jinja2 and dev tools pytest, ruff, pyright; add a `ffforecast` console script; generate `uv.lock`
- [x] T003 [P] Configure ruff and pyright in `pyproject.toml` and add a `.gitignore` (cache, runs, out, .venv)
- [x] T004 [P] Create `config/site.mystic.toml` (id `mystic`, name "Mystic, VIC", lat -36.7584099, lon 146.965839, elevation_m 785 (later corrected to 800, the owner's figure), timezone `Australia/Melbourne`, d01 12 km and d02 4 km domains, links to the FreeFlightWx station, gauge and NEVHGC)
- [x] T005 [P] Create `config/rules.toml` seeded from FreeFlightWx (version 1; source "NEVHGC FreeFlightWx Mystic site settings"; `speed_green_from_mph = 1`, `speed_orange_from_mph = 12`, `speed_red_from_mph = 14`; sector centre 0, half-width 40; thermal and XC cut-offs as documented defaults)

## Phase 2: Foundational (blocks all stories)

- [x] T006 [P] Implement unit conversions (mph, kph, m/s, ft, degrees and compass names) in `src/ffforecast/units.py` and tests in `tests/unit/test_units.py`
- [x] T007 Implement validated loading of the site and rules files in `src/ffforecast/config.py` per `contracts/config-schema.md`: speed keys MUST carry unit suffixes, `version` MUST be present, `source` MUST be non-empty; tests in `tests/unit/test_config.py`
- [x] T008 [P] Implement the forecast data classes from `data-model.md` (Site, VerdictRules, ForecastBlock, DailyOutlook, ForecastRun) in `src/ffforecast/models.py`, including JSON (de)serialisation matching `contracts/forecast-json.md`
- [x] T009 [P] Implement run state in `src/ffforecast/state.py`: `state.json` (last published cycle), append-only run log, cycle dedupe; tests in `tests/unit/test_state.py`
- [x] T010 Implement the CLI skeleton and `check` command in `src/ffforecast/cli.py` per `contracts/cli.md` (exit codes 0, 1, 2, 3)
- [x] T011 [P] Implement GFS cycle discovery, `.idx` parsing and ranged download in `src/ffforecast/gfs.py` (bucket `noaa-gfs-bdp-pds`, path `gfs.YYYYMMDD/CC/atmos/gfs.tCCz.pgrb2.0p25.fFFF`); tests in `tests/unit/test_gfs.py` using a saved idx fixture
- [ ] T012 [P] Write `docker/Dockerfile` for Linux arm64: build WPS and WRF 4.6.x from source, install Python 3.13 and `uv`, copy the project **[iMac]**
- [x] T013 [P] Write `docker/namelists/namelist.wps` and `docker/namelists/namelist.input` templates for d01 12 km and d02 4 km centred on Mystic, hourly output (run length to be 96 hours for days 1 to 4; the templates are unverified), GFS 3-hourly forcing

**Checkpoint**: config, models, state and GFS fetch usable.

## Phase 3: User Story 1 - See this week's conditions at a glance (P1) MVP

**Goal**: A phone-readable page with 4 detailed days and a labelled low-confidence outlook for days 5 to 7.

**Independent Test**: Render from `tests/fixtures/forecast.json` and confirm every block shows its values and verdict, readable at phone width, page under 200 KB.

### Tests

- [x] T014 [P] [US1] Grading tests in `tests/unit/test_grading.py`: green only when direction is inside the sector (0 degrees, 40 degrees either side) and speed is in the green band; 12 mph and 14 mph boundaries; reasons text present; PG and HG graded separately
- [x] T015 [P] [US1] Diagnostics tests in `tests/unit/test_diagnostics.py` for thermal height, Deardorff `w*`, shear classification and XC rating on known values
- [x] T016 [P] [US1] Rendering golden test in `tests/integration/test_render.py`: page under 200 KB, no `<script>` in the forecast itself, no external images, verdict not conveyed by colour alone

### Implementation

- [x] T017 [P] [US1] Create `tests/fixtures/forecast.json` with 4 days of blocks and a 3-day outlook (days 5 to 7), covering all four verdicts, hang glider grades and a wet storm block
- [x] T018 [US1] Implement the rules engine in `src/ffforecast/grading.py`: wind verdict from strength and direction (dangerous, turbulent, great, poor) with text reasons, separate PG and HG limits
- [x] T019 [P] [US1] Implement diagnostics in `src/ffforecast/diagnostics.py`: thermal height from `PBLH`, `w* = ((g/theta) * (HFX/(rho*cp)) * zi)^(1/3)`, thermal quality percent mapping, shear class, temperatures, qualitative XC rating (poor, fair, good, great; no distances)
- [x] T020 [P] [US1] Implement the days 5 to 7 outlook from GFS point values in `src/ffforecast/outlook.py`, always `confidence: low`
- [x] T021 [US1] Create the page template `templates/page.html.j2`: inline CSS, mobile-first, emoji or inline SVG icons, verdict shown as colour plus text, days 1 to 3 as 2-hour blocks, outlook section labelled low confidence
- [x] T022 [US1] Implement `src/ffforecast/render.py` and the `render` CLI command: render only from `forecast.json`, write `out/index.html` and `out/forecast.json`
- [x] T023 [US1] *Superseded by T050 and T069.* Embedded the FreeFlightWx gauge as a lazy, sandboxed iframe with a fallback link; the gauge is now only a link

**Checkpoint**: US1 verifiable from fixtures.

## Phase 4: User Story 2 - Forecast refreshes itself (P2)

**Goal**: A daily unattended run that keeps the last good page on any failure.

**Independent Test**: Simulate a late cycle and a failed stage; confirm the previous page stays, its age is shown and the failure is logged.

- [x] T024 [P] [US2] Tests in `tests/integration/test_run.py`: failed stage never replaces the published page; duplicate cycle exits as `skipped_duplicate`; no data in window exits 2
- [ ] T025 [US2] Implement WPS and WRF orchestration in `src/ffforecast/wrf.py` (`geogrid`, `ungrib`, `metgrid`, `real.exe`, `wrf.exe` via MPI) and the `wrf` command **[iMac]**
- [ ] T026 [US2] **Benchmark first** (constitution III): run a 6 to 12 hour case with the Colima VM at 8 CPUs and 10 GB; record wall time and peak memory in `docs/benchmarks.md`; extrapolate to 96 hours **[iMac]**
- [ ] T027 [US2] Read WRF output into diagnostics: wire `diagnostics.py` to WRF `PBLH`, `HFX`, winds and temperatures at the Mystic point, and write `forecast.json` (`diagnose` command) **[iMac]**
- [x] T028 [US2] Implement the `run` pipeline in `src/ffforecast/cli.py`: bounded retry for a late GFS cycle, stage ordering, atomic swap of `out/` only after success, "last updated" age shown on the page
- [x] T029 [P] [US2] Implement the interim git publisher in `src/ffforecast/publish.py`: force-push a single orphan commit to a git remote using a mounted deploy key. *To be replaced by the Firebase deployment (002) and then removed (002 FR-026)*
- [x] T030 [P] [US2] Write `scripts/run-on-host.sh` (start Colima at 8 CPUs, 10 GB if stopped; `docker run` with cache, runs and key mounts) and `scripts/ffforecast-launchd.plist` (`StartCalendarInterval` so a missed run fires on wake)
- [x] T031 [P] [US2] Add old-run pruning in `src/ffforecast/state.py` and the run log fields `duration_s` and `peak_mem_mb`
- [ ] T032 [US2] Verify catch-up on the iMac: sleep across the schedule, wake, confirm exactly one run and one skipped duplicate **[iMac]**

## Phase 5: User Story 3 - Understand and trust the numbers (P3)

**Goal**: Visible sources, credits, advisory notice and config-only tuning.

**Independent Test**: Change a threshold, regenerate, confirm verdicts and legend change without code edits.

- [x] T033 [P] [US3] Test in `tests/integration/test_footer.py`: footer contains model, cycle time, generated time, rules version, advisory notice and working credit links to FreeFlightWx station, gauge and NEVHGC (FR-007, FR-012d)
- [x] T034 [P] [US3] Test in `tests/integration/test_tuning.py`: editing `config/rules.toml` changes verdicts and the legend with no code change (FR-012)
- [x] T035 [US3] Add the footer and credit block to `templates/page.html.j2`, including that the verdict rules are based on the club's published Mystic site settings
- [x] T036 [US3] Generate the legend from the loaded rules so it always matches the thresholds, and show the rules version and source

## Phase 5b: Display units (added mid-build, spec FR-016)

- [x] T040 [US1] Render every speed, height and temperature in all units and show only the selected one, with a CSS-only selector (kts default, m default, C default) in `src/ffforecast/render.py` and `templates/page.html.j2`
- [x] T041 [US1] Convert plain-text reasons and the legend to the selected units (`unitise` in `render.py`); tests in `tests/integration/test_units_ui.py`
- [x] T042 [US1] Remember the chosen units on the device (optional `localStorage`)
- [x] T043 [US1] *Withdrawn.* Asking FreeFlightWx for a `?units=` option for the gauge: the gauge is no longer embedded, and the station chart shows km/h and knots together (FR-016a)

## Phase 5c: GFS-only mode (built early, research item 12)

- [x] T044 [US2] Plan the GFS forecast hours for blocks and outlook, including the daylight-saving start (`gfs.plan_hours`); `tests/unit/test_gfsmode.py`
- [x] T045 [US2] Build blocks and outlook from GFS point values (`src/ffforecast/gfsmode.py`, `outlook.py`), and wire `ffforecast run --model gfs` (`runner.py`, `cli.py`)
- [x] T046 [US2] Verify against live NOAA data: one run, one skipped duplicate (see `docs/benchmarks.md`)

## Phase 5d: Rain, storms and the live panels (raised mid-build, FR-012c, FR-017, FR-018)

- [x] T047 [US1] Fetch precipitation rate, CAPE and gusts from GFS (instantaneous PRATE only), read them from the GRIB files, and key the cache on the field list (`gfs.py`, `outlook.py`)
- [x] T048 [US1] Grade rain, storms and gusts with thresholds in `config/rules.toml` `[weather]` (`grading.py`, `config.py`); tests in `tests/unit/test_weather_rules.py`
- [x] T049 [US1] Show rain and gusts per block, a wet-days banner with the BoM warnings link, and unit-aware reasons (`render.py`, `templates/page.html.j2`)
- [x] T050 [US1] Replace the gauge embed with the station's 4-hour chart image, linked and credited
- [x] T051 [US1] Add the current-conditions tile from Open-Meteo (first called "Right now"; it is now the "Today at Mystic" panel), following the unit selector, hidden on failure
- [x] T054 [US1] Lay days out as expandable rows with one column per time slot, collapsed to grade and thermal height, and the outlook four across (`render.py`, `templates/page.html.j2`; `tests/integration/test_day_rows.py`)
- [x] T055 [US1] Two-column top section: today's weather and hourly forecast on the left, half-width station chart on the right; wind units cut to knots and km/h (`templates/page.html.j2`, `render.py`, `config/site.mystic.toml`; `tests/integration/test_top_panels.py`)
- [x] T056 [US1] Wind at launch altitude: vertical profile and interpolation (`profile.py`), extra GFS levels, verdict judged on it, shown with an arrow in each day header and labelled in the details (`gfs.py`, `outlook.py`, `gfsmode.py`, `diagnostics.py`, `render.py`, template; `tests/unit/test_profile.py`)
- [x] T057 [US1] Header shows only the labelled PG grade; launch-wind arrows coloured by direction on a white circle, stacked above the text on phones (`render.py` `direction_class`, template; `tests/integration/test_direction_arrows.py`)
- [x] T058 [US1] Header shows only a larger grade icon (word kept for screen readers); launch-wind arrow is a solid, coloured triangle on a white circle (template; `tests/integration/test_day_rows.py`, `test_direction_arrows.py`)
- [x] T059 Detailed days 1 to 4 and outlook days 5 to 7, from one setting (`models.py` `DETAILED_DAYS`, `OUTLOOK_DAYS`; `gfs.plan_hours`, `gfsmode.py`, `render.py`, template; tests updated)
- [x] T060 [US3] Move the unit selector into a hamburger settings menu in the header (`templates/page.html.j2`; `tests/integration/test_settings_menu.py`)
- [x] T061 Rename the product to Free Flying Forecast everywhere: text, package and command `ffforecast`, environment variables `FFFORECAST_*`, launchd label, spec folder, memory notes
- [x] T062 [US3] Rewrite the Guide from the rules: grades and triggers, factors used, hang glider limits, and what is not graded; every claim tested against the grading (`render.py` legend, template; `tests/integration/test_guide.py`)
- [ ] T063 Decide whether wind shear should affect the grade (it is shown but not graded today)
- [x] T064 [US3] Collapse the Guide; selecting a grade opens it at that grade and highlights it, without toggling the day row (`templates/page.html.j2`; `tests/integration/test_guide.py`)
- [x] T065 [US1] Glider setting (PG default, HG): keep HG reasons and outlook grades in the data, render both gliders and show only the chosen one by CSS, per-glider colours and Guide limits (`models.py`, `diagnostics.py`, `outlook.py`, `render.py`, template; `tests/integration/test_glider_setting.py`)
- [x] T066 Settings kept in a first-party cookie (localStorage fallback), validated and applied before the page is drawn; verified in a real browser: survives a reload, Path follows the site folder, a tampered cookie is ignored (`templates/page.html.j2`; `tests/integration/test_cookie_and_sticky.py`)
- [x] T067 [US1] Pin the header (title, glider toggle, settings, update time, alerts) with spacing beneath and scroll-padding for anchors; glider toggle always visible; grade pill shows only the grade
- [x] T068 [US1] Outlook days use the day-box style with wind arrows (shared arrow macro); heading "Weather Station: last 4 hours" (the owner later changed it to a "FreeFlight WX" link) (`tests/integration/test_outlook_cells.py`)
- [x] T069 [US1] Weather station period toggle (Current/1/4/12/Day) from the site config, links in a new tab, only the chosen chart fetched, period remembered; two real bugs found in a browser and fixed (hidden charts still downloaded; saved period not applied before the chart loaded) (`config.py`, `site.mystic.toml`, template; `tests/integration/test_station_periods.py`)
- [x] T070 [US1] Day details as one table: row headings once in the left column under the date, time columns aligned with the header row (verified 0 px off in a browser), reasons listed per time (`render.py`, template; `tests/integration/test_detail_table.py`)
- [x] T072 Compare the thermal values with AUSRASP-based reference figures and fix the differences: hourly heating (bug), usable thermal height, calibrated quality, XC cut-offs; results in research section 21 (`diagnostics.py`, `outlook.py`, `gfs.py`, `runner.py`, `rules.toml`; `tests/unit/test_flux.py`)
- [x] T073 Acknowledge AUSRASP Victoria and the VHPA in the footer (FR-012e)
- [x] T075 [US3] Collapsed "How the numbers are calculated" section: data sources, each thermal calculation and the limits, with figures from the rules (the "how well it matches" part was removed at the owner's request, along with its `[calibration]` record); also fixed the temperature at thermal height to use the usable height (`render.py`, template, `rules.toml`, `config.py`; `tests/integration/test_method_section.py`)
- [x] T076 [US1] Split "Great" into Good, Great and Pumping: configurable thresholds with validation, tiers in the grading, six icons and colours in both themes, the Guide, the fixture and tests (`grading.py`, `config.py`, `rules.toml`, `render.py`, template; `tests/unit/test_tiers.py`, `tests/integration/test_grade_tiers_ui.py`)
- [x] T077 Marginally off-sector wind no longer caps the grade at Turbulent (owner decision 2026-10-04: a crossed launch can still be flown); it is noted in the reasons and the amber arrow and the thermals decide. Tuning the Good, Great and Pumping thresholds against real days continues under T052 (`grading.py`, `rules.toml`, template; `tests/unit/test_grading.py`, `tests/unit/test_crossed.py`, `tests/integration/test_guide.py`)
- [ ] T074 Re-check the thermal calibration against a second and third snapshot of the reference figures and real flying days (the constants come from one snapshot); consider whether the remaining updraft bias (ours about 16% high) and the quality gap (wind input) need further work
- [ ] T052 Tune the weather thresholds against real days (the starting values are judgement calls)
- [ ] T053 Add rain and gusts to the WRF path (`wrf.py` output reader) so WRF mode grades them too

## Phase 6: Polish

- [x] T037 [P] Write `README.md` covering setup, Colima settings, running, and credits
- [ ] T038 [P] Check accessibility: contrast, text alternatives, phone-width layout, no horizontal scroll
- [ ] T039 Run `ruff`, `pyright` and `pytest` clean; walk through `quickstart.md` steps 5 and 9 on any machine and steps 1 to 4, 6 to 8 on the iMac **[iMac]**

## Dependencies

- Phase 1, then Phase 2, then stories. US1 depends only on Phase 2 and fixtures; US2 and US3 build on US1's render.
- T026 (benchmark) gates the domain and run-length choices in T025, T027.
- Order within US1: T014 to T016 first (tests must fail), then T017 to T023.

## Parallel Examples

- Phase 2: T006, T008, T009, T011, T012 and T013 touch different files.
- US1: T014, T015, T016 and T017, then T018, T019 and T020 in parallel.

## Implementation Strategy

1. Phases 1 and 2, then US1 from fixtures (MVP, runnable on any machine).
2. US3 footer and credits, which are small and already needed by the page.
3. US2 offline parts (state, run logic, publish, scripts, Dockerfile) can be written now.
4. WRF verification and the benchmark need the iMac, so those tasks stay open until run there.

## Where things stand (2026-10-03)

**Done and verified**: everything user-facing in the spec: the page, grading, Guide, settings, cookie,
pinned header, station chart periods, today panel; the GFS-only forecast and the run pipeline
against live data. 212 automated tests, `ruff` and `pyright` clean, plus recorded checks in a real
browser.

**Open, needs the iMac** (T012, T025 to T027, T032, T039): build the WRF image, write the WRF
orchestration and output reader, run the benchmark, and prove the schedule and the sleep-and-wake
catch-up. Until then the GFS-only mode is what runs.

**Open, can be done anywhere**: T038 (accessibility review), T052 (tune the thresholds against real
days), T053 (rain and gusts in the WRF path, after T025 to T027), T063 (should shear affect the
grade?).

**Not started**: the Firebase deployment. Its specification is in
[002](../002-firebase-hosting-deploy/spec.md); `/speckit-plan` and `/speckit-tasks` have not been run
for it, so it has no tasks yet.

