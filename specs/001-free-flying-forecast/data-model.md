# Data Model: Free Flying Forecast

All data are plain files. Types are conceptual; `forecast.json` (see
[contracts/forecast-json.md](contracts/forecast-json.md)) is the serialised forecast. Field names
below match the code (`src/ffforecast/models.py`, `config.py`, `state.py`). Last reviewed against
the build: 2026-10-03.

## Site (`config/site.mystic.toml`)

| Field | Notes |
|---|---|
| `id`, `name` | `mystic`, "Mystic, VIC" |
| `lat`, `lon` | -36.7584099, 146.965839 (from the owner's map link) |
| `elevation_m` | 800: the launch altitude above sea level, as given by the owner; used for thermal height and for wind at launch |
| `timezone` | `Australia/Melbourne` |
| `station_default` | id of the weather station chart period shown first (`4h`) |
| `[domain.d01]`, `[domain.d02]` | resolution and size of the WRF domains (used by the WRF stage, not yet built) |
| `[links]` | `station`, `gauge`, `history`, `freeflightwx`, `nevhgc`, `openmeteo`: used for links and credits |
| `[[station_charts]]` | one per period: `id`, `label`, `heading`, `link`, `page`, `chart`. Periods: `cur`, `1h`, `4h`, `12h`, `day`. All links must be https and ids unique |

## Grading Rules (`config/rules.toml`)

| Field | Notes |
|---|---|
| `version`, `source` | version must be a positive integer and increase on any change; source must be non-empty (currently the NEVHGC FreeFlightWx Mystic site settings) |
| `[wind]` | `speed_green_from_mph` 1, `speed_orange_from_mph` 12, `speed_red_from_mph` 14 (paraglider); `hg_speed_orange_from_mph` 14, `hg_speed_red_from_mph` 20. Keys must end in `_mph` or `_kph`; bands must be in order |
| `[direction]` | `sector_center_deg` 0, `sector_half_width_deg` 40, `marginal_margin_deg` 30 (how far outside still counts as marginal: a crossed launch, noted but not limiting the grade) |
| `[shear]` | `moderate_from_kph`, `strong_from_kph`: used to label shear, which does not change the grade |
| `[thermal]` | The tiers for a block with no problems: `ok_quality_pct` 40 and `min_height_m` 900 separate Ok from Poor; `good_quality_pct` 70 with `good_updraft_ms` 2.5 make Good; `strong_updraft_ms` 3.5, or Good-strength thermals with a wind of `strong_wind_from_mph` 9 (`hg_strong_wind_from_mph` 11 for hang gliders), make Strong. Orders are validated (ok quality, then good, up to 100; good updraft below strong; the strong wind below the orange band). Calibrated against AUSRASP-based reference figures (research section 21), all optional: `critical_updraft_ms` 1.143 (225 ft/min: below it there are no usable thermals), `usable_depth_fraction` 0.48 (usable height = launch altitude plus this fraction of the boundary layer depth), `quality_full_updraft_ms` 1.6, `quality_wind_threshold_kph` 12, `quality_wind_penalty_per_kph` 2.5 |
| `[weather]` | `rain_light_mm_h` 0.1, `rain_heavy_mm_h` 1.0, `cape_overdevelop_j_kg` 400, `cape_storm_j_kg` 1000, `gust_orange_from_mph` 16, `gust_red_from_mph` 20. Optional; defaults apply when absent. Light must not exceed heavy, and so on |

## Forecast Run (`state/state.json` and `state/run-log.jsonl`)

| Field | Notes |
|---|---|
| `cycle` | GFS cycle, e.g. `2026-10-03T00Z` |
| `started_at`, `finished_at`, `duration_s` | |
| `outcome` | `published`, `failed`, `skipped_duplicate`, `no_data` |
| `failed_stage` | `fetch`, `diagnose`, `render` or `publish` (`wrf` once it exists) |
| `peak_mem_mb` | reserved for constitution III; not yet filled in |

`state.json` holds only `last_published_cycle` and `published_at`, and is replaced atomically, only
after a successful run. `run-log.jsonl` has one line per attempt. Stages run in order (fetch,
diagnose, render, publish); any failure leaves the published page and `state.json` untouched.

## Forecast Block (days 1 to 4)

| Field | Notes |
|---|---|
| `start` | start time with offset: hourly, 10:00 to 18:00 local |
| `wind_ground`, `wind_aloft` | direction in degrees, speed in km/h (10 m wind; 850 hPa wind) |
| `wind_launch` | the same, interpolated to launch altitude. Optional: older forecasts lack it |
| `shear` | `light`, `moderate` or `strong` |
| `thermal_height_m` | usable thermal height above sea level: the launch altitude when the updraft is below the critical value, else launch altitude plus about half the boundary layer depth (not the top of the boundary layer) |
| `thermal_quality_pct`, `updraft_ms` | |
| `thermal_source`, `thermal_run` | `ausrasp` with the run start (then `thermal_height_m` and `updraft_ms` are AUSRASP's, the updraft a whole number), or `gfs` (the estimate). Optional: older forecasts read as `gfs` |
| `temp_ground_c`, `temp_air_c` | ground, and at thermal height |
| `rain_mm_h`, `cape_j_kg`, `gust_kph` | rain rate, storm energy, gust speed |
| `verdict_pg`, `verdict_hg` | `ok`, `good`, `strong`, `poor`, `turbulent`, `dangerous` (the first three are the "no problem" grades, decided by the thermals) |
| `reasons`, `reasons_hg` | text reasons for each glider type. `reasons_hg` is optional: older forecasts lack it and the paraglider reasons are used |

## Daily Outlook (days 5 to 7)

| Field | Notes |
|---|---|
| `date` | |
| `wind` | direction and speed; at launch altitude when the vertical profile is available |
| `verdict`, `verdict_hg` | paraglider and hang glider grades, from the same six. `verdict_hg` is optional: older forecasts lack it and `verdict` is used |
| `rain_mm_h`, `cape_j_kg` | the day's highest values; used for the wet-weather note |
| `confidence` | always `low` |

The split between detailed and outlook days is `DETAILED_DAYS` (4) and `OUTLOOK_DAYS` (3) in
`models.py`.

## Settings (in the visitor's browser, not in the data)

| Setting | Choices | Default |
|---|---|---|
| glider | paraglider, hang glider | paraglider |
| wind unit | knots, km/h | knots |
| height unit | metres, feet | metres |
| temperature unit | Celsius, Fahrenheit | Celsius |
| station chart period | current, 1 hr, 4 hr, 12 hr, day | the site's `station_default` |

Kept in the cookie `ffforecast-prefs` (local storage as fallback); see research section 18.

## Published Page

| Field | Notes |
|---|---|
| `generated_at`, `cycle` | shown in the header and footer; the page shows an out-of-date notice after 30 hours |
| `rules_version`, `rules_source` | shown in the footer |
| `model` | e.g. "NOAA GFS 0.25 degree (no regional model)" in GFS-only mode |
