# Contract: configuration files

Both files are TOML and are validated when loaded (and by `ffforecast check`). Field meanings are in
[data-model.md](../data-model.md). Last reviewed against the build: 2026-10-03.

## `config/site.mystic.toml`

Top-level keys (these must come before any table): `id`, `name`, `lat`, `lon`, `elevation_m`,
`timezone`, `station_default`.

Tables: `[domain.d01]`, `[domain.d02]`, `[links]`, and one `[[station_charts]]` per chart period.

Validation:

- `lat` is within -90 to 90 and `lon` within -180 to 180; the required keys are present.
- Every `[[station_charts]]` has `id`, `label`, `heading`, `link`, `page` and `chart`; `page` and
  `chart` are https addresses; ids are unique; `station_default` is one of the ids.

## `config/rules.toml`

Keys: `version`, `source`; tables `[wind]`, `[direction]`, `[shear]`, `[thermal]` and
`[weather]`.

Validation:

- `version` is a positive integer and MUST increase on any threshold change; `source` is non-empty.
- Speed keys carry their units in their names (`_mph` or `_kph`).
- Wind bands are in order (green, orange, red); the sector half-width is above 0 and at most 180.
- In `[thermal]` (calibration values, all optional): `critical_updraft_ms`, `quality_full_updraft_ms` above 0; `usable_depth_fraction` above 0 and at most 1; the quality wind threshold and penalty not negative.
- In `[weather]`: light rain does not exceed heavy rain, the overdevelopment storm level does not
  exceed the storm level, and the orange gust level does not exceed the red. The whole table is
  optional.
