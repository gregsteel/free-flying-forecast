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
| The Mystic weather station (FreeFlightWx) | Measured wind (average, gust, lull), direction, temperature, humidity and a calculated cumulus base, a reading about every 11 seconds | **Built.** See the next section. The best check for wind and gusts at the launch |
| SkyLines (`skylines.aero/api/flights/...`) | A working public JSON API: flights by date with takeoff and landing times, distance and an IGC file name | Checked 5 Oct 2026: **3 flights in the whole world on 4 Oct, all in Belgium.** No Australian use, so no Mystic flights |
| LiveTrack24 | API v2 (manual: `livetrack24.com/doc/api/api.zip`). Reads: users last seen within a radius of a point (op 30), waypoints near a point (op 3), live tracks in range (`liveList`), and the track points of given users or tracks (`getTrackPoints`: time, position, altitude, speed, vario) | **Chosen**, because FlySkyHy and others feed it. Needs an **application key and secret** (free, from LiveTrack24 on request) plus a user login; keys are **tied to the IP address** the calls come from (the manual's demo key is refused: "No access for this appKey from IP"). There is no "all flights at this site yesterday" call, so the plan is: ask for users seen near the launch in the last day, then fetch their tracks. The XCSoar client only uploads and is not a guide |
| kk7 Thermal Database (`thermal.kk7.ch`) | A long-term map built from millions of flights (XContest, DHV-XC, Syride and others): skyways, thermal probability, thermal hotspots, with a time-of-year/day filter. Downloads as KML, GPX, CUP, WPT and CSV; map tiles with a `src=<your hostname>` parameter | **Not a daily check.** It is a climatology: it says where and when thermals usually are, and its own page says it was last updated 2026-03-07. It cannot tell us what happened on a given Tuesday. It could later give a sanity check on typical thermal heights and the time of day they start. Terms: CC BY-NC-SA 4.0 (attribute it, non-commercial, share alike), and commercial use needs the author's agreement. Its flights come largely from XContest, which shows the data is there, but it does not replace asking XContest for permission |
| XContest | Where many Australian pilots upload after flying. Public flight pages show launch, times, distance and the track | **Wanted, but not usable yet.** It publishes no API and no terms for automated use. Its `robots.txt` (read 2026-10-06) disallows the flight search pages, the track downloads (`/track.php`, `/trackml.php`, `/trackmz.php`) and every address with a query string, and disallows AI crawlers outright. Its rules page says an uploaded track "becomes the public property" but says nothing about automated access. So nothing may be read from it by program until XContest agrees: the next step is to ask them (what we would read, how often, that only daily totals are kept), and to ask whether they have an API or feed |

## The station's wind: how it is collected and compared

There is no published API, but the station's table page offers its log as a CSV download
(`table.php?h=<hours>&download=csv`, with 1, 12, 24, 48, 168 (7 days) and 720 (30 days) hours). It is
newest first, in local time, with speeds in mph. (A JSON feed behind the gauge page also exists, but it only
reaches back about an hour.)

- **Daily download:** once a day, after the flying (`[observations] run_time` in `config/site.mystic.toml`,
  21:30), the container fetches the last 2 days and keeps **5 minute summaries** (average wind, strongest
  gust, lightest lull, direction, temperature, calculated cloudbase) in `state/observations/<date>.json`.
  The 2 day log overlaps the last download, so a late or short run loses nothing.
- **Catching up:** if the newest reading is more than 30 hours old, a download happens at once, and the log
  length is the shortest of 2, 7 or 30 days that reaches back past the last reading. A gap longer than 30 days
  is recorded in `state/observations/status.json` (`gaps`) and cannot be recovered. The first ever download
  takes 30 days (about 18 MB, once). A failed download is retried after an hour, not every few minutes.
- **Resolution:** the 1 day and 2 day logs are full resolution (every 11 seconds). The 7 and 30 day logs are
  thinned to about one reading a minute, so a day recovered by catching up has gusts that read a little low.
  Buckets built from fewer than 12 readings are treated as thinned, and the report says so. A later
  full-resolution download of the same time replaces a thinned bucket.
- **Cloudbase:** the station's "cloudbase" is calculated, not measured: its height (about 796 m) plus 125 m
  for every degree between temperature and dew point. It shows where cumulus would form, so it can test
  AUSRASP's cumulus cap on thermal height and the forecast temperature. It says nothing about thermal strength
  or the real top of the thermals, and real cloud bases often differ from it by a few hundred metres.

Compare what was forecast with what was measured:

```
uv run ffforecast compare --days 14          # a summary over the last 14 days
uv run ffforecast compare --date 2026-10-06 --blocks
```

For each hourly block the measurement is the hour centred on it. Two forecasts of each date are scored: the one
standing the evening before and the one standing that morning (08:00). The report gives bias and mean error for
the global model's 10 m and launch-height wind, AUSRASP's 10 m wind and the speed the grade used; for the 10 m gust
and the estimated gust at launch; for ground temperature; for thermal height against the cumulus base; for wind
direction; and rough air as hits, false alarms, misses and quiet hours. **It needs saved forecasts, which start when
the new image is deployed, so the first report is possible the day after.**

## Two flight sources, one daily summary

Pilots use LiveTrack24, XContest or both (the same flight can be in each), so the daily summary is to be built
from whichever sources are available and must not count a flight twice.

- Each source is a reader that returns, for one local date, the flights that launched at Mystic: launch time,
  launch position, highest altitude, best climb rate and landing time. Nothing else is kept from it: no
  pilot names, ids or tracks.
- **De-duplication:** two flights are the same flight when they launch within 5 minutes of each other and
  within 1 km. This needs no names. The merged flight takes the larger of each value.
- The saved summary says how many flights each source supplied and how many were in both, so a day with only
  one source working is not mistaken for a quiet day.
- A source that is not set up, refused or down is skipped and noted. The summary never fails the run.
- LiveTrack24 has a reader (below). XContest has none until it agrees to automated access.

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

## LiveTrack24: what is built, and what is next

Built, from the manual and its PHP samples, and tested against a pretend server only
(`src/ffforecast/livetrack24.py`): the one-time-password sign-in, login with the encrypted password (the
`passe` form, never plain text), the read calls above, and unpacking of the delta-packed track strings.
It is read-only, pauses a second between calls and stops after 60 calls a run.

To try it, request an application key from LiveTrack24 (give it the public IP address of the machine the
calls will come from), then run, with these set in the environment and never in a file in the repository:

```
FFFORECAST_LT24_APP_KEY=...  FFFORECAST_LT24_APP_SECRET=...
FFFORECAST_LT24_USERNAME=... FFFORECAST_LT24_PASSWORD=...
uv run ffforecast lt24-probe --radius 5 --ago 86400
```

It prints the replies with people's names hidden. The shape of the op 30 reply is not in the manual, so
the daily summary (count, highest altitude, best climb) is written against that real output, not guessed.

## Not done yet

The daily flight summary (LiveTrack24 first, XContest if it agrees) and scoring flights against the forecast. Nothing is tuned from
the wind comparison yet: it needs a few weeks of both halves first.
