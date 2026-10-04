# Phase 0 Research: Free Flying Forecast

Verified facts are marked **Verified**. Everything else is a recommendation or an open item to be
confirmed by a task. Sections are numbered in the order they were written; where a later section
replaced an earlier decision, the earlier one is marked **Superseded** and points to the new one.

Last reviewed against the build: 2026-10-03 (section 21 added after the thermal comparison).

## 1. Source weather data

- **Decision**: NOAA GFS 0.25 degree, pulled from the public AWS bucket `noaa-gfs-bdp-pds`, using
  HTTP range requests guided by each file's `.idx`, fetching only the needed fields (each is a
  global grid; the bucket cannot subset by area).
- **Verified** (2026-10-03): files are at `gfs.YYYYMMDD/CC/atmos/gfs.tCCz.pgrb2.0p25.fFFF` with a
  matching `.idx`; all four cycles (00, 06, 12, 18 UTC) were present for the previous day. The
  idx lists `HPBL`, `CAPE`, `SHTFL`, `LAND`, `HGT:surface` and 10 m winds.
- **Rationale**: free, no key, and each field can be fetched alone by byte range.
- **Verified** (real download, 2026-10-03): the bucket cannot subset by area, so each field is a
  global 0.25 degree grid of about 0.7 MB. The outlook's 5 fields cost under 6 MB per forecast
  hour; the whole GFS-only run (24 hours) downloaded 140 MB in under a minute. WRF's boundary
  input needs many more fields and levels, so it should use NOMADS's regional subsetting or a
  full-file download; to be decided with the benchmark.
- **Alternatives**: NOMADS (rate limited, short retention); Open-Meteo (simpler but cannot feed
  WRF).
- **Verified** (final field set, 2026-10-03): the GFS-only run now fetches 8 surface fields plus
  winds and heights at four pressure levels for each needed hour. A full run (24 hours) took 143
  seconds and left 398 MB in the cache, so old cycles are pruned (the newest two are kept).
- **Open**: publication delay after cycle time to be measured; the retry window depends on it.

## 2. Regional model

- **Decision**: WPS + WRF 4.6.x built from source in a Linux arm64 image. Domains: d01 12 km
  (about 1200 km square) and d02 4 km nested (about 400 km square) over Bright, forced by GFS
  every 3 hours, 96 hour run (days 1 to 4), hourly output.
- **Rationale**: matches the RASP approach (nested 12/4 km). A 0.25 degree to 4 km direct jump is
  too large a ratio, so the 12 km parent is kept.
- **Alternatives**: single 4 km domain (cheaper, worse boundary behaviour); pre-built
  `openeuler/wrf` image (an arm64 WRF 4.6.1 exists but I have not checked it includes WPS or is
  suitable; fall back to it only if the source build fails).
- **Open (risk)**: static geography data. The default low-resolution set is a small download;
  high-resolution terrain for 4 km needs a larger subset. Choose after the benchmark.
- **Open (risk)**: no WRF build has been attempted on arm64 here. Colima is installed only on the
  iMac, not on the machine this plan was written on, and Docker was not running here.

## 3. Diagnostics (replace RASP's NCL scripts)

- **Decision**: compute in Python from WRF output.
  - Thermal height: WRF `PBLH` above ground, converted to metres above sea level for display.
  - Updraft velocity: Deardorff convective velocity scale `w* = ((g / theta) * (HFX / (rho * cp)) * zi)^(1/3)`
    using `HFX` and `PBLH`; thermal quality is a configured mapping from `w*` and wind, in percent.
  - Wind aloft: wind at a level inside the boundary layer; vertical shear from the difference
    between 10 m and that level.
  - XC potential: poor, fair, good or great from thermal height, `w*` and wind (spec FR-002).
- **Alternatives**: `wrf-python` (heavier dependencies, but can be used to cross-check); porting
  RASP's NCL (rejected: NCL is end-of-life and awkward on arm64).
- **Open**: map `w*` to the old forecast's "thermal quality %" by comparing a few days of both.

## 4. Runtime and memory budget

