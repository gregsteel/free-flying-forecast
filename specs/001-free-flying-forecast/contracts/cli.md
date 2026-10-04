# Contract: command line

Run as `ffforecast <command>` (inside the container on the iMac, or with `uv run ffforecast` for
development). Global options, before the command: `--site PATH` (default `config/site.mystic.toml`)
and `--rules PATH` (default `config/rules.toml`). Last reviewed against the build: 2026-10-03.

| Command | State | Purpose | Exit codes |
|---|---|---|---|
| `check` | built | Validate the site and rules files | 0 valid, 1 invalid |
| `render --input FILE --out DIR` | built | Render the static page from a `forecast.json` | 0, 1 cannot render |
| `run [options]` | built (GFS-only) | Whole pipeline for the newest available cycle: fetch, build the forecast, render, publish if asked | 0 published or skipped as a duplicate, 2 no data in the retry window, 3 a stage failed |
| `fetch`, `wrf`, `diagnose`, `publish` | placeholders | Individual stages; they print that they are not wired up and exit 3 | 3 |

`run` options:

| Option | Default | Meaning |
|---|---|---|
| `--model gfs\|wrf` | `gfs` | Forecast source. `wrf` is not wired up yet and exits 3 |
| `--force` | off | Run even if this cycle is already published |
| `--cache`, `--state`, `--out`, `--work` | `cache`, `state`, `out`, `work` | Folders for downloaded weather data, run state, the published site, and scratch space |
| `--retries`, `--retry-sleep` | 6, 600 s | How long to wait for a late data cycle |
| `--publish-remote`, `--publish-branch`, `--publish-key` | none, `gh-pages`, none | Interim git publisher; replaced by the Firebase deployment (002) |

Rules:

- Every command prints plain text; `run` prints one line: outcome, cycle and duration.
- A non-zero exit never changes the published page or `state.json`: a new page replaces the old one
  only after every stage has succeeded, by swapping whole folders.
- A cycle already published is skipped (outcome `skipped_duplicate`) unless `--force` is given.
- After a published or duplicate run, downloaded weather data for all but the newest two cycles is
  deleted.
