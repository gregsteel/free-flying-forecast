# Free Flying Forecast

A self-hosted, simple soaring forecast for paraglider and hang glider pilots at Mystic (Bright),
VIC. It builds one static, phone-friendly web page from free NOAA weather data - published with GitHub Pages (its address is the repository's website link).

- **Days 1 to 4**: detailed hourly blocks (10:00 to 18:00 local) with wind, estimated gusts at launch and
  at thermal height, shear, thermal height and quality, updraft, sun reaching the ground, temperature and a grade for paragliders and hang gliders: Ok,
  Good ("definitely go flying"), Strong (powerful, demands experience), Poor or Bad (rough air or dangerous: do not fly).
- **Days 5 to 7**: a low-confidence daily outlook.
- **Glider type**: a PG / HG toggle in the header (paraglider by default).
- **Settings** (hamburger menu): units (knots, metres and Celsius by default; km/h, feet and Fahrenheit
  available). Both choices are kept in a cookie in the browser.
- **Guide**: collapsed; select any grade to open it at that grade.
- **How the numbers are calculated**: collapsed; where the data comes from and how the thermal figures are worked out.
- **Rain, storms and gusts**: rain, thunderstorm risk and gusts (at 10 m, at launch and at thermal height) are graded; cloud shading lowers thermal quality; a notice links to the official BoM Victorian warnings when any are possible.
- **Today**: current conditions and an hourly forecast for the rest of the day (Open-Meteo), with a tab
  for Mystic and one for Mt Hotham (strong wind there can mean Mystic is marginal). Add more places as
  `[[weather_tabs]]` in `config/site.mystic.toml`.
- **FreeFlight WX**: the Mystic station's wind chart (FreeFlightWx) with a Current / 1 / 4 / 12 hour / Day toggle.

## Run it

```bash
uv sync
uv run ffforecast check                       # validate config/
uv run ffforecast render --input tests/fixtures/forecast.json --out out   # page from sample data
uv run ffforecast run --model gfs             # real forecast from NOAA GFS (about a minute; --force reruns a published cycle)
uv run ffforecast poll --no-rebuild           # check AUSRASP for new thermal data (about 2 minutes the first time)
uv run pytest                                  # tests (FFF_NETWORK=1 adds live NOAA and AUSRASP checks)
```

Output is `out/index.html` and `out/forecast.json`. Add `--publish-remote <git url>` (and
`--publish-key <deploy key>`) to push the site to a git remote as a single commit. In the repository's
settings, set GitHub Pages to deploy from the `gh-pages` branch. (A free GitHub Pages site needs a public
repository. The deploy key lives outside the project, and nothing secret is committed.)

## On a Mac with Colima

```bash
colima start --cpu 8 --memory 10 --disk 80 --vm-type vz
docker build -t ffforecast -f docker/Dockerfile .
```

Copy `scripts/ffforecast-launchd.plist` to `~/Library/LaunchAgents/`, edit its path, and put
settings in `~/.config/ffforecast/env` (`FFFORECAST_PUBLISH_REMOTE`, `FFFORECAST_DEPLOY_KEY`,
`FFFORECAST_MODEL`). `scripts/run-on-host.sh` starts Colima and runs the container.

AUSRASP re-runs each forecast day on its own, so a second job checks for changes: copy
`scripts/ffforecast-poll-launchd.plist` the same way. Every 20 minutes it runs
`run-on-host.sh poll`, which only acts inside the polling windows in `config/site.mystic.toml`
(`[[ausrasp.poll]]`) and rebuilds the page when a day changed. Put your contact in `[ausrasp] contact`
(it is sent to AUSRASP in the user agent) and set `enabled = false` there to stop all requests.
The poll windows are a first guess: after a week, compare them with
`cache/ausrasp/stamps.jsonl` (every change AUSRASP made, with the time it was noticed).

After forking, run `python3 scripts/update_readme_url.py` to point the page link at your own GitHub Pages
address. It reads the owner and repository from `FFFORECAST_PROJECT` or the `origin` remote.

## Using a Docker image and Portainer

`.github/workflows/docker.yml` runs the tests, then builds `docker/Dockerfile.gfs` (GFS-only, no WRF) for
arm64 (on GitHub's native arm64 runners) and pushes it to `ghcr.io/<username>/free-flying-forecast` (`latest` on main, plus a
`sha-` tag). The container runs `docker/gfs-scheduler.sh`: a forecast run at start-up and at 05:30 and
15:30 Melbourne time (`FFFORECAST_RUN_TIMES`), and `poll --if-due` every 5 minutes. Paste
`docker/portainer-stack.yml` into a Portainer stack, set `FFFORECAST_PUBLISH_REMOTE`, `FFFORECAST_PROJECT` (the repository URL, for the page's "fork the project" link) and `FFFORECAST_CONTACT` (your email, sent to AUSRASP in the user agent), and provide the
deploy key by bind-mounting the key file. Keep `cache`, `state`, `out` and
`work` on volumes.

## Forecast history

Every run keeps each day's forecast in `state/history/<date>.jsonl` (`/app/state/history` in the
container), so it can later be compared with what happened. How that comparison could be made, and
which flight and weather sources were checked, is in `docs/verification.md`. The measured wind from the Mystic
station is downloaded once a day (`observe`) and `uv run ffforecast compare` lines it up against the saved forecasts.

## Tuning

The grading rules live in `config/rules.toml`; bump `version` when you change them. They start from
the NEVHGC FreeFlightWx Mystic site settings. The site (location, AUSRASP polling, weather tabs, station
charts and links) is defined in `config/site.mystic.toml`; set the `FFFORECAST_PROJECT` environment variable (or `[links] github` there) and the page's
"fork the project" text becomes a link. Run `uv run ffforecast check` after editing either file. The gust, sun and AUSRASP-wind values in
`rules.toml` are starting guesses; `docs/verification.md` says how they are to be checked.

## Credits

The wind speed and wind direction rules are based on the published Mystic site settings of the
[North East Victorian Hang Gliding Club (NEVHGC)](https://www.nevhgc.net) as shown on the
[FreeFlightWx Mystic weather station](https://www.freeflightwx.com/mystic/index.php). The
station chart is from [FreeFlightWx](https://www.freeflightwx.com/mystic/4hours.php). Current
conditions: [Open-Meteo.com](https://open-meteo.com/) (CC BY 4.0). Forecast data: NOAA GFS.

This is advisory information, not a safety guarantee.