- **Decision**: do not assume. The first implementation task is a benchmark of a 6 to 12 hour run
  on the iMac with the Colima VM at 8 CPUs and 10 GB, recording wall time and peak memory
  (constitution III). If 96 hours exceeds 3 hours, reduce d01 size, then output frequency, before
  reducing d02.

## 5. Days 5 to 7 outlook

- **Decision**: no WRF. Read GFS fields at the nearest points for Mystic (10 m wind, a boundary
  level wind, `HPBL`, `CAPE`) at 3 or 6 hourly steps to f168, reduce to one daily verdict and wind
  summary, and label it low confidence.

## 6. Grading rules

- **Decision**: seed from the NEVHGC FreeFlightWx Mystic settings (**Verified** on the site's Site
  Info page): green from 1 mph, orange from 12 mph, red from 14 mph; green direction sector centred
  on 0 degrees, 40 degrees either side; calibrated to an intermediate pilot on a low-end B
  paraglider.
- Config keeps the original mph values and converts to kph for display (12 mph is 19.3 kph, 14 mph
  is 22.5 kph).
- Grade mapping as built (all thresholds in `config/rules.toml`, to be tuned; see also section 14):
  - Dangerous: wind in the red band; strong wind (orange band or more) well outside the green
    sector; heavy rain; storm energy at the storm level, or at the overdevelopment level with rain;
    or gusts in the red band.
  - Turbulent: wind in the orange band; storm energy at the overdevelopment level without rain; or
    gusts in the orange band. (Wind marginally outside the sector used to be here; since 2026-10-04
    it is only noted and the thermals decide: section 24.)
  - Poor: wind too light, or outside the sector at lower speeds; any rain; or green wind with weak
    or low thermals.
  - Good, Great, Pumping: none of the above, with thermal quality and height above their limits; the
    thermals then decide (section 22).
  - The worst problem found sets the grade. Direction is judged on the wind at launch altitude
    (section 16). Hang gliders have their own, higher, wind bands; everything else is shared.
  - Turbulence is not measured. Wind shear is calculated and shown but does not change the grade
    (task T063 asks whether it should).
- Each verdict carries a text reason (spec FR-003).

## 7. Scheduling and catch-up

- **Decision**: a launchd agent with `StartCalendarInterval`. launchd runs a missed calendar job
  when the Mac next wakes, which fits FR-008a. `state.json` records the last published cycle so a
  second firing for the same cycle exits immediately. The wrapper starts Colima if it is stopped.
- **Open**: confirm on the iMac that a wake-time catch-up fires, and decide whether to set a
  `pmset` wake schedule shortly before the run (optional).

## 8. Publishing

- **Superseded (2026-10-03)**: the first plan was GitHub Pages, pushed as a single orphan commit to
  an output repository. The owner has chosen **Firebase Hosting** instead, in the existing project
  `free-flying-forecast`; it is specified in
  [`../002-firebase-hosting-deploy/spec.md`](../002-firebase-hosting-deploy/spec.md).
- **Interim**: `publish.py` still implements the git push (tested against a local bare repository).
  It is replaced by the Firebase deployment and removed once that is live (002 FR-026).
- **Why it matters here**: the page's security headers, caching and the cookie `Secure` flag are
  now the deployment's concern (002 FR-017 to FR-020), and the page's inline scripts and styles
  mean the content security policy has to be computed from the page (002 FR-019).

## 9. Embedded gauge and credits (superseded by section 15)

- **Verified**: `https://www.freeflightwx.com/mystic/gauge.php` returns HTTP 200 and sends no
  `X-Frame-Options` or CSP frame headers, so it can be framed. It is a script-driven canvas page
  that refreshes itself.
- **Superseded**: the gauge was first embedded as an `iframe`, then replaced by the station's
  chart image (section 15) and a period toggle (section 19). The gauge is now only a link in the
  panel and the footer credit. The credit to FreeFlightWx and NEVHGC with links stays (spec
  FR-012d), and NEVHGC is to be contacted as a courtesy before launch.

## 10. Site coordinates

