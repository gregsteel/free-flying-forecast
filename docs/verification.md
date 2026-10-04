# Checking the forecast against what happened

The gust, sunshine and wind rules in `config/rules.toml` are judgement calls (`gust_mix_fraction`,
`gust_aloft_factor`, the aloft gust limits, `sun_full_pct`, `ausrasp_wind_counts`). Tuning them needs
evidence of what the weather and the flying were actually like. This is where that evidence comes from.

## What is kept now

Every run keeps the forecast for each local date in `state/history/<date>.jsonl` (in the container,
`/app/state/history`, on the `state` volume). A line is one snapshot with the model cycle, the AUSRASP
runs used, and that date's blocks in full: winds, estimated gusts, sun, thermals and both grades. A
rebuild that changes nothing for a date adds nothing. With this, "what did we say on Tuesday morning"
can always be answered, whichever later run replaced it on the page.

Read it with `ffforecast.history.read_day(Path("state/history"), "2026-10-06")`.

## What actually happened: sources

| Source | What it offers | Verdict |
|---|---|---|
| The Mystic weather station (FreeFlightWx) | Measured wind speed, direction and gusts at the launch, all day | The best check for **wind and gusts at launch**. The page only embeds its charts as images; the data behind them has no known open interface. Worth asking the club (NEVHGC) for an export |
| SkyLines (`skylines.aero/api/flights/...`) | A working public JSON API: flights by date with takeoff and landing times, distance and an IGC file name | Checked 5 Oct 2026: **3 flights in the whole world on 4 Oct, all in Belgium.** No Australian use, so no Mystic flights |
| LiveTrack24 | A documented "API v2" with login and one-time passwords, a track-data sub-API and a competition sub-API | Needs an account. The public pages give no endpoint formats or usage terms, so a reader cannot be written yet. The XCSoar client (`src/Tracking/LiveTrack24`) only **uploads** the pilot's own track: login, start, send position, end. It cannot read other pilots' flights |
| XContest | Where most Australian pilots upload | Not checked. Has the best chance of covering Mystic; terms of use need reading first |

## What to compute from flights, once a source is chosen

Per flying day, from flights that launched at Mystic (a takeoff within about 1 km of the launch):

- **Did anyone fly**, and how many launches, against the grade we gave.
- **Highest altitude reached** (metres above sea level), against our thermal height.
- **Best climb rates**, against our updraft.
- **Day length of flying** (first launch to last landing), against the hours we graded Ok or better.

Score each day against the forecast that stood on the page the morning before and the morning of, both from
the history above.

## Rules for using pilots' data

- Keep only totals per day (counts, maximum height, best climb). Do not store names or tracks.
- Read the service's terms and use its published interface; no scraping.
- Identify the program in the user agent, as the AUSRASP client does, and keep requests few.

## Not done yet

Reading any flight source, and the scoring itself. The history store above is the part that cannot be
recovered later, so it comes first.
