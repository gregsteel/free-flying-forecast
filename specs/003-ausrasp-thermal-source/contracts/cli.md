# CLI contract: poll

`ffforecast poll [--if-due] [--no-rebuild] [--cache DIR] [--state DIR] [--out DIR] [--work DIR]`

Reads the AUSRASP manifest, fetches changed days, stores them, and unless `--no-rebuild` rebuilds and publishes once when at least one day was stored.

- `--if-due`: do nothing (exit 0, one line) unless a check is due under the schedule in the site file.
- Exit 0: nothing to do, or checked and (if needed) rebuilt. Exit 0 also when AUSRASP is unreachable (the fallback is a normal state); the line printed says so.
- Exit 3: a rebuild was needed and failed (the previous page stays live).
- Output: one line, e.g. `poll: 2 changed (OUT+1, OUT+2); rebuilt and published` or `poll: no change` or `poll: not due`.

`ffforecast run` also refreshes AUSRASP first (stage "ausrasp") and prints `thermal: ausrasp (n of m blocks)` or `thermal: gfs estimate (reason)`.

# Site file additions: `[ausrasp]`

```toml
[ausrasp]
enabled = true
base_url = "https://ausrasp.com/VIC/"
contact = "<an email or web address of the owner>"   # sent in the user agent
max_cell_km = 3
cell_radius = 1                                       # 1 = highest of a 3 by 3 block, 0 = nearest cell only
max_age_h = 36
[[ausrasp.poll]]     # windows (UTC) with the interval in minutes; the last entry without a window is the default
from = "04:30"
to = "09:00"
every_min = 20
[[ausrasp.poll]]
from = "16:00"
to = "21:00"
every_min = 20
[ausrasp.poll_default]
every_min = 180
```

# Rules file additions

```toml
[thermal_ausrasp]
good_updraft_ms = 3
strong_updraft_ms = 4
```
