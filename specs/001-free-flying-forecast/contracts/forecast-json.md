# Contract: forecast.json

Written to the output folder beside the page. The page template renders only from this file, so
the page, the tests and any future consumer share one structure. Last reviewed against the build:
2026-10-03. Field meanings are in [data-model.md](../data-model.md).

```json
{
  "schema": 1,
  "site": "mystic",
  "model": "NOAA GFS 0.25 degree (no regional model)",
  "cycle": "2026-10-02T18Z",
  "generated_at": "2026-10-03T13:12:07+10:00",
  "rules_version": 1,
  "blocks": [
    {
      "start": "2026-10-03T11:00:00+10:00",
      "wind_ground": {"dir_deg": 344, "kph": 5},
      "wind_aloft": {"dir_deg": 4, "kph": 11},
      "wind_launch": {"dir_deg": 347, "kph": 8},
      "shear": "light",
      "thermal_height_m": 1571,
      "thermal_quality_pct": 40,
      "updraft_ms": 1.1,
      "thermal_source": "gfs",
      "thermal_run": "",
      "temp_ground_c": 14,
      "temp_air_c": 6.9,
      "verdict_pg": "bad",
      "verdict_hg": "bad",
      "reasons": ["Wind 8 kph is in the green band.", "Rain expected (0.9 mm/h)."],
      "reasons_hg": ["Wind 8 kph is in the green band.", "Rain expected (0.9 mm/h)."],
      "rain_mm_h": 0.92,
      "cape_j_kg": 650,
      "gust_kph": 8
    }
  ],
  "outlook": [
    {
      "date": "2026-10-07",
      "wind": {"dir_deg": 350, "kph": 7},
      "verdict": "good",
      "verdict_hg": "good",
      "confidence": "low",
      "rain_mm_h": 0.0,
      "cape_j_kg": 0
    }
  ]
}
```

Values are illustrative. A real file has 16 blocks (4 days of 4) and 3 outlook days. `verdict_pg`, `verdict_hg` and the outlook `verdict` and `verdict_hg` are one of `ok`, `good`, `strong`, `poor`, `bad` (schema 4). Forecasts made before 2026-10-03 only ever hold `good` for what is now Ok, Good or Strong, and those made before 2026-10-05 hold `turbulent` and `dangerous` for what is now Bad; they are translated when read and still render.

Compatibility: `thermal_source` (`ausrasp` or `gfs`) and `thermal_run` (the AUSRASP model start, ISO UTC, empty for `gfs`) were added by [003](../../003-ausrasp-thermal-source/spec.md); outlook days carry `thermal_source` too; files without them read as `gfs`. `wind_launch`, `reasons_hg`, `verdict_hg`, `rain_mm_h`, `cape_j_kg` and `gust_kph` were
added after the first version. A file without them still renders: missing hang glider values fall
back to the paraglider values and the launch wind row is left out.

## Page contract

- The page is one static HTML document: inline styles, two small inline scripts, no framework.
- The forecast, the grades, and the glider and unit choices work without scripting.
- Header (pinned): title, glider toggle, settings menu (units), update time, rain or out-of-date
  alerts.
- Credits and links (FreeFlightWx station, history and gauge; NEVHGC; Open-Meteo), the data source,
  model, cycle, generation time, rules version and rules source, the advisory notice and the BoM
  warnings link appear in the footer (spec FR-007, FR-012d, FR-017a).
- The only requests the page makes to other hosts: the weather station chart images
  (`www.freeflightwx.com`) and the current-conditions data (`api.open-meteo.com`). Both are optional
  and fail soft. This list is what the deployment's content security policy is built from (002
  FR-018, FR-019).
- The one cookie, `ffforecast-prefs`, holds only the visitor's settings (spec FR-016).
