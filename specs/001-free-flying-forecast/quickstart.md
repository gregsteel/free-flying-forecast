# Quickstart: validating Free Flying Forecast end to end

Last reviewed against the build: 2026-10-03. Steps marked **[any Mac]** can be run anywhere with
`uv`; steps marked **[iMac]** need the Colima and Docker setup on the owner's iMac and have not been
run yet.

Prerequisites on the iMac: Colima running with 8 CPUs, 10 GB RAM and enough disk
(`colima start --cpu 8 --memory 10 --disk 80 --vm-type vz`). Hosting credentials are specified in
[002](../002-firebase-hosting-deploy/spec.md) and are not needed for steps 1 to 9.

1. **Environment [any Mac]**: `uv sync`, then `uv run pytest` (about 210 tests, one live test skipped unless `FFF_NETWORK=1`), `uv run ruff check .`, `uv run pyright`. Expected: all clean.
2. **Config check [any Mac]**: `uv run ffforecast check`. Expected: exit 0 and the rules version and source.
3. **Render from sample data [any Mac]**: `uv run ffforecast render --input tests/fixtures/forecast.json --out out`. Expected: `out/index.html` under 200 KB, readable at phone width, with the credits, advisory notice and BoM link.
4. **Real forecast [any Mac]**: `uv run ffforecast run --model gfs`. Expected: "published: cycle ... in about 2 minutes"; `out/index.html` and `out/forecast.json`; a second run reports `skipped_duplicate`.
5. **Settings in a browser [any Mac]**: open `out/index.html` over a local web server (cookies do not work from a file). Change the glider, a unit and the station period, reload. Expected: choices are applied before the page is drawn; only the chosen station chart is downloaded; the Guide opens at a clicked grade.
6. **Failure safety [any Mac]**: break the fetch (offline) and run. Expected: previous page still in `out/`, its age shown, the failure in `state/run-log.jsonl`, exit 2 or 3.
7. **Build the image [iMac]**: `docker build -t ffforecast -f docker/Dockerfile .` Expected: the image builds and WRF and WPS are present. The Dockerfile is unverified and is expected to need fixes.
8. **Benchmark [iMac]**: time a 6 to 12 hour WRF case and extrapolate to 96 hours; record wall time and peak memory in `docs/benchmarks.md` (constitution III).
9. **Catch-up [iMac]**: install the launchd job, sleep the Mac across the schedule, wake it. Expected: one run fires; a second firing for the same cycle exits as `skipped_duplicate`.

The deployment checks (preview, rollback, headers, live verification) belong to 002's quickstart.
