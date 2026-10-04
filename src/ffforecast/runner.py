"""Assemble the stages for `ffforecast run`."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

from . import ausrasp, gfs
from .config import Rules, Site
from .gfsmode import blocks_from_samples, outlook_after_blocks
from .models import Forecast
from .outlook import deaccumulate_flux, read_flux_samples, read_gfs_samples
from .pipeline import Stage
from .publish import publish_site
from .render import render_to_dir

GFS_MODEL_LABEL = "NOAA GFS 0.25 degree (no regional model)"


@dataclass
class RunConfig:
    site: Site
    rules: Rules
    cache_dir: Path
    publish_remote: str | None = None
    publish_branch: str = "gh-pages"
    publish_key: Path | None = None
    now: datetime | None = None
    last_hour: int = 192  # day 7 can reach about f180 when the run starts after the day's flying


def make_finder(cfg: RunConfig, session: requests.Session):
    def find() -> str | None:
        c = gfs.latest_available_cycle(session, now=cfg.now, check_fhour=cfg.last_hour)
        return c.label if c else None

    return find


def cycle_from_label(label: str) -> gfs.Cycle:
    return gfs.Cycle(label[:4] + label[5:7] + label[8:10], int(label[11:13]))


def gfs_stages(
    cfg: RunConfig,
    cycle_label: str,
    session: requests.Session,
    refresh_ausrasp: bool = True,
) -> list[Stage]:
    """fetch, (ausrasp), diagnose, render, (publish). `refresh_ausrasp` is False when the caller
    has just refreshed AUSRASP itself (the poller), so the page is rebuilt from what is stored."""
    cycle = cycle_from_label(cycle_label)
    now = cfg.now or datetime.now(UTC)
    thermal: dict = {}
    block_h, outlook_h, first_day = gfs.plan_hours(cycle, now, cfg.site.timezone)
    hours = sorted(set(block_h + outlook_h))
    files: list[Path] = []
    flux_files: list[Path] = []

    def fetch(staging: Path) -> None:
        d = cfg.cache_dir / "gfs" / cycle.label.replace(":", "")
        for fh in hours:
            files.append(gfs.fetch_forecast_hour(session, cycle, fh, d))
        # the heating the hour before each block, to recover the hourly value (see outlook.py)
        for fh in gfs.flux_prev_hours(block_h):
            try:
                flux_files.append(gfs.fetch_forecast_hour(session, cycle, fh, d, gfs.FLUX_FIELDS))
            except Exception as e:  # noqa: BLE001 - keep the window average for that block instead
                print(f"note: no heating for forecast hour {fh} ({e}); using the window average")

    def thermal_source(staging: Path) -> None:
        """AUSRASP's thermal height and updraft. Never fails the run: the page falls back to the
        global-model estimate, block by block, for whatever AUSRASP could not supply."""
        a = cfg.site.ausrasp
        if refresh_ausrasp and a.enabled:
            r = ausrasp.refresh(a, cfg.site, cfg.cache_dir, session, now=lambda: now)
            if r.reason:
                print(f"note: AUSRASP unavailable ({r.reason}); using stored values if fresh")
        found, notes = ausrasp.thermal_lookup(cfg.cache_dir, a, now)
        thermal.update(found)
        for n in notes:
            print(f"note: AUSRASP {n}")

    def diagnose(staging: Path) -> None:
        samples = read_gfs_samples(files, cfg.site.lat, cfg.site.lon)
        samples = deaccumulate_flux(
            samples, read_flux_samples(flux_files, cfg.site.lat, cfg.site.lon)
        )
        if not samples:
            raise RuntimeError("no usable GFS samples were read")
        blocks = blocks_from_samples(samples, cfg.rules, cfg.site, first_day, thermal=thermal)
        outlook = outlook_after_blocks(samples, cfg.rules, cfg.site, first_day, thermal=thermal)
        if not blocks:
            raise RuntimeError("no forecast blocks could be built")
        n_a = sum(b.thermal_source == "ausrasp" for b in blocks)
        print(
            f"thermal: ausrasp ({n_a} of {len(blocks)} blocks)"
            if n_a
            else "thermal: gfs estimate (AUSRASP not used)"
        )
        fc = Forecast(
            site=cfg.site.id,
            model=GFS_MODEL_LABEL,
            cycle=cycle.label,
            generated_at=now.astimezone(ZoneInfo(cfg.site.timezone)).isoformat(timespec="seconds"),
            rules_version=cfg.rules.version,
            blocks=blocks,
            outlook=outlook,
        )
        (staging / "forecast.json").write_text(json.dumps(fc.to_dict(), indent=2))

    def render(staging: Path) -> None:
        fc = Forecast.from_dict(json.loads((staging / "forecast.json").read_text()))
        render_to_dir(fc, cfg.site, cfg.rules, staging)

    stages = [
        Stage("fetch", fetch),
        Stage("ausrasp", thermal_source),
        Stage("diagnose", diagnose),
        Stage("render", render),
    ]
    if cfg.publish_remote:
        remote = cfg.publish_remote

        def publish(staging: Path) -> None:
            publish_site(staging, remote, cfg.publish_branch, cfg.publish_key)

        stages.append(Stage("publish", publish))
    return stages
