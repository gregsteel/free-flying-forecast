# Tasks: AUSRASP Thermal Source

**Input**: [spec.md](spec.md), [plan.md](plan.md), [research.md](research.md), [data-model.md](data-model.md), [contracts/cli.md](contracts/cli.md)

Format: `- [ ] ID [P?] [Story] Description with file path`. Tests are included (the project's practice).

## Phase 1: Foundations (blocking)

- [x] T001 Add the `[ausrasp]` site section (enabled, base_url, contact, max_cell_km, max_age_h, poll windows) and the `[thermal_ausrasp]` rules section, with validation, in src/ffforecast/config.py, config/site.mystic.toml, config/rules.toml; tests in tests/unit/test_config.py
- [x] T002 Add `thermal_source` and `thermal_run` to ForecastBlock and `thermal_source` to DailyOutlook (optional, default "gfs") in src/ffforecast/models.py; test round trip and reading an old file
- [x] T003 [P] Parse an AUSRASP grid file (header, shape, parameter, unit, `Mult`, range, `Day=` date, model start from valid time and forecast hours) in src/ffforecast/ausrasp.py; tests in tests/unit/test_ausrasp.py
- [x] T004 [P] Find the nearest cell from `latlon2d.json` (cell centres from corner points) and store it in cell.json in src/ffforecast/ausrasp.py; tests
- [x] T005 [P] Pure schedule logic `due(now, last_check, windows, default)` in src/ffforecast/schedule.py; tests in tests/unit/test_schedule.py

## Phase 2: User Story 1 - the page shows AUSRASP's height and updraft (P1)

- [x] T006 [US1] The HTTP client: user agent with contact, gzip, sequential with 1 s pause, request and byte budget (60 an hour, 10 MB a day), 6-hour back-off after a refusal, off switch in src/ffforecast/ausrasp.py; tests with a fake session
- [x] T007 [US1] Fetch a day set (wanted hours for `hglider` and `wstar`), check completeness and the same model start, never replace with an older run, store atomically in cache/ausrasp/days in src/ffforecast/ausrasp.py; tests including partial and mixed days
- [x] T008 [US1] Selection: `thermal_lookup(store, now, max_age_h)` returning `{utc hour: Thermal}` for fresh complete days in src/ffforecast/ausrasp.py; tests (age, DST, hour mapping)
- [x] T009 [US1] Let build_block take an AUSRASP Thermal (height, updraft, run), recompute quality, temperature at height, XC rating and verdicts, and set the source fields in src/ffforecast/diagnostics.py; tests in tests/unit/test_thermal_override.py
- [x] T010 [US1] Use the lookup in blocks and in the day outlook in src/ffforecast/gfsmode.py and src/ffforecast/outlook.py (block hour match by UTC; outlook averages at least two block hours); tests
- [x] T011 [US1] Add an "ausrasp" stage before "diagnose" in src/ffforecast/runner.py and pass the lookup into the blocks; failures fall back with a note; integration test in tests/integration/test_ausrasp_run.py

## Phase 3: User Story 2 - following AUSRASP's updates (P1)

- [x] T012 [US2] Manifest read and compare, stamp log, status file in src/ffforecast/ausrasp.py; tests (no change, one change, several, partial day kept)
- [x] T013 [US2] The `poll` command (`--if-due`, `--no-rebuild`), one rebuild per check using the stored GFS cycle with force, in src/ffforecast/cli.py and src/ffforecast/runner.py; tests in tests/integration/test_poll.py
- [x] T014 [P] [US2] launchd job every 20 minutes: scripts/ffforecast-poll-launchd.plist and a note in README.md

## Phase 4: User Story 3 - fallback (P2)

- [x] T015 [US3] Reasons recorded when AUSRASP is unavailable (unreachable, rejected, too old, off, back-off) and shown in the status; the page labels estimate blocks in src/ffforecast/ausrasp.py, src/ffforecast/render.py; tests for each reason

## Phase 5: User Story 4 - grades with whole-number updraft (P2)

- [x] T016 [US4] `grade_block` takes the Good and Strong updraft thresholds; AUSRASP blocks use `[thermal_ausrasp]` in src/ffforecast/grading.py; tests for updrafts 0 to 5 in tests/unit/test_grading.py
- [x] T017 [US4] Page: a "Thermal figures" row per block (source and run time), Guide and method text for the source in use (whole-number thresholds), unrounded updraft shown as published, in templates/page.html.j2 and src/ffforecast/render.py; tests in tests/integration/test_ausrasp_ui.py

## Phase 6: User Story 5 - polite use and credit (P3)

- [x] T018 [US5] Footer and method wording: thermal figures are AUSRASP's, VHPA credit, donations, in templates/page.html.j2; update the existing footer and method tests
- [x] T019 [US5] Counters and ceilings visible in status; test that a day of polling stays within budget in tests/integration/test_poll.py

## Phase 7: Polish

- [x] T020 [P] Live test reading the real manifest and one grid (needs `FFF_NETWORK=1`) in tests/integration/test_ausrasp_live.py; run it once and record the result in research.md
- [x] T021 Regenerate fixtures (tests/make_fixture.py) and update the Guide, footer and method tests; ruff, pyright and the whole suite green
- [x] T022 Update README.md, specs/001 plan and data-model/contracts for the new fields, and the task list; end-to-end run against live data and record it in research.md
- [ ] T023 [P] After a week of stamps: review cache/ausrasp/stamps.jsonl against the poll windows and adjust (owner follow-up; not blocking)
