# Benchmarks

To be filled in on the iMac (task T026). Record, for each configuration: Colima CPUs and memory,
domain sizes, run length, wall-clock time and peak memory. Constitution principle III requires a
measured figure before any scale-up.

| Date | Colima VM | Domains | Run length | Wall time | Peak memory | Notes |
|------|-----------|---------|------------|-----------|-------------|-------|

## GFS-only mode (measured 2026-10-03, on a different Mac, home network)

| Machine | Stage | Result |
|---------|-------|--------|
| Apple M4 Pro, 48 GB (not the iMac) | Full `run --model gfs`, 24 forecast hours | 53 s total, 140 MB downloaded |
