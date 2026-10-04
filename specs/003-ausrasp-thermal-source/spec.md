# Feature Specification: AUSRASP Thermal Source

**Feature Branch**: `003-ausrasp-thermal-source`

**Created**: 2026-10-03

**Status**: Built and tested on 2026-10-03 (live read and one full run against real data); the polling schedule and the whole-number tier limits still need the owner's review (tasks T023, FR-021)

**Input**: User description: "Use AUSRASP's published forecast values for thermal height and updraft instead of deriving them from the global model. Do not use AUSRASP for wind or rain. Poll periodically to detect when AUSRASP's data changes, aligned with its schedule if there is one."

**Builds on**: [001 Free Flying Forecast](../001-free-flying-forecast/spec.md) (page, grading, run pipeline) and works with [002 Firebase deployment](../002-firebase-hosting-deploy/spec.md) (making each refreshed page public).

## Why this change

The owner compared the page's thermal height and updraft with the AUSRASP maps for Mystic and found them different. The page estimates thermals from a 25 km global model; AUSRASP runs a 4 km regional model with its own terrain and surface heating, and its maps are the forecast the owner's club already uses and trusts. Matching it exactly is not possible by recalculation (the inputs differ, and the original program's licence forbids copying it), so the page should show AUSRASP's own values for Mystic.

What was learned on 2026-10-03 (see [research.md](../001-free-flying-forecast/research.md) section 23 once recorded):

- AUSRASP publishes the numbers behind its Victoria maps as plain-text grids (4 km cells, 144 by 144), one file per quantity, day and hour, plus a file giving each cell's position. The nearest cell to the Mystic launch is about 0.8 km away.
- Thermalling height is published in metres above sea level and already allows for cloudbase. Updraft is published only in whole metres per second.
- Hours are 0800 to 1800 on AUSRASP's own clock for today and the next six days. That clock is labelled AES (Australian Eastern Standard, UTC+10) or AED (Daylight, UTC+11) in each file's header, and **which one depends on when the run was made, not on the date it is for**: runs made before daylight saving began (16:00Z on 3 October 2026) label every day in AES, runs made after it label every day in AED. (This was first assumed to be a fixed UTC+10 clock; the 4 October update showed otherwise.)
- A small manifest file lists, for each of the seven days, a stamp that changes when that day is re-run. Each day is re-run on its own, from either the 00Z or the 12Z global-model cycle. On the day examined the days were stamped between 10:52Z and 19:35Z on 2 October and 04:51Z on 3 October, and one day was still from a run 35 hours older than the rest.
- No terms of use, permission statement or contact address could be found on the site (its disclaimer page returns "not found").

## User Scenarios & Testing *(mandatory)*

### User Story 1 - The page shows AUSRASP's thermal height and updraft for Mystic (Priority: P1)

A pilot opens the page and sees, for each forecast block that falls in AUSRASP's hours, the thermal height and thermal updraft that AUSRASP forecasts at Mystic, clearly labelled as coming from AUSRASP, with the time of the AUSRASP run they come from. The grade (Ok, Good, Strong, Poor and so on) uses these values.

**Why this priority**: This is the whole point of the change: the page's thermals match the forecast the owner trusts.

**Independent Test**: Take a saved copy of AUSRASP's files for one day. Build the page, then look up the nearest cell by hand for three hours and compare; the page's height and updraft equal those cell values (height in the page's chosen units).

**Acceptance Scenarios**:

1. **Given** AUSRASP's data for a day, **When** the page is built, **Then** each block's thermal height and updraft equal the values of the cell nearest the launch for the hour that block represents.
2. **Given** the page's units setting, **When** it is changed, **Then** the AUSRASP height and updraft follow it like every other figure.
3. **Given** a block, **When** the pilot opens its details, **Then** the page says the thermal figures are AUSRASP's, names the run (its model start time) and links to AUSRASP and the VHPA as it already does.
4. **Given** the launch is on a mountain and the nearest cell reads lower than the cells around it, **When** values are read, **Then** the page uses the highest height and the highest updraft in the 3 by 3 block of cells around the launch, not the nearest cell alone and not an average.

---

### User Story 2 - The page follows AUSRASP's updates (Priority: P1)

AUSRASP re-runs each of its seven days at different times. The system checks the manifest on a schedule, notices which days have changed, fetches only those, rebuilds the page and (once 002 is live) publishes it, so that the page is never left showing an old AUSRASP run for longer than necessary, and nobody has to remember to refresh it.

**Why this priority**: AUSRASP values go stale within hours; without this the main feature would quietly show old thermals.

**Independent Test**: Run the check twice with the manifest unchanged (nothing fetched, no rebuild), then change one day's stamp in a test copy and run it again (only that day is fetched and the page is rebuilt with it).

**Acceptance Scenarios**:

1. **Given** no day's stamp has changed since the last check, **When** the check runs, **Then** it fetches only the manifest and does not rebuild or publish.
2. **Given** one day's stamp has changed, **When** the check runs, **Then** only that day's files are fetched, the page is rebuilt from them and the other days' saved values, and (when deployment exists) published once.
3. **Given** several days changed in the same check, **When** the page is rebuilt, **Then** there is one rebuild and one publish, not one per day.
4. **Given** a day's files are still being written (some hours or quantities missing or unreadable), **When** the check runs, **Then** that day is not used yet and is checked again at the next poll; a half-updated day is never shown.
5. **Given** the check ran just before the scheduled global-model update, **When** it runs, **Then** the existing GFS-based parts of the page are refreshed on their own schedule and are not blocked by the AUSRASP check, nor the other way round.

---

### User Story 3 - The page keeps working when AUSRASP is not available (Priority: P2)

If AUSRASP's files cannot be reached, are missing for a day, are older than allowed, or have changed shape, the page still builds. Where AUSRASP values are not available it falls back to the thermal estimate from the global model that the page already has, says so, and never shows a gap or an error.

**Why this priority**: The data comes from an unofficial public source that may change or vanish; the forecast must not depend on it. The fallback already exists, so this is cheap and protects the owner.

**Independent Test**: Block the AUSRASP address, rebuild the page and confirm it shows the global-model values with a clear "estimate" label; restore access and confirm the AUSRASP values return at the next check.

**Acceptance Scenarios**:

1. **Given** AUSRASP cannot be reached, **When** the page is built, **Then** thermal figures come from the global-model estimate, are labelled as such, and the run succeeds.
2. **Given** one day is missing or unreadable but others are fine, **When** the page is built, **Then** AUSRASP values are used for the good days and the estimate for the bad day, and each day says which it is.
3. **Given** a day's AUSRASP run is older than the allowed age (default 36 hours of model start time), **When** the page is built, **Then** the page uses the estimate for that day and says why.
4. **Given** AUSRASP's grid description or file format no longer matches what the system expects (for example a different grid size or unit), **When** a file is read, **Then** the file is rejected, the estimate is used, and the problem is recorded for the owner.
5. **Given** the fallback is in use, **When** the owner views the owner-only status, **Then** the reason and the time it began are visible.

---

### User Story 4 - Grades still make sense with a whole-number updraft (Priority: P2)

AUSRASP's updraft is published in whole metres per second, so the page can only know "1, 2, 3, 4". The Ok, Good and Strong grades, and the "quality" percentage, are decided in a way that is stated in the Guide and does not pretend to more precision than the data has.

**Why this priority**: Without this the tiers would silently change meaning (for example "Good needs 2.5 m/s" becomes "3 or more").

**Independent Test**: Feed whole-number updrafts 0 to 5 with a calm wind and confirm each maps to the grade the Guide states; confirm the Guide text matches.

**Acceptance Scenarios**:

1. **Given** an AUSRASP updraft of 0 to 5 m/s and no wind, rain or other problem, **When** the block is graded, **Then** the grade follows the thresholds in the rules file, applied to the whole-number value, and the Guide states the same thresholds in whole numbers when AUSRASP is the source.
2. **Given** the grade is decided from a whole-number updraft, **When** the page shows the updraft, **Then** it shows it as published (no false decimals) and says it is rounded.
3. **Given** wind, gusts, rain or storms are a problem, **When** the block is graded, **Then** the problem still wins over thermals, exactly as before.

---

### User Story 5 - AUSRASP is used politely and credited (Priority: P3)

The system asks AUSRASP for as little as it can, identifies itself, can be switched off with one setting, and credits AUSRASP and the VHPA on the page.

**Why this priority**: AUSRASP is a volunteer-run, donation-funded service with no stated terms for automated use. Keeping the load tiny and the credit visible is the minimum respect for it, and a switch lets the owner stop at once if asked.

**Independent Test**: Run a full day of checks against a recording of AUSRASP and count the requests, bytes and identification sent.

**Acceptance Scenarios**:

1. **Given** a day of polling, **When** requests are counted, **Then** they stay within the budget stated in the requirements.
2. **Given** a request is sent, **When** it is inspected, **Then** it carries a clear identification of this project and a contact point chosen by the owner.
3. **Given** the owner turns the AUSRASP source off in configuration, **When** the next page is built, **Then** nothing is fetched from AUSRASP and the page shows the estimate, labelled as such.
4. **Given** AUSRASP responds with an error asking for fewer requests or refuses access, **When** the system sees it, **Then** it backs off for hours (not minutes) and uses the estimate meanwhile.

---

### Edge Cases

- The nearest cell changes because AUSRASP changes its grid or position file.
- A day's files arrive in pieces over several minutes (the manifest should change only when complete, but the system must not assume it).
- The manifest is reachable but a data file is not, or the reverse.
- The manifest stamp changes but the data is identical (nothing visible changes; the page may rebuild without difference).
- A day is re-run from an older global-model cycle than one already stored (the older run must not replace the newer one).
- Daylight saving begins or ends (4 October 2026 is the first case): AUSRASP labels a run's files in standard or daylight time depending on when the run was made, so the same instant is "1000" in one run and "1100" in the next. Every file's real valid time must be taken from its own header (local hour and UTC hour) and matched to the block by absolute time, never by the clock face or by an assumed offset.
- A page block straddles two AUSRASP hours, or falls outside AUSRASP's 0800 to 1800 hours (early morning and evening blocks).
- AUSRASP reports height at or below the launch height (no usable thermals); the page must show "no thermals" rather than a height lower than the ground.
- The owner's computer is asleep during the best polling windows (the check runs when it wakes, and is not lost).
- AUSRASP is down for days.
- The same day appears in two states at once during a re-run (old files and new files mixed).
- Values outside a believable range (for example a negative height or an updraft over 10 m/s).

## Requirements *(mandatory)*

### Functional Requirements

**What is taken from AUSRASP, and what is not**

- **FR-001**: The system MUST take only two quantities from AUSRASP for the page's thermal figures: thermalling height (metres above sea level, including the cloudbase limit) and thermal updraft velocity (whole metres per second). Nothing else from AUSRASP MAY be used in the forecast or grading.
- **FR-002**: The system MUST NOT use AUSRASP for wind (speed, direction or gusts, at the surface or at launch altitude) or for rain (nor for CAPE, temperature or cloud). Those continue to come from the global model as in 001.
- **FR-003**: Thermal "quality" (001 FR on thermal quality) MUST continue to be calculated by the existing formula, now from AUSRASP's updraft and the global model's launch-altitude wind.
- **FR-004**: The page MUST show, for every block, which source its thermal figures came from (AUSRASP or the global-model estimate).
- **FR-004a**: When AUSRASP is the source, the page MUST show the whole-number updraft as published, without added decimals, and MUST NOT present quality, height or tier decisions as more precise than that.

**Locating Mystic**

- **FR-005**: The system MUST find the grid cell nearest the configured launch position from AUSRASP's own cell-position file, and MUST use the highest value among the block of cells around it (default: that cell and the ring of eight around it, a 3 by 3 block about 12 km square), taking the highest height and the highest updraft separately. The size of the block MUST be a setting (0 means the nearest cell alone), and a day stored for a different block size MUST be fetched again. The system MUST NOT average or interpolate between cells. The page MUST say that the highest value in a block is used.
- **FR-006**: The system MUST record, with each forecast, which cell was used (its position and distance from the launch), and MUST reject the data if that distance exceeds a configured limit (default 3 km).
- **FR-007**: Heights MUST be treated as metres above sea level. A height at or below the launch altitude MUST be shown as "no usable thermals", not as a height.

**Hours and time**

- **FR-008**: The system MUST match page blocks to AUSRASP's hours by absolute time (UTC), reading each file's valid time from its own header (AUSRASP's clock is UTC+10 or UTC+11 depending on the run), including across the start and end of daylight saving, and MUST reject a file whose valid time is not the one asked for.
- **FR-009**: Each block MUST use the AUSRASP hour valid at the block's time (the page's blocks are hourly, 10:00 to 18:00), the time the page shows for it (as the global-model values already are), and the method section MUST say so. A day outlook (days 5 to 7) MUST use the average of the AUSRASP hours that fall on the page's hourly block times that day, when at least two are available.
- **FR-010**: A block whose hour is outside AUSRASP's published hours (0800 to 1800 on AUSRASP's clock) MUST use the global-model estimate and be labelled as such (FR-016).

**Detecting changes (polling)**

- **FR-011**: The system MUST detect new AUSRASP data by reading AUSRASP's per-day manifest, which is small and not cached, and MUST fetch a day's data files only when that day's stamp differs from the one last stored.
- **FR-012**: Polling MUST follow a schedule held in configuration. The default schedule MUST be aligned with when AUSRASP's runs have been observed to finish: a frequent check (every 20 minutes) from 04:30Z to 09:00Z and from 16:00Z to 21:00Z, which brackets the completion of runs started from the 00Z and 12Z global-model cycles, and an infrequent check (every 3 hours) at other times.
- **FR-013**: The observed times above come from one day's examination and are NOT established as AUSRASP's schedule. The system MUST log every stamp change it sees (day, old stamp, new stamp, time noticed, and the model start time found in the data), so that the owner can review at least 7 days of this log and adjust the schedule.
- **FR-014**: A day's files MUST only be used when all the hours and both quantities needed for that day are present, valid and from the same model start time. Otherwise the previous complete set for that day MUST stay in use and the day MUST be checked again at the next poll.
- **FR-015**: One check that finds several changed days MUST result in one page rebuild and (with 002) one publication. A rebuild MUST NOT repeat the global-model download or recalculation; it reuses what the last run stored, and the global-model schedule MUST be unaffected by the AUSRASP polling.
- **FR-015a**: A day MUST NOT be replaced by data from an older model start time than the one already stored for it.
- **FR-015b**: The most recent complete set for each day MUST be stored locally so that a rebuild needs no network access to AUSRASP, and so that a missed poll (for example computer asleep) loses nothing.

**Fallback and staleness**

- **FR-016**: Where AUSRASP values are not available for a block (unreachable, incomplete, rejected, too old, source turned off), the system MUST use the existing global-model estimate for that block, MUST label the block as an estimate, and MUST still complete the run successfully.
- **FR-017**: AUSRASP data whose model start time is older than a configured age (default 36 hours) MUST NOT be used.
- **FR-018**: Each file read MUST be checked for the expected grid size, the expected quantity and unit, and a believable value range (height between 0 and 5,000 m; updraft between 0 and 10 m/s). A file that fails MUST be rejected whole, recorded, and treated as unavailable.
- **FR-019**: The owner-only status (001/002) MUST show, for AUSRASP: the stamp and model start time held for each day, the time of the last successful and last attempted check, whether the fallback is in use and why.

**Grading with whole-number updraft**

- **FR-020**: The tiers Ok, Good and Strong MUST be decided from the whole-number AUSRASP updraft using thresholds held in the rules file, separate from the thresholds used for the global-model estimate.
- **FR-021**: The default AUSRASP thresholds MUST be: Good at an updraft of 3 m/s or more (the owner's rule that Good needs at least 2.5 m/s, applied to whole numbers) and Strong at 4 m/s or more, with the existing quality threshold for Ok. These defaults MUST be confirmed by the owner against real days before they are relied on.
- **FR-022**: The Guide and the page's method section MUST state the thresholds in use for the current source, in whole numbers when AUSRASP is the source, and MUST be generated from the rules file as today.
- **FR-023**: Wind, gust, direction, rain and storm problems MUST continue to take precedence over thermals when grading, unchanged from 001.

**Respect for the source**

- **FR-024**: Only the hours the page needs MUST be fetched (the nine hourly block times of each day, two quantities each), asking for compressed transfer, one request at a time with a pause of at least 1 second between requests. The system MUST send no more than 60 requests to AUSRASP in any one hour and MUST keep total transfer under 10 MB per day, counted and recorded; when a limit would be exceeded the rest is left until the limit allows.
- **FR-025**: Every request MUST identify the project by name and give a contact point supplied by the owner in configuration.
- **FR-026**: A single configuration setting MUST turn the AUSRASP source off entirely; when off, no request MUST be made to AUSRASP.
- **FR-027**: On a refusal or a request to slow down from AUSRASP, the system MUST stop requesting for at least 6 hours and use the estimate in the meantime.
- **FR-028**: The page MUST keep crediting AUSRASP, naming its operators' supporters for Victoria (the VHPA), saying that AUSRASP is run on donations and linking to its donations route as in 001, and MUST state that the thermal figures are AUSRASP's, not the project's own forecast.
- **FR-029**: The system MUST NOT copy, redistribute or republish AUSRASP's maps, images or raw grids; it MUST show only the Mystic values and link to AUSRASP for the maps.
- **FR-030**: The data format being relied on is not a published interface. The system MUST treat every change in it as a normal event (FR-016, FR-018), never as a failure of the run.

### Key Entities

- **AUSRASP Day Set**: The files for one AUSRASP day and region: the day, the stamp from the manifest, the model start time, the time fetched, the hours present, whether complete, the Mystic cell values by hour.
- **AUSRASP Manifest Snapshot**: What the manifest said at a check: the stamp for each of the seven days and the time it was read.
- **Mystic Cell**: The grid cell nearest the launch, with its position, its distance from the launch and the grid it belongs to, and the block of cells around it that is read.
- **Thermal Figure**: A block's thermal height and updraft with their source (AUSRASP or estimate), model start time, and the reason if it is an estimate.
- **Poll Schedule**: The windows and intervals at which the manifest is checked, held in configuration.
- **Stamp Log**: The record of every stamp change noticed.
- **Source Status**: The owner-only summary of whether AUSRASP is in use, last success, last attempt and reason for any fallback.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For 100% of blocks inside AUSRASP's hours when its data is available, the page's thermal height and updraft equal the nearest-cell values in AUSRASP's files for the matching hour (checked on at least three different days).
- **SC-002**: After AUSRASP finishes re-running a day, the page reflects it within 40 minutes during the frequent-polling windows and within 3 hours at other times.
- **SC-003**: With AUSRASP unreachable, 100% of page builds still succeed and every block shows a thermal figure source label.
- **SC-004**: In 100% of tested bad-data cases (wrong grid size, wrong unit, truncated file, out-of-range value, older model start time, mixed old and new files) no bad value reaches the page.
- **SC-005**: Over a day of normal operation the system sends no more than 150 requests in any hour and transfers under 25 MB.
- **SC-006**: After 7 days of logging, the owner can read from the stamp log when each AUSRASP day was re-run, and the polling schedule has been checked against it and adjusted if it was wrong.
- **SC-007**: On a sample of at least 10 flying days chosen by the owner, the owner judges the AUSRASP-based page to agree with their experience at least as well as the previous estimate did.
- **SC-008**: The page's thermal figures for any block can be traced, in the owner-only status, to a particular AUSRASP run and cell.

## Assumptions

- AUSRASP's Victoria forecast continues to be published at its current address and in its current format; this cannot be assured, which is why the fallback is required.
- The owner has decided to use AUSRASP's thermal values and not to use it for wind or rain (decision of 2026-10-03). No statement of terms or permission could be found on AUSRASP's site, and its operator could not be contacted by the project; the owner may choose to approach AUSRASP through the VHPA. The design keeps load very low, credits the source, can be switched off at once, and keeps the fallback so that withdrawal of the data would not break the page.
- The owner asked (2026-10-03) for the highest of the cells surrounding the launch, because the launch is on a mountain and the nearest cell can read low (neighbouring cells differ by several hundred metres). "Surrounding" is taken as the nearest cell and its eight neighbours; the block size is a setting. The highest height and the highest updraft are each taken separately, so they may come from different cells. This will tend to read higher than a single cell; the owner has judged that acceptable.
- "Thermalling height" (the lowest of the height where updraft falls to 225 feet per minute, cumulus cloudbase and over-development cloudbase) is the figure to show as thermal height, because it is the one AUSRASP's own map labels "Thermalling Height".
- Whole-number updraft is a limitation of the published data, not of the project. Sorting days into Ok, Good and Strong will be coarser than before.
- Today's page already stores the global-model values for each run, so a rebuild with new AUSRASP values can reuse them (001 run pipeline).
- The poll windows in FR-012 are a starting guess drawn from one day's observations (stamps between 10:52Z and 19:35Z on 2 October and 04:51Z on 3 October, consistent with 12Z and 00Z cycles). They are to be checked against the stamp log (FR-013) and revised.
- Publishing the refreshed page is done by the deployment in 002; until that exists, the existing interim publisher is used.
- The page's wind and rain handling, grades other than thermal tiers, units, settings and layout are unchanged.

## Out of Scope

- Using AUSRASP for wind, rain, gusts, CAPE, temperature, cloud, soundings or any other quantity.
- Showing, copying or hosting AUSRASP's maps, images, meteograms or raw grids.
- Other AUSRASP regions, other sites, or other launch points.
- Recalculating AUSRASP's values or copying its program.
- Running our own regional model (001 WRF work remains separate and is not affected).
- Asking AUSRASP's operators for permission (a decision for the owner).