- **Verified** (from the owner's Google Maps link, "Mystic paraglider and hang glider launch"):
  latitude -36.7584099, longitude 146.965839.
- **Superseded**: the owner states the launch is **800 m** above sea level, which is now the
  configured value. For reference, a 90 m elevation model gave about 785 m. This was a rough
  figure; the real launch height should be checked against a surveyed value or the club's launch
  guide. The FreeFlightWx station altitude is a separate figure (2615 ft, about 797 m).

## 11. Time zone

- **Decision**: all display times use `Australia/Melbourne`; blocks are at 11:00, 13:00, 15:00 and
  17:00 local, handling daylight saving explicitly in tests.

## 12. GFS-only mode (built and measured)

- **Decision**: a first working forecast needs no WRF. GFS is hourly to 120 hours, so the 11, 13,
  15 and 17 o'clock local blocks for 4 days come from point values at the nearest grid cell, with
  850 hPa wind standing in for wind aloft; days 5 to 7 use the 3-hourly steps. The page labels the
  model as "NOAA GFS 0.25 degree (no regional model)".
- **Verified**: `ffforecast run --model gfs` ran end to end against live data in 53 seconds;
  a repeat run for the same cycle was skipped; a failed stage keeps the last page (unit-tested).
- **Verified from real files**: boundary layer height is GRIB discipline 0, category 3, number 196
  (ecCodes gives it no short name, so messages are matched by number); `SHTFL` is positive upward
  (76 W/m2 averaged over the 11:00 to 14:00 local window); GFS terrain at the launch is 687 m
  against the launch's 785 m, and the nearest grid point is 3 km away.
- **Limit**: ground winds from a 25 km grid are light (3 to 8 km/h in the first run), so this mode
  understates ridge winds. That is the case for the 4 km WRF stage.
- It stays as the fallback when the regional run fails.

## 13. Display units

- **Decision**: render every value in all supported units and let CSS show the selected one
  (radio buttons plus `:has()`), so the selector works without JavaScript. Choices: wind in knots
  (default) or km/h, height in metres (default) or feet, temperature in Celsius (default) or
  Fahrenheit. Updraft and rain rate follow the height unit. Plain-text reasons such as "Wind 12
  kph" are converted at render time, so `forecast.json` stays in kph and metres. (mph and m/s were
  offered at first and removed at the owner's request.) Where the choices are stored is section 18.
- **Verified** (reading the gauge page source): the gauge has its own unit buttons but no URL
  parameter, storage key or `postMessage` hook and is on another origin, so the page could not
  drive it. This no longer matters: the gauge is not embedded (section 15).

## 14. Rain, storms and gusts (added after a real miss, 2026-10-03)

- **What went wrong**: on a day with a thunderstorm and BoM severe weather warnings (screenshot from
  Apple Weather), Free Flying Forecast showed "great" for 11:00 to 15:00 because the GFS-only mode ignored
  rain, storm energy and gusts. The independent Open-Meteo model gave 75 to 92% rain probability
  and CAPE up to 900 J/kg for the same hours; GFS itself had 2.3 mm/h and CAPE 648 at 11:00.
- **Decision**: fetch `PRATE`, `CAPE` and `GUST` (identified in the files as 0/1/7, 0/7/6 and
  0/2/22). `PRATE` is listed twice, instantaneous and a 6-hour average; only the instantaneous one
  is used. Rules live in `rules.toml` `[weather]`: rain from 0.1 mm/h caps at "poor", from 1 mm/h
  "dangerous"; CAPE 400 gives "turbulent" (or "dangerous" with rain), 1000 "dangerous"; gusts
  16 mph "turbulent", 20 mph "dangerous". These are judgement calls to tune.
- **Verified**: after the change the same cycle grades every block on 3 Oct "dangerous", with the
  reasons shown.
- **BoM warnings**: `ftp.bom.gov.au/anon/gen/fwo/IDZ00054.warnings_vic.xml` returns 550 and the HTTP
  equivalent 403, so warnings are not fetched; the page links to https://www.bom.gov.au/vic/warnings/.
- **Limit**: GFS rain at 25 km is smeared. Treat rain and storm flags as "possible", not exact.

## 15. Station chart and current-conditions tile

- **Verified**: `4hours.php` sends no frame-blocking headers but is a Bootstrap page with navigation
  around a fixed 780 px chart image (`windgraph.php?time=14400...`), which would be cropped in a
  phone-width iframe. The chart image already shows km/h and knots axes, so no unit control is
  needed. Embedded as a scaled image linked to the page, refreshed every 5 minutes while open.
- The station measures wind, temperature, humidity, pressure and cloudbase, but has no rain gauge and
  publishes only an HTML table, so rain comes from Open-Meteo `current` (15-minute model
  analysis), which allows browser requests (`access-control-allow-origin: *`).

## 16. Wind at launch altitude

- **Decision**: interpolate u and v linearly in height at the site's altitude (800 m AMSL, the
  owner's figure) from a profile made of the 10 m wind (placed 10 m above the model surface) and
  the 950, 925, 900 and 850 hPa levels with their geopotential heights.
- **Verified from real data**: GFS puts the Mystic grid cell's ground at 687 m with surface pressure
  near 940 hPa, so 950 hPa and below are underground and hold extrapolated values. Those levels are
  dropped using surface pressure (`profile.usable_profile`); 925 hPa sat at about 803 m, almost
  exactly launch height.
- **Cost**: eleven more fields per hour (surface pressure and height, plus wind and height at four
  levels), roughly doubling the download per forecast hour.
- **Effect on grading**: the verdict is now judged on the launch-altitude wind (direction and
  speed), together with the stronger of the 10 m and 850 hPa winds for speed. Easy to revert if it
  proves too strict.
- **Limit**: a 25 km grid with a 687 m ground height standing in for a ridge at 800 m. The WRF
  path will interpolate from model levels instead (T053).

## 17. Four detailed days, three outlook days (changed 2026-10-03)

- **Decision**: days 1 to 4 get 2-hour blocks and days 5 to 7 the low-confidence outlook (the
  owner's call; it replaces the earlier 3 and 4 split). One setting in `models.py` drives the
  forecast hours fetched, the page headings and the outlook column count.
- **Verified**: day 4's last block (17:00 local) falls at about f78, inside GFS's hourly range
  (hourly to f120), so the GFS-only mode needs no new data. Day 7 outlook steps reach about f150.
  A run that starts after the day's flying moves everything one day later (up to about f180), so the
  cycle-availability check now waits for f192.
- **Cost for the WRF stage**: the regional run lengthens from 72 to 96 hours, about a third more
  run time. The benchmark (T026) must therefore time 96 hours. If that exceeds the budget,
  options are a shorter run with day 4 taken from GFS-only values, or a coarser outer domain.
- **Accuracy**: day 4 is still a long way out for hour-by-hour thermal numbers, so the page's
  "low confidence" notice for the outlook does not apply to it. The grades for day 4 should be read
  as indicative.

## 18. Where settings are kept (cookie)

- **Decision**: a first-party cookie, `ffforecast-prefs`, holding only the radio choices (glider,
  wind, height, temperature, station period), one year, `SameSite=Lax`, `Path` set to the site's
  own folder, `Secure` on https. Local storage is the fallback when cookies are unavailable (for
  example a page opened from a file). The values are checked against the page's own radios before
  being applied, because a cookie is user-controlled input.
- **Verified in a real browser** (headless Chrome over HTTP): choices survive a reload; the cookie
  reports a 365-day expiry, `SameSite=Lax` and `Path=/` (or `/sub/` when the site lives in a
  folder); a tampered cookie applies only its one valid entry, injects nothing and cannot pollute
  object prototypes.
- **Why a small script runs early**: it sits straight after the header controls so the rest of the
  page is drawn with the saved choices (no flash of defaults). The period radios are further down,
  so the script re-applies once the page has loaded and the chart loader asks it to apply first.

## 19. Weather station periods

- **Verified**: the station's own pages build their charts with `windgraph.php?time=SECONDS` for
  the current (600 s), 1 hour, 4 hour and 12 hour views, and `windgraph2.php?begin=today&end=tomorrow`
  for the day view. All five render at 440 by 380 pixels.
- **Decision**: the periods and their links live in the site configuration, with 4 hours first.
  Each period has a heading wording, a chart and a "full page" link; all links open in a new tab.
- **Verified in a real browser, two bugs found and fixed**: (1) `loading="lazy"` did not stop hidden
  charts being downloaded, so all five loaded on every visit (about 200 KB); now no chart has an
  address in the page until the script gives one to the chosen period, with a no-script fallback
  for the default. (2) A saved non-default period was ticked but the default chart still loaded,
  because the saved choice was applied after the chart was chosen; now it is applied first.

## 20. Glider type and the details table

- **Decision (glider)**: both gliders' grades, reasons and outlook grades are rendered into the
  page and CSS shows only the chosen one, as with units. Block colours come from two sets of CSS
  variables, one per glider. The Guide has a list per glider with that glider's wind limits.
  `forecast.json` now carries the hang glider reasons and outlook grade; older files fall back to
  the paraglider values.
- **Verified in a real browser**: switching glider hides and shows the right icons, colours and
  Guide limits; selecting a grade opens the Guide at that grade without toggling the day row; a
  link to the hang glider part of the Guide selects hang glider (a hash bug was found and fixed).
- **Decision (details)**: the expanded day is one table, row headings once in the left column, and
  the four times as columns. A shared width variable makes the first column and the four time
  columns line up with the collapsed row above; verified 0 px out in a browser. On phones the
  reasons are listed per time below the table because four narrow columns cannot hold sentences.

## 21. Thermal height, quality and updraft against a reference forecast (2026-10-03)

The owner finds a public forecast page for the Victorian sites a reasonable guide, so it is the
baseline for the thermal values. It is built on AUSRASP Victoria (the same host runs AUSRASP, and
the page says it is "based on the local RASP"). Ours did not match it. The comparison was made on
16 blocks, 3 to 6 October, from one snapshot of that page and our GFS cycle 2026-10-02T18Z. The
page's own table (32 blocks) was also used to work out what its figures mean. The page itself is
not named or shown anywhere in the product.

**What was found (four causes):**

1. **Different clocks.** The reference page and RASP label times "AES", Australian Eastern *Standard* Time,
   all year; after daylight saving began on 4 October "1100 AES" is 12:00 local. Our blocks use the
   local clock (11:00, 13:00, 15:00 and 17:00 AEDT, which is 00Z, 02Z, 04Z and 06Z). Comparing them
   is only fair at the same UTC hours (01Z, 03Z, 05Z, 07Z). Our page keeps the local clock because
   pilots read it; this is a labelling difference, not an error.
2. **A real bug: the heating was an average over a window.** GFS gives surface heating as the
   average since the last multiple of 6 hours. Our 17:00 block (06Z) therefore used the average of
   the whole midday (267 W/m2 on 5 Oct) when the heating at that hour was 111, and our 11:00 block
   used too little. That made our mornings weak and our late afternoons strong. The hourly value is
   recovered as `n * avg(n) - (n - 1) * avg(n - 1)` from the previous hour's average, which costs one
   small extra download per block (hours that already hold one hour need nothing).
3. **A different meaning of "thermal height".** In the reference table the height is exactly 657 m (its
   model's ground height) in every block whose updraft is below about 1.1 m/s (largest 0.96, and the
   smallest with a height is 1.17); 225 ft/min is 1.143 m/s, RASP's critical updraft. Otherwise its
   depth above the ground is 0.34 to 0.63 (mean 0.48) of the GFS boundary layer depth. So it is the
   height thermals are *usable* to, not the top of the boundary layer, which is what we showed and
   which is about twice as high. Its own wording agrees: "Great height for flying XC" starts at about
   1,000 m and "difficult" covers everything up to 977 m.
4. **A different quality scale.** The reference quality reaches 100% at an updraft of about 1.6 to 2.0 m/s
   and loses about 2.5 points per km/h of wind above 12 to 15 km/h. Ours reached 100% at 2.5 m/s and
   used 3 points above 15, which was 15 points out on average against 5 points for the best fit.

RASP's own definition of updraft is the same formula we use (W* = [(g/T0) * heating * depth]^(1/3)),
so the formula was not the problem.

**Changes made (all values in `config/rules.toml` under `[thermal]`, with their source recorded):**
hourly heating; usable thermal height (launch altitude when the updraft is under 1.143 m/s, else
launch altitude plus 0.48 of the boundary layer depth); quality 100% at 1.6 m/s less 2.5 per km/h
above 12; the minimum height for "great" raised to 900 m; the XC height cut-offs moved to 1,000,
1,200 and 1,500 m.

**Result on the 16 comparable blocks (mean absolute error against the reference):**

| | Thermal height | Quality | Updraft |
|---|---|---|---|
| Before | 937 m | 22.5 points | 0.51 m/s |
| After | 255 m (155 m measured as depth above each model's own ground) | 18.1 points | 0.47 m/s |

**What is still different, and why:**

- Updraft is on average 16% above the reference, and some blocks differ a lot (for example 4 Oct 13:00:
  ours 2.7, the reference 0.9). The reference snapshot comes from an earlier GFS cycle and a regional model at
  higher resolution; our input is GFS at 25 km. The formulas now agree; the weather input does not,
  and we have no way to close that gap without the regional model (WRF) or RASP output itself.
- Quality still differs by 18 points on average, mostly because our GFS winds are lighter than the
  winds the reference shows, and the wind term is large (for example 6 Oct 11:00: reference 25 to 29 km/h,
  ours lighter).
- The calibration constants come from a single snapshot of 16 to 32 blocks. They are reasonable and
  match RASP's own critical value, but they are fitted, not proven. Re-check them against a second
  and third snapshot, and against real flying days (task T052).

**Credit.** Nothing is fetched from AUSRASP at run time; only the reference page's published numbers were read,
once, to calibrate. The page nevertheless acknowledges AUSRASP and, for Victoria, its supporter the Victorian
Hang Gliding and Paragliding Association (VHPA), in the footer (spec FR-012e). AUSRASP's own Victoria page says it
"needs funds to cover running costs" and may close without support, so using its output directly as an
input would be fragile and would need its operator's permission.

The page's collapsed "How the numbers are calculated" section explains the calculations and limits but
deliberately has no "how well it matches" part, and the comparison figures live only here and as a
comment in `config/rules.toml`.

## 22. Good, Great and Pumping (2026-10-03)

- **Owner's definitions**: Great is "a time you definitely want to go flying". Pumping "means it's
  powerful and demands experience". Good is what is left: flyable with decent thermals. The earlier
  single "Great" covered all three.
- **Decision**: the problem grades are unchanged and still win: Poor, Turbulent and Dangerous come
  from the worst problem (wind, direction, gusts, rain, storm energy), and weak or low thermals are
  Poor. Only a block with no problem is split by its thermals:
  - Good: quality at least 40% and thermals reaching 900 m (the old Great bar).
  - Great: quality at least 70% and an updraft of at least 2.5 m/s. The owner's figure: a block shown
    with an updraft of 1.7 m/s and 100% quality was wrongly Great, because the first version used 1.6
    m/s (where quality reaches 100%). An updraft of 1.7 m/s is Good.
  - Pumping: an updraft of at least 3.5 m/s (my starting value, to tune; the owner gave no figure
    for it), or Great-strength thermals together with a brisk but
    still green wind: 9 mph for paragliders, 11 mph for hang gliders (about three mph under each
    glider's orange band, so a day is Pumping before it becomes Turbulent).
- **Order in the Guide**: Good, Great, Pumping, Poor, Turbulent, Dangerous, which is the owner's
  order. Pumping is not "better than Great": it is stronger and for experienced pilots.
- **Colours and icons**: Good is teal with a thumbs up, Great stays green with a tick, Pumping is
  violet with a flame, so none can be mistaken for the amber and red problem grades. Both themes
  have all six.
- **Updraft is now passed to the grading** (it was not needed before). Without an updraft value only
  quality is used and Pumping cannot be reached; the outlook passes the day's average updraft.
- **Verified on the real forecast** (cycle 2026-10-03T00Z, with the first version's 1.6 m/s Great
  bar, since raised to 2.5): 5 Oct 11:00 (updraft 2.4 m/s, wind 11 km/h) was Great and is now Good;
  most strong-thermal blocks that day are Turbulent because the interpolated launch
  wind is from the north-west, just outside the 320 degree edge of the flyable sector (313 degrees),
  and no block in that forecast reaches Pumping. The thresholds are starting values and need tuning
  against real days (task T052); the updraft here runs about 16% above the reference figures
  (section 21), so Great and Pumping may prove too easy to reach even at 2.5 and 3.5 m/s.
- **Open**: whether a marginal direction (a few degrees outside the sector) should really be
  Turbulent, as it is now, rather than keep the Good/Great/Pumping tiers; it decides most of the
  strong days in the current data.


## 23. AUSRASP published data (2026-10-03)

Looked at what AUSRASP serves for Victoria, to see whether its values can be used directly. Fetched about 30 small files, nothing else; no one was contacted.

- **Raw grids exist.** The map page itself loads plain-text grids named `<quantity>.curr.<hhmm>lst.d2.data` under `OUT+0` to `OUT+6` (today to six days ahead), and a `latlon2d.json` with each cell's position. Grid: 144 by 144 cells at 4 km (Lambert), values multiplied by the header's `Mult`.
- **Found for VIC:** thermalling height (`hglider`), critical-updraft height (`hwcrit`) and its depth (`dwcrit`), boundary-layer top (`hbl`), updraft (`wstar`), `rain1`, `cape`, `sfctemp`, `sfcsunpct`. **Not found under the obvious names:** wind, `bsratio`, `dbl`, `sfcshf`, the cloudbase masks. Hours 0800 to 1800 AES exist; 0600 and 1900 return 404.
- **Updraft is coarse.** `wstar` is stored with `Mult=1` in m/s, so only whole numbers (0 to 3 that day).
- **Nearest cell to the Mystic launch:** row 59, column 100 (zero-based), 0.8 km away. For Sun 4 Oct 1500 AES (05Z) it gave thermalling height 1844 m, `hbl` 2487 m, `wstar` 2 m/s. Neighbouring cells ranged 1106 to 1885 m. The map's colour at the marker agreed with 1844 m. Our own page showed about 1440 m and 1.73 m/s for the nearest block, the other reference forecast showed 1252 m (it matches no cell near the launch), so it must come from a different run or calculation.
- **Timing.** A small manifest, `version.json` (about 300 bytes, `no-store`), holds a stamp per day. Header comments say the stamp changes only when that day is re-run. Observed stamps: day 0 16:40Z and day 1 17:39Z on 2 Oct; day 2 04:53Z on 3 Oct; day 3 19:37Z; day 4 11:47Z; day 5 10:55Z; day 6 18:38Z (all 2 Oct). File times and the "NNhrFcst" headers show initial times of 12Z (2 Oct) for days 0, 1, 3, 6 and 00Z (3 Oct) for day 2; day 5 was still from 12Z on 1 Oct. So each day is re-run on its own, apparently after the 12Z and 00Z global-model cycles, with no fixed time. One day's evidence only: spec 003 FR-013 logs stamp changes for a week.
- **Clock.** Not fixed, as first assumed (corrected 2026-10-04): each file's header says AES (UTC+10) or AED (UTC+11), and it depends on when the run was made. Files made after 16:00Z on 3 Oct (when daylight saving began) say `Valid 1000 AED (2300Z)`; earlier ones say `Valid 1500 AES (0500Z)` even for the same date. The first reader assumed UTC+10, so daylight-time runs were read an hour late until the reader was changed to take the offset from the header.
- **Terms.** No licence, terms or permission text on the site; its "Disclaimer" popup returns 404; `robots.txt` is absent; the host's error page says no administrator email is set. The original RASP program's licence (2006) restricts copying without written permission, which concerns the program, not the published values. Whether automated use is welcome is unknown.
- **Consequence for the design:** use AUSRASP only for thermal height and updraft at the nearest cell, keep the global-model estimate as fallback and for everything else (owner decision: not wind or rain). See spec 003.

**Built and run live (2026-10-03).** `FFF_NETWORK=1` live test and a full run read the real files: the nearest cell is row 59, column 100, 0.81 km from the launch, grid 144 by 144. A full seven-day refresh is 58 requests with the 1 s pause (about 1 minute 50 seconds) and stores about 44 KB. Between two reads about 4 hours apart AUSRASP re-ran day 1 (stamp 04:53Z to 06:25Z, from its 00Z run), and the Sun 4 Oct thermal height at the same block went from about 1840 m (12Z run, 15:00 AES) to about 1500 m at 11:00 local: runs differ a lot, which is why the page names the run. Day 5 (Thu 8 Oct) was still from the 12Z run of 1 Oct, older than the 36-hour limit, so its outlook used the estimate, as designed. Whole-number updraft: the real grids used `Mult=1` in every file seen; the reader divides by `Mult`, following AUSRASP's own note that the printed value is the true value times the factor.


## 24. Crossed launches no longer cap the grade (2026-10-04)

- **Decision (owner)**: wind marginally outside the green sector (up to 30 degrees past its edge; called *marginally crossed* on the page) no longer sets Turbulent. "Sometimes you can get off when it's crossed and if conditions are otherwise okay then you can have a good day."
- **Effect**: the block is graded on its other conditions (wind speed, gusts, rain, storms, thermals). The page still notes it: the wind arrow is amber and the block's reasons say the wind is crossed.
- **Unchanged**: wind further outside the sector is Poor, or Dangerous when strong; strong wind, gusts and storm energy still set Turbulent or Dangerous as before.
- **Why it mattered**: in the 3 Oct 12Z forecast, all six Turbulent blocks were Turbulent because of direction alone (launch wind 307 to 319 degrees, 8 to 15 degrees past the 320 degree edge).

## 25. Hourly blocks, three grade names and no XC rating (2026-10-04)

Three owner changes the same day, all in the page and its data:

- **Hourly blocks, 10:00 to 18:00** (nine a day) instead of 2-hour blocks at 11, 13, 15 and 17. GFS is hourly to forecast hour 120 and day 4 ends near hour 80, so every block has its own GFS hour (about 2.25 times the download of before, still inside the cache budget). AUSRASP needs 18 files a day instead of 8, so its request budget became 150 an hour and 25 MB a day (spec 003 FR-024). The page shows nine narrow cells a day (hour, grade icon, thermal height and launch wind as bare numbers in the chosen units); the detail table scrolls sideways on a narrow phone with the row headings kept in view; the reasons are listed hour by hour beneath it. Rendered, the fixture page is about 155 KB (the 200 KB target holds).
- **Grades renamed**: Good is now **Ok**, Great is now **Good**, Pumping is now **Strong**. Poor, Turbulent and Dangerous are unchanged. Forecast files carry schema 2; a schema 1 file is read with its old names translated. Earlier sections of this file use the old names.
- **XC potential removed** (the row, the rating, its thresholds and the method-section item). Old forecast files that still carry `xc_rating` read normally.

## 26. Display rounding (2026-10-04)

- **Thermal heights are shown rounded down to the nearest 100 m, or to the nearest 100 ft when feet are selected** (each unit rounds in its own steps, so 1,844 m shows as 1,800 m or 6,000 ft). The owner asked for it because the forecast is not that precise. It applies to the collapsed cells, the detail table and the reasons that quote a height; grading uses the unrounded value. Launch altitude is not rounded.
- **Updrafts in feet are ft/sec to one decimal** instead of ft/min (2 m/s shows as 6.6 ft/sec; the owner first asked for whole numbers, then one decimal). Metres stay m/s with one decimal (AUSRASP's whole numbers show as whole m/s).

## 27. Weather tabs, and units in the row labels (2026-10-04)

- **"Today" panel tabs**: the panel is now a tab bar of places, defined by `[[weather_tabs]]` in the site file (id, label, heading, optional lat/lon/elevation_m/note). The first, Mystic, uses the launch position as before. The second is **Mt Hotham** (summit -36.97528, 147.13278, 1,862 m), added because the owner knows that the wind at Mt Hotham indicates how suitable the day is at Mystic; its note says so. Each tab shows current conditions and today's hourly forecast from Open-Meteo, as Mystic did, with the wind and gusts of its own place. More tabs are only more configuration. The chosen tab is a radio like the other settings, so it is remembered in the settings cookie. Values are Open-Meteo model figures for 10 m wind, not measurements, and no threshold is applied to Hotham's wind yet (the owner has not given one).
- **Units in the detail table's row labels**: the numbers sit in the cells and the unit (which still follows the settings) is in the row label, e.g. "Ground wind (kts)", "Thermal height (m)", "Updraft (m/s)", "Rain (mm/h)". Thermal quality keeps its percent sign in the cells (owner request); words (shear, "none", "not available") stay as words.
