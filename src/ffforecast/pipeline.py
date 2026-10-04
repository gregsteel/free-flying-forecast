"""The `run` pipeline: stages, retry for late data, and last-ok-forecast safety."""

from __future__ import annotations

import shutil
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .state import RunRecord, State, now_iso

EXIT_OK = 0
EXIT_NO_DATA = 2
EXIT_FAILED = 3


@dataclass
class Stage:
    name: str
    fn: Callable[[Path], None]  # receives the staging directory for this run


def swap_in(staging: Path, publish_dir: Path) -> None:
    """Replace publish_dir with staging. Done only after every stage succeeded.

    Renaming is atomic, but it fails when publish_dir is a mount point (a Docker volume) or on another
    filesystem than staging; then the contents are copied across instead."""
    prev = publish_dir.with_name(publish_dir.name + ".prev")
    if prev.exists():
        shutil.rmtree(prev)
    try:
        if publish_dir.exists():
            publish_dir.rename(prev)
        staging.rename(publish_dir)
        return
    except OSError:
        pass
    _swap_in_by_copy(staging, publish_dir, prev)


def _swap_in_by_copy(staging: Path, publish_dir: Path, prev: Path) -> None:
    if prev.exists() and not publish_dir.exists():
        prev.rename(publish_dir)  # a rename half-done: put the old output back first
    if publish_dir.exists():
        shutil.copytree(publish_dir, prev, dirs_exist_ok=True)
        for child in publish_dir.iterdir():
            shutil.rmtree(child) if child.is_dir() else child.unlink()
    else:
        publish_dir.mkdir(parents=True)
    for child in staging.iterdir():
        shutil.move(child, publish_dir / child.name)  # shutil.move copes with other filesystems
    staging.rmdir()


def run_pipeline(
    find_cycle: Callable[[], str | None],
    stages: list[Stage] | Callable[[str], list[Stage]],
    state: State,
    publish_dir: Path,
    work_dir: Path,
    retries: int = 6,
    retry_sleep_s: float = 600,
    force: bool = False,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> tuple[int, RunRecord]:
    started = clock()
    rec = RunRecord(cycle="", started_at=now_iso())

    def finish(outcome: str, stage: str = "") -> RunRecord:
        rec.outcome = outcome
        rec.failed_stage = stage
        rec.finished_at = now_iso()
        rec.duration_s = round(clock() - started, 1)
        state.record(rec)
        return rec

    cycle = None
    for attempt in range(retries + 1):
        cycle = find_cycle()
        if cycle is not None:
            break
        if attempt < retries:
            sleep(retry_sleep_s)
    if cycle is None:
        return EXIT_NO_DATA, finish("no_data", "fetch")
    rec.cycle = cycle

    if state.is_duplicate(cycle) and not force:
        return EXIT_OK, finish("skipped_duplicate")

    staging = work_dir / f"staging-{cycle.replace(':', '')}"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    stage_list = stages(cycle) if callable(stages) else stages
    for stage in stage_list:
        try:
            stage.fn(staging)
        except Exception as e:  # noqa: BLE001 - any stage failure must keep the last good page
            shutil.rmtree(staging, ignore_errors=True)
            print(f"stage '{stage.name}' failed: {e}")
            return EXIT_FAILED, finish("failed", stage.name)
    swap_in(staging, publish_dir)
    return EXIT_OK, finish("published")
