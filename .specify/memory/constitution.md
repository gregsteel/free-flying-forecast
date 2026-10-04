<!--
Sync Impact Report (temporary; remove before commit)
- 1.2.0 → 1.3.0 (MINOR, 2026-10-04): Principle V now permits three optional live elements (the station chart image, a cropped view of the FreeFlightWx gauge in a frame, and Open-Meteo current conditions for each place tab), and describes the output as hourly blocks without an XC estimate.
- 1.1.0 → 1.2.0 (MINOR): Principle V now permits two optional live elements: the station chart
  image and the Open-Meteo current-conditions tile (replacing the gauge iframe).
- 1.0.0 → 1.1.0 (MINOR): Principle V now permits one optional external embed, the
  FreeFlightWx Mystic wind gauge, with a fallback link.
- Version change: 0.1.0 (unratified draft) → 1.0.0 (first ratified version)
- Modified principles: all rewritten with MUST/SHOULD wording and testable criteria;
  "Fits the Hardware" gained explicit Colima VM budget; "Honest Forecasts" gained
  versioned-config requirement.
- Added sections: Operational Constraints; Development Workflow
- Removed sections: Constraints (split into the two sections above)
- Follow-up TODOs: none. Measured runtime budget is to be recorded after the first
  test forecast on the iMac.
-->

# Free Flying Forecast Constitution

Free Flying Forecast is a self-hosted, simple soaring forecast for paragliding and hang gliding
at Mystic (Bright), VIC, produced from open weather data on a home Mac.

## Core Principles

### I. Free and Open Inputs
All software and data MUST be free to use: WRF/WPS, RASP or equivalent post-processing,
and NOAA GFS data. No paid APIs or subscriptions. GFS downloads MUST be limited to the
needed region and fields, via NOAA's public AWS bucket or NOMADS.
Rationale: the project is a hobby tool and must carry no running cost.

### II. Reproducible in Docker
All forecast tooling MUST run in containers under Colima on the target iMac (Apple M4,
16 GB RAM). WRF and its libraries MUST NOT be built on the host. A clean checkout plus
`docker build` MUST reproduce the environment. Native arm64 images MUST be used unless
an amd64/Rosetta image is unavoidable, in which case the reason MUST be documented.

### III. Fits the Hardware
The design budget is the Colima VM on the iMac: at most 8 CPUs and 10 GB RAM, leaving
the rest to macOS. Domain size, nesting and run length MUST fit that budget. Each
configuration change MUST be accompanied by a measured wall-clock runtime and peak
memory figure, recorded in the repo. Scale-ups MUST NOT be adopted without measurement.

### IV. Unattended and Resilient
The daily run (scheduled with launchd) MUST work without supervision. It MUST retry when
a GFS cycle is late, exit non-zero and log clearly on failure, and MUST NOT replace the
last good forecast with output from a failed run. Old run output MUST be pruned
automatically.

### V. Simple, Pilot-First Output
The product is a static, mobile-friendly HTML page. It MUST work without JavaScript, MUST
NOT autoplay media, and MUST NOT depend on external image files (use emoji or inline
SVG). The only permitted external dependencies are optional live elements: the FreeFlightWx Mystic station chart (one image, linked to its page), a small cropped view of the FreeFlightWx Mystic wind gauge (one frame, linked to its page), and current-conditions tiles filled in by the visitor's browser from Open-Meteo (one per place tab). Each MUST fail soft: if it does not load, the forecast MUST remain complete and a plain link MUST be available. The page MUST credit each provider with a link. For each hourly block it MUST show wind on the ground and aloft, vertical shear,
thermal height and quality, updraft strength and temperature, with a
colour-graded verdict that is not conveyed by colour alone.

### VI. Honest, Configurable Forecasts
Grading thresholds MUST live in explicit, versioned configuration, not inline in code.
Every output page MUST state its model source, model run time and validity period.
Thresholds SHOULD be calibrated against real flying days and other forecast sources. The page MUST carry a notice that it is advisory information, not a safety
guarantee.

### VII. Incremental, Verified Delivery
Work MUST proceed in verifiable steps: container builds, then a short test forecast, then
post-processing, then grading and HTML, then scheduling. Each step MUST have a runnable
check (for example, a build succeeds, a test run completes, an output parses) that passes
before the next step starts. Pure logic such as grading and unit conversion MUST have
automated tests.

## Operational Constraints

- The default site is Mystic, VIC. Additional sites MUST be added through configuration,
  not code changes.
- Output MUST be static files that can be served locally or pushed to free static
  hosting.
- The project MUST NOT collect or store personal data.
- Secrets, if ever needed, MUST NOT be committed to the repository.

## Development Workflow

- Specs and plans are produced with Spec Kit and MUST be checked against this
  constitution before implementation begins.
- Changes to the Dockerfile, domain definition or grading config MUST state their
  effect on runtime, memory and forecast output.
- Large downloads (GFS, static geography) MUST be cached outside the image so rebuilds
  do not refetch them.

## Governance

This constitution supersedes other project practices. Amendments MUST be recorded in
this file with a version bump and date. Versioning follows semantic rules: MAJOR for
removing or redefining a principle, MINOR for adding a principle or materially expanding
guidance, PATCH for clarifications. Each plan and review MUST verify compliance; any
deviation MUST be justified in writing in the plan.

**Version**: 1.3.0 | **Ratified**: 2026-10-03 | **Last Amended**: 2026-10-04
