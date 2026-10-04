# Feature Specification: Free Flying Forecast

**Feature Branch**: `001-free-flying-forecast`

**Created**: 2026-10-03

**Last updated**: 2026-10-03 (brought in line with what is built)

**Status**: In progress. The forecast page, grading, settings and GFS-only forecast mode are built and tested. The regional model (WRF), the home-computer schedule and the public deployment are not yet verified or built; see `tasks.md` and [002 Firebase Hosting Deployment](../002-firebase-hosting-deploy/spec.md).

**Input**: User description: "Free Flying Forecast: a self-hosted daily soaring forecast for Mystic, VIC. It downloads a GFS subset from NOAA, runs WRF in Docker on Colima (M4 iMac, 16 GB), computes thermal and wind diagnostics, grades each 2-hour block, and publishes a static, mobile-friendly HTML page for paraglider and hang glider pilots."

How to read this document: requirement numbers (FR-nnn, SC-nnn) are stable identifiers used by tests, tasks and notes. They were assigned as the feature grew, so they are grouped by topic here rather than numbered in order.

## Decisions Log

Decisions made with the owner while the feature was specified and built. Where a later decision replaced an earlier one, the earlier one is shown as *superseded*.

**What the forecast covers**

- Detailed forecast: **days 1 to 4**, in **hourly blocks from 10:00 to 18:00** local time (changed from 2-hour blocks at 11, 13, 15 and 17 on 2026-10-04 at the owner's request). Days 5 to 7: a simpler, low-confidence daily outlook. (*Superseded*: an earlier split of days 1 to 3 and 4 to 7.) The split is one setting in the code.
- Site: **Mystic launch, VIC**, at -36.7584, 146.9658, **800 m above sea level** (the owner's figure, replacing a 785 m terrain-model estimate). Wind at launch altitude is a core value.
- XC potential was dropped from the page on 2026-10-04 at the owner's request (it did not help); no XC rating or distance figures are shown.
- **Rain, thunderstorms and gusts are graded.** A real thunderstorm day (3 Oct 2026) was first graded "good" because they were ignored.
- A collapsed **"How the numbers are calculated"** section explains the data sources, the thermal calculations and the limits, from the rules in force (FR-025). It has no "how well it matches" part.
- The grading rules start from the **North East Victorian Hang Gliding Club (NEVHGC) FreeFlightWx Mystic site settings** (wind bands and a green direction sector), then are tuned against real flying days. (*Superseded*: an earlier plan to copy the bands of the forecast service this replaces.)
- **Grades**: six, not four, and renamed by the owner on 2026-10-04 (Good became **Ok**, Great became **Good**, Pumping became **Strong**): **Ok** (flyable, decent thermals), **Good** ("a time you definitely want to go flying") and **Strong** (powerful; it demands experience). Poor, Turbulent and Dangerous are unchanged. Good needs an updraft of 2.5 m/s (the owner's figure; 1.7 m/s is only Ok) and Strong 3.5 m/s (a starting value to tune, task T052).
- Missed scheduled runs **catch up** when the computer wakes; a cycle is never run twice.
- A **GFS-only mode** (25 km global model, no regional model) was built first and stays as the fallback if the regional model fails.

**How the page is presented**

- Weather on the left (today's conditions and an hourly forecast for the rest of today), the weather station chart on the right at about half the page width; stacked on phones.
- The station chart has a **period toggle** (Current, 1 hr, 4 hr, 12 hr, Day; 4 hr first), under a heading "FreeFlight WX" that links to the station. Links to the station pages open in a **new tab**. (*Superseded*: an embedded live gauge, then a fixed 4-hour chart.)
- Each day is **one expandable row**: day at the left, four time columns. Collapsed, each time shows only the **grade icon, thermal height and launch wind** (a coloured triangle). Expanded, one **table** with row headings once in the left column under the date. (*Superseded*: separate cards per time, and a header that showed PG and HG labels or grade words.)
- Days 5 to 7 use the **same box style** as the day boxes, three across, with wind arrows.
- The **title bar, glider toggle, settings menu, update time and alerts are pinned** at the top.
- The **Guide** is collapsed; selecting any grade opens it at that grade.
- The wind arrow colour (green, amber, red) follows the flyable direction sector.

**Settings**

- **Glider type** (paraglider, the default, or hang glider) is always visible beside the settings button; everything glider-specific shows only for the chosen type. (*Superseded*: showing both, then PG only.)
- **Units** live in the settings menu: wind in knots (default) or km/h, height in metres (default) or feet, temperature in Celsius (default) or Fahrenheit. (*Superseded*: four wind units; units in a bar on the page.)
- Settings, and the chosen station chart period, are remembered in a **first-party cookie** with local storage as a fallback.

**Names and hosting**

- The product is **Free Flying Forecast**; the short code name is `ffforecast`. In the page, "PG" and "HG" mean paraglider and hang glider grades. (*Superseded*: the working name "PG Forecast".)
- Public hosting is **GitHub Pages**, fed by the git publisher (FR-005a): the owner went back to it on 2026-10-04. (*Superseded*: Firebase Hosting, specified in [002](../002-firebase-hosting-deploy/spec.md), which is kept for reference.)

**Source notes**

- The FreeFlightWx Mystic site settings give: wind bands (green from 1 mph, orange from 12 mph, red from 14 mph) and a green direction sector (centre 0 degrees, half-width 40 degrees), calibrated for an intermediate pilot on a low-end B paraglider.
- BoM warnings cannot be fetched by program, so the page links to the official warnings.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - See the coming days' flying conditions at a glance (Priority: P1)

A paraglider or hang glider pilot opens Free Flying Forecast on their phone, the evening before or on the morning of a possible flying day. They see the next 4 days in 2-hour blocks, each with a clear grade, followed by a low-confidence outlook for days 5 to 7, and can quickly decide which day and time is worth flying at Mystic. Rain, storms and strong gusts are not missed.

**Why this priority**: This is the whole product. A readable, trustworthy page replaces the existing forecast the pilot relies on.

**Independent Test**: With a pre-computed set of forecast values for Mystic, generate the page and confirm all 4 detailed days and the 3 outlook days show their grades and values and are readable on a phone-width screen.

**Acceptance Scenarios**:

1. **Given** a completed forecast run, **When** the pilot opens the page, **Then** they see 4 days of hourly blocks (10:00 to 18:00), each with wind at launch altitude, ground wind, wind aloft, shear, thermal height, thermal quality, updraft, temperatures, gusts and rain, followed by a daily outlook for days 5 to 7 labelled low confidence.
2. **Given** a block with strong or dangerous winds, rain or a thunderstorm risk, **When** the page is shown, **Then** it is clearly marked unsuitable and the reasons are stated in words, not only by colour.
3. **Given** a phone-width screen, **When** the page loads, **Then** it is fully readable without horizontal scrolling or zooming, and a whole day fits across one row.
4. **Given** rain or storms are possible in any shown day, **When** the page loads, **Then** a notice names the days and links to the official Bureau of Meteorology warnings.
5. **Given** today's weather matters before flying, **When** the page loads, **Then** the pilot sees current conditions and an hourly forecast for the rest of today, and the weather station's recent wind chart.

---

### User Story 2 - The forecast refreshes itself every day (Priority: P2)

The forecast is recalculated automatically each day from the latest weather model data, with no action from the owner. If new data is late or a run fails, the pilot still sees the last good forecast, labelled with when it was produced.

**Why this priority**: A forecast that needs hand-holding goes stale, which is the problem with the service it replaces.

**Independent Test**: Simulate a failed run and a late data cycle; confirm the previous page remains, its age is shown, and the failure is recorded for the owner.

**Acceptance Scenarios**:

1. **Given** a normal day, **When** the scheduled time passes, **Then** the page is updated with a new run without manual input.
2. **Given** the data for the expected cycle is not yet published, **When** the run starts, **Then** it retries for a bounded time and falls back to the previous good forecast if the data never arrives.
3. **Given** a run fails part way, **When** the pilot opens the page, **Then** they see the last good forecast with its production time and an indication that it is out of date.
4. **Given** the computer was asleep at the scheduled time, **When** it next wakes, **Then** one run catches up, and a cycle already published is not run again.

---

### User Story 3 - Understand and trust the grades (Priority: P3)

A pilot can see where the forecast came from, when it was made and exactly what each grade means, and understands it is advisory. The owner can change the thresholds behind each grade without changing the program.

**Why this priority**: It builds trust and lets the owner tune the forecast to local experience.

**Independent Test**: Change a threshold in the configuration and regenerate; confirm the affected grades change and the Guide still matches.

**Acceptance Scenarios**:

1. **Given** any page, **When** the pilot reads the footer, **Then** they see the data source, model run time, validity period, an advisory notice and credits with working links.
2. **Given** an edited threshold, **When** the page is regenerated, **Then** grades and the Guide both reflect it, with no code change.
3. **Given** the pilot selects a grade anywhere, **When** the Guide opens, **Then** it shows that grade for the chosen glider, highlighted, with the real thresholds, what is taken into account and what is not (turbulence is inferred, shear is shown but not graded).

---

### User Story 4 - Show it my way (Priority: P2)

A pilot chooses whether they fly a paraglider or a hang glider, and the units they prefer, and the page remembers this on their phone. Only what is relevant to their glider is shown.

**Why this priority**: Hang gliders and paragliders have different wind limits, and pilots read speeds in different units; a page showing both is noisier and easier to misread.

**Independent Test**: Choose hang glider, km/h, feet and Fahrenheit; confirm every glider-specific grade and every value changes; reload and confirm the choices are still applied with no flash of the defaults.

**Acceptance Scenarios**:

1. **Given** a first visit, **When** the page loads, **Then** paraglider, knots, metres and Celsius are chosen, and the glider toggle is visible without opening any menu.
2. **Given** the pilot changes glider or a unit, **When** they look at the page, **Then** the grades, reasons, colours, outlook, Guide limits and every value update immediately with no reload.
3. **Given** the pilot returns later, **When** the page loads, **Then** their choices, including the weather station period, are already applied.
4. **Given** cookies are blocked, **When** the pilot changes a setting, **Then** it still takes effect for the visit and the page keeps working.

---

### Edge Cases

- The weather data for the latest cycle is missing, partial or corrupt.
- The run takes much longer than expected and overlaps the next scheduled run.
- The computer is asleep or off at the scheduled time (the run catches up on wake, FR-008a).
- Winds or thermal values fall exactly on a threshold boundary.
- Night-time or very early blocks where thermals are not meaningful.
- The forecast is older than a day or two when the pilot views it.
- Disk space runs low from accumulated old runs.
- Scripting is turned off: the forecast, grades, glider and unit choices still work; the optional extras (current conditions, remembering settings, the out-of-date banner, opening the Guide from a grade) do not.
- The weather station or the current-conditions provider is unreachable: the forecast is unaffected and those parts stay empty or hidden.
- Cookies are blocked or the saved cookie has been altered: settings fall back or are ignored safely.
- A forecast produced before hang glider data existed is shown: paraglider values are used for hang gliders.
- The wet-weather notice is needed but only the outlook days are wet.

## Requirements *(mandatory)*

### Functional Requirements

**Forecast content**

- **FR-001**: The system MUST produce a detailed forecast for Mystic, VIC covering the next 4 days in hourly blocks from 1000 to 1800 local time, and a simpler daily outlook for days 5 to 7.
- **FR-001a**: The days 5 to 7 outlook MUST show wind and an overall grade per day, and MUST be visibly labelled as low confidence.
- **FR-002**: For each detailed block (days 1 to 4) the system MUST report wind speed and direction on the ground and aloft, vertical wind shear, thermal height, thermal quality, updraft strength and temperature on the ground and aloft. "Thermal height" MUST mean the height usable thermals reach (the launch altitude when the updraft is below the critical value of 225 ft/min, 1.1 m/s or about 3.8 ft/sec), not the top of the boundary layer; the heating used MUST be the heating at that hour, not an average over a longer window; and the constants involved MUST be in configuration with their source.
- **FR-003**: The system MUST grade each block as Ok, Good, Strong, Poor, Turbulent or Dangerous and state the reasons in words. Poor, Turbulent and Dangerous are set by the worst problem found (wind, direction, gusts, rain, storms, weak or low thermals). With no problem, the thermals decide: Ok (decent thermals), Good ("a time you definitely want to go flying": strong, workable thermals) or Strong (powerful: very strong thermals, or strong thermals with a brisk wind; it demands experience and is not for novices). The thresholds that separate them MUST be in configuration, differ by glider type where wind is involved, and no good thermals may ever hide a problem.
- **FR-004**: The system MUST grade wind suitability separately for paragliders and hang gliders.
- **FR-013**: The forecast location, launch altitude and weather station chart periods MUST be defined in configuration so further sites can be added without code changes.
- **FR-017**: The forecast MUST account for rain, thunderstorms and gusts. Each block MUST show rain and gusts. Rain at or above a light threshold MUST cap the grade at "poor"; heavy rain, a thunderstorm risk or gusts in the red band MUST give "dangerous"; moderate storm energy without rain, or gusts in the orange band, MUST give "turbulent". Thresholds MUST be in configuration.
- **FR-020**: Each block MUST include the wind speed and direction at launch altitude (800 m above sea level for Mystic, held in the site configuration). The grade MUST be judged on this wind (direction, and speed together with the stronger lower-level wind) whenever it is available.

**Grading rules and the Guide**

- **FR-012**: Grade thresholds MUST be adjustable in configuration without changing program code.
- **FR-012a**: The initial grading rules MUST be seeded from the NEVHGC FreeFlightWx Mystic site settings and recorded in configuration with their source: wind speed bands (green from 1 mph, orange from 12 mph, red from 14 mph) and a green direction sector (centred on 0 degrees, 40 degrees either side). They are calibrated to an intermediate pilot on a low-end B paraglider and MUST be tunable later.
- **FR-012b**: Wind grading MUST consider both strength and direction: a block can be Ok, Good or Strong only when wind direction is inside the green sector, or marginally outside it (within 30 degrees of its edge: a marginally crossed launch, noted on the page but not limiting the grade, owner decision 2026-10-04), and strength is inside the green band. Further outside the sector the block is Poor, or Dangerous in strong wind. Speeds in configuration MUST state their units.
- **FR-021**: The Guide MUST list the grades in the order Ok, Good, Strong, Poor, Turbulent, Dangerous. It MUST describe exactly what the grading does, with every threshold taken from the rules in force (so it changes when the rules change and shows in the selected units): the six grades and what triggers each, every factor taken into account (wind speed and direction at launch altitude, gusts, rain, storm energy, thermal strength and height), the wind limits for the chosen glider, and what is NOT done: turbulence is inferred, not measured, and wind shear is shown but does not change the grade. Tests MUST check each claim against the real grading.
- **FR-025**: The page MUST have a collapsed section, "How the numbers are calculated", below the Guide, that says where each kind of data comes from (the forecast model and its run, the current-conditions provider, the measured weather station chart, the grading limits and the calibration baseline, with links), states plainly that the forecast is model output and the station chart is the only measurement, explains how each thermal figure is worked out (wind at launch altitude, heating at the hour, updraft, thermal height, thermal quality, temperature at thermal height, XC potential, rain, gusts and storm energy) and states the known limits. It MUST NOT present a scorecard of how closely the figures matched another forecast. Every threshold and figure it quotes MUST come from the rules in force and follow the chosen units, and tests MUST check each calculation it describes against the code.
- **FR-023**: The Guide MUST be collapsed by default. Selecting a grade anywhere (day icon, expanded-view grade, outlook icon) MUST open the Guide at that grade for the chosen glider and highlight it, without also expanding or collapsing the day row. Without scripting the grade is still a link to the Guide.

**Page and layout**

- **FR-005**: The system MUST publish the forecast as a static web page that loads quickly and is readable on a phone. The forecast itself, the grades and the glider and unit choices MUST work without scripting; scripting adds only optional extras (FR-006, FR-016, FR-018, FR-023, out-of-date banner).
- **FR-005a**: After each successful run the system MUST publish the page so it is reachable from the internet without the home computer accepting incoming connections, and it MUST remain available while the computer is asleep. Publishing is specified in [002](../002-firebase-hosting-deploy/spec.md).
- **FR-006**: The page MUST NOT play audio or depend on externally hosted images or media, with two exceptions that MUST fail soft: the weather station chart (FR-012c) and the current-conditions panel (FR-018).
- **FR-007**: The system MUST show the data source, model run time, validity period and an advisory notice on every page, and MUST show an out-of-date notice when the forecast is more than 30 hours old.
- **FR-012c**: The page MUST show the Mystic weather station's wind chart (from FreeFlightWx), about half the page width, beside the "Today at Mystic" panel (weather on the left, chart on the right on wide screens; stacked on phones). A toggle MUST let the pilot choose the period: Current, 1 hr, 4 hr (the default), 12 hr or Day. The heading MUST be the station's name, "FreeFlight WX", as a link to the station page, followed by the period (current, last hour, last 4 hours, last 12 hours, today), and the chart and its "full page" link MUST follow the choice. The chart, the "full page", "Station (live)" and "Gauge" links MUST open in a new tab (`noopener noreferrer`); the heading link opens the station page in the same tab. Only the chosen period's chart MAY be downloaded (none until it is wanted); the default still loads without scripting. The chart is optional: if it fails to load, the forecast MUST remain complete and the links MUST still work.
- **FR-012e**: Because the thermal values are calibrated against AUSRASP forecasts, the page MUST acknowledge AUSRASP with a link, MUST acknowledge the Victorian Hang Gliding and Paragliding Association (VHPA) as the supporter of its Victoria forecast, and MUST say AUSRASP is run on donations. If AUSRASP data is ever used directly, the state being used MUST be acknowledged and its operator's permission obtained first.
- **FR-012d**: The page MUST credit FreeFlightWx and the North East Victorian Hang Gliding Club (NEVHGC) wherever their data or chart is used, with working links to the Mystic station page (https://www.freeflightwx.com/mystic/index.php), FreeFlightWx (https://www.freeflightwx.com/) and NEVHGC (https://www.nevhgc.net), and MUST credit Open-Meteo for the current-conditions panel. The credit MUST state that the grading rules are based on the club's published Mystic site settings. The links to the individual station pages and the gauge are in the weather station panel (FR-012c), not repeated in the footer.
- **FR-017a**: When any block in the detailed days or any outlook day has rain or storm risk, the page MUST show a prominent notice naming the days, with a link to the Bureau of Meteorology Victorian warnings. The link MUST appear on every page.
- **FR-018**: The page SHOULD show a "Today at Mystic" panel with a simple current-conditions tile (conditions, temperature, wind, gusts, rain) and a forecast for the rest of the current day (every 2 hours from 06:00 to 20:00: weather, temperature, rain, wind and gusts) for the launch, filled in by the visitor's browser from Open-Meteo. It MUST follow the chosen units, be labelled a model estimate, show the Open-Meteo credit, and stay hidden if the data cannot be loaded.
- **FR-019**: Each detailed day MUST be one row: the day at the left and one column per hourly block (10:00 to 18:00, nine columns), so a whole day fits across the screen on a phone. The collapsed row MUST show only each hour's grade icon, thermal height and launch wind, as bare numbers in the chosen units. Opening a row MUST reveal the full details as one table; on a narrow screen the table MAY scroll sideways with the row headings kept in view.  The table's row headings (which carry the unit of their row, e.g. "Ground wind (kts)"; cells hold only the number, except percentages and words) appear once in the left column, under the date, with the hours as columns that line up with the collapsed row above; the grade word for the chosen glider heads each column, and the reasons are listed hour by hour in a "Why this grade" section beneath the table that is collapsed by default (owner request, 2026-10-04). Gusts are the row directly under the ground wind; they are the model's near-ground gusts, not gusts at launch altitude. It MUST work without scripting and by keyboard. The first day starts open. The days 5 to 7 outlook MUST use one box per day (three across), in the same style, fonts and sizes as the day boxes: the date, the grade icon for the chosen glider, and the wind arrow with direction and speed, plus a note when rain or storms are possible.
- **FR-020a**: The collapsed day header MUST show only the grade for the chosen glider as a single enlarged icon, with no glider label and no grade word on screen; the grade word and glider MUST remain available as a tooltip and to screen readers, and a sentence above the days MUST say the icon is the grade for the chosen glider. The launch wind MUST be shown in every time column with a solid triangle pointing the way the wind is blowing, coloured green inside the flyable direction sector, amber just outside it and red beyond that (the same sector and margin the grading uses), on a white circle so it reads on dark and light themes; the expanded details MUST label it with the altitude.
- **FR-024**: The title bar (with the glider toggle and settings menu), the update time and the rain or out-of-date alerts MUST stay pinned at the top while the rest of the page scrolls, with a visible edge and spacing beneath, and anything scrolled to (such as the Guide opened from a grade) MUST stop below the pinned header, not behind it. The glider toggle MUST be always visible, left of the settings button.

**Settings and units**

- **FR-016**: The page MUST let the pilot choose display units for wind speed (knots, km/h), height (metres, feet) and temperature (Celsius, Fahrenheit). Defaults MUST be knots, metres and Celsius. The choice MUST apply to every value on the page, including thresholds, reasons and the Guide; updraft strength and rain rate follow the height unit (m/s and mm/h, or ft/sec to one decimal and in/h). The unit choices MUST live in a settings menu opened by a hamburger button at the right of the page header (closed by default, with a text name for screen readers, and closing on an outside tap or Escape). The selector MUST work without scripting. The choices (glider, units and the weather station period) MUST be remembered in a first-party cookie (one year, `SameSite=Lax`, scoped to the site's folder, `Secure` on https, holding only these settings), with local storage as a fallback when cookies are unavailable, and MUST be applied before the page content is drawn so a returning visitor never sees the defaults flash. Values read from the cookie MUST be validated: only an existing setting's own options may be applied.
- **FR-016a**: The embedded station chart is an image with its own axes (km/h and knots shown together), so it does not follow the unit choices; the page MUST say what it shows.
- **FR-022**: The page MUST let the pilot choose the glider type: paraglider (PG, the default) or hang glider (HG), with the toggle always visible in the header (FR-024). Everything glider-specific MUST then show only for the chosen glider: the day icon, the grade and reasons in the expanded view, the outlook grades, the colours of each block, and the Guide (its wind limits and text). Values that do not depend on the glider are always shown. The choice MUST work without scripting, be remembered (FR-016), and a link to the hang glider part of the Guide MUST select hang glider.

**Pipeline and operation**

- **FR-008**: The system MUST update itself daily without manual intervention.
- **FR-008a**: If a scheduled run is missed because the computer was asleep or off, the system MUST run as soon as the computer is next awake and a newer source data cycle is available, and MUST NOT run a second time for a cycle already published.
- **FR-009**: The system MUST retry when the expected source data is not yet available, within a bounded time.
- **FR-010**: The system MUST keep the last good forecast published when a run fails, and show its age.
- **FR-011**: The system MUST record each run's outcome and duration so the owner can see failures and trends.
- **FR-014**: The system MUST remove old run data and downloaded weather data automatically to bound disk use.
- **FR-015**: The system MUST NOT collect or store personal data from page visitors.

### Key Entities

- **Site**: A flying location: name, coordinates, launch altitude (800 m for Mystic), time zone, and the weather station chart periods. Mystic is the first.
- **Forecast Run**: One execution of the pipeline: source data cycle, start and finish time, outcome, failed stage, duration.
- **Forecast Block**: One hour for a site (days 1 to 4, 10:00 to 18:00 local): winds (launch altitude, ground, aloft), shear, thermal height, quality and updraft, temperatures, gusts, rain, storm energy, where the thermal figures came from, and a grade with reasons for each glider type.
- **Daily Outlook**: A single-day summary for days 5 to 7 with wind, a grade for each glider type and a low-confidence label.
- **Grading Rules**: The thresholds that turn values into grades (wind bands per glider, direction sector, gust, rain, storm energy, thermal limits), with a version and a recorded source.
- **Settings**: The pilot's glider type, units and weather station period, kept in a cookie on their own device.
- **Published Page**: The page derived from a run, with its production time, model, cycle and rules version.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A pilot can find the best flying window in the coming week within 30 seconds of opening the page on a phone.
- **SC-002**: The page itself (document, styles and scripts) is under 200 KB and is usable within 1 second on a typical mobile connection. The weather station chart images, which come from another provider, are not counted.
- **SC-003**: The forecast updates automatically on at least 95% of days over a month, with no manual action.
- **SC-004**: When a run fails, 100% of the time the pilot still sees a forecast with its age clearly stated.
- **SC-005**: A full daily run completes in under 3 hours on the target home computer. (Not yet measured for the regional model; the GFS-only mode completes in about 2 minutes.)
- **SC-006**: On a sample of at least 10 days, the grades agree with the pilot's own judgement of the conditions for at least 80% of blocks, after threshold tuning, and no day with thunderstorms or heavy rain is graded better than "poor".
- **SC-007**: Changing a grading threshold and republishing takes under 5 minutes.
- **SC-008**: Changing the glider type or any unit updates every affected value on the page instantly, with no page reload.
- **SC-009**: A returning visitor's glider, unit and chart period choices are applied before the page is drawn, with no visible flash of the defaults.
- **SC-011**: On days where both are available, the thermal values agree with AUSRASP-based reference figures (the baseline for thermal values) to within, on average, 300 m for thermal height and 0.5 m/s for updraft, compared at the same UTC hours. Measured 2026-10-03 on 16 blocks: 255 m and 0.47 m/s; quality 18 points (target 10, not yet met). This is an internal target; the page does not show it.
- **SC-010**: Every claim the Guide makes about the grading is checked by an automated test against the real grading.

## Assumptions

- The user is the sole operator and the first user; the page is for personal and club-level pilots, not a public commercial service.
- The forecast is built from NOAA's free global weather model data, refined by running a regional atmospheric model on the owner's own computer, in line with the project constitution. Until the regional model is verified, the GFS-only mode is what runs.
- The target machine is a home Apple M4 iMac with 16 GB RAM that is not guaranteed to be awake at the scheduled time.
- The page is served as static files from GitHub Pages; the home computer only publishes and never serves visitors. GitHub Pages sets its own response headers (no custom security headers, and a cache lifetime of about 10 minutes), so a new forecast can take up to about 10 minutes to reach a returning visitor.
- The FreeFlightWx station chart is a fixed-width image inside site navigation, so the chart image is embedded (scaled to the screen) rather than the whole page. FreeFlightWx sends no frame-blocking headers and no hotlink protection was seen; NEVHGC will be contacted as a courtesy before launch. The station has no rain gauge, which is why rain comes from the model.
- The current-conditions panel makes a request from each visitor's browser to Open-Meteo (free for non-commercial use with attribution).
- BoM warnings cannot be fetched by program (its feed returns errors), so the page links to the official warnings instead of showing them.
- Mystic is the only site in the first version; WA or other sites are out of scope.
- The grading thresholds (including the rain, storm and gust ones and the Ok, Good and Strong ones) start from reasonable defaults and are tuned over time against real flying days.
- Forecasts are advisory and not a safety guarantee; live observations and pilot judgement still apply.
- Historical archives, user accounts, notifications and a public API are out of scope for the first version.
