# Research: AUSRASP Thermal Source

Decisions for 003. The investigation of what AUSRASP publishes is in
[001 research section 23](../001-free-flying-forecast/research.md).

## 1. Hours and size of what is fetched

- **Decision**: fetch only the hourly block times (nine a day, 10:00 to 18:00 local), for `hglider` and `wstar`: 18 files a day, 126 for all seven days (the page first had four blocks a day and 56 files; it changed to hourly on 2026-10-04).
- **Rationale**: a full-resolution grid is about 94 KB for `hglider` (33.6 KB with gzip, which the server offers) and about 42 KB for `wstar`. With nine hours a day the whole seven days is about 5.7 MB compressed. The spec's limits are therefore 150 requests an hour and 25 MB a day (first 12 an hour, then 60 an hour and 10 MB, as the page's block count grew).
- **Alternatives**: byte ranges of the first rows (the server answers 206 but with compression the range applies to the compressed stream, so it saves nothing reliable); fetching every hour (4 times the load for values the page does not show).

## 2. Which AUSRASP hour a block uses

- **Decision**: the hour valid at the block's start time.
- **Rationale**: the GFS values on the page are point values at the block start and the owner compares at one hour at a time. Taking the highest of two hours would bias the page high, which is the complaint that started this work.

## 3. Whole-number updraft

- **Decision**: Great at 3 m/s or more, Pumping at 4 m/s or more for AUSRASP, held in the rules file, with the Guide generated from them.
- **Rationale**: the owner's rule is Great at 2.5 m/s or more; applied to whole numbers that is 3. Pumping was 3.5, which is 4. Starting values to be confirmed on real days.
- **Alternative** (not taken, the owner chose plain AUSRASP): keep GFS's finer updraft to split the tiers.

## 4. Detecting changes

- **Decision**: poll the manifest, never the data files; fetch data only for days whose stamp changed.
- **Rationale**: the manifest is about 300 bytes, sent with `no-store`, and (per the site's own code comments) its stamp changes only when a day is re-run. The data files are cached by the site for a day, so a changed stamp is the reliable signal.
- **Schedule**: no published schedule exists. Observed on 2026-10-03: runs follow the 00Z and 12Z GFS cycles, each day separately, completing between roughly 04:50Z and 19:40Z. The default windows bracket those and every stamp change is logged, so the schedule can be corrected after a week.

## 5. Triggering the poller

- **Decision**: a second launchd job every 20 minutes running `ffforecast poll --if-due`, which decides from the configured windows whether to act.
- **Rationale**: launchd's calendar syntax cannot express "every 20 minutes in these two windows" without dozens of entries; keeping the schedule in the project's configuration makes it testable and changeable without touching launchd.

## 6. Rebuild without repeating the GFS work

- **Decision**: rerun the normal stages with `force` for the cycle in the state file.
- **Rationale**: the GFS downloads are cached by file; only the AUSRASP store differs. This reuses tested code instead of adding a second render path.

## 7. Politeness

- **Decision**: user agent `FreeFlyingForecast/<version> (+contact)`, gzip, sequential requests with a 1 s pause, 150 requests an hour and 25 MB a day ceilings, back-off of 6 hours after a refusal, an off switch.
- **Rationale**: the site has no stated terms; a donation-funded volunteer service deserves a low, identifiable, easily stopped load.

## 8. Which cells (2026-10-03, owner request)

- **Decision**: the highest height and the highest updraft in the 3 by 3 block of cells around the launch (`cell_radius = 1`), each taken separately.
- **Rationale**: the launch is on a mountain and the nearest 4 km cell can read low; on 4 Oct 1500 AES the nearest cell gave 1844 m while the cells around it ranged from 1106 to 1885 m. The owner asked for the highest of the surrounding cells.
- **Consequence**: this reads higher than a single cell by design, and the height and updraft can come from different cells. The setting is `[ausrasp] cell_radius` (0 means one cell); stored days record the radius they were read with and are fetched again if it changes.
- **Alternatives**: the four cells whose centres enclose the launch (a smaller block); an average (rejected, it would pull the figure back down towards the valley).

## 9. AUSRASP's clock (found 2026-10-04)

- **Finding**: the label on a file's time is AES or AED depending on when the run was made. The first fetch after daylight saving began showed `Valid 1000 AED (2300Z)` where earlier runs showed `Valid 1500 AES (0500Z)` for the same date.
- **Decision**: take the offset from the header (local hour less the UTC hour, which must be 10 or 11), never from an assumption; ask for the file hour by guessing the clock from the stamp and correct the guess from the first file; reject any file not valid at the expected UTC time.
- **Cost of the mistake**: between the first build and the fix, runs labelled AED (the 4th and later days made after 16:00Z on 3 Oct) were read one hour early; those stored days were discarded (format 2) and read again.
