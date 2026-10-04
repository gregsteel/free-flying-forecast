"""Run state, run log and pruning."""

from __future__ import annotations

import fcntl
import json
import shutil
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

OUTCOMES = ("published", "failed", "skipped_duplicate", "no_data")


@dataclass
class RunRecord:
    cycle: str
    started_at: str
    finished_at: str = ""
    duration_s: float = 0.0
    outcome: str = "failed"
    failed_stage: str = ""
    peak_mem_mb: float = 0.0


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class State:
    def __init__(self, root: Path):
        self.root = root
        self.path = root / "state.json"
        self.log_path = root / "run-log.jsonl"

    @contextmanager
    def lock(self, wait: bool = True) -> Iterator[bool]:
        """Hold the run lock so a run and the AUSRASP poller never build the page at once.
        Yields False (without waiting) when `wait` is False and someone else holds it."""
        self.root.mkdir(parents=True, exist_ok=True)
        with (self.root / "run.lock").open("w") as f:
            try:
                fcntl.flock(f, fcntl.LOCK_EX | (0 if wait else fcntl.LOCK_NB))
            except BlockingIOError:
                yield False
                return
            try:
                yield True
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)

    def last_published_cycle(self) -> str | None:
        if not self.path.exists():
            return None
        try:
            return json.loads(self.path.read_text()).get("last_published_cycle")
        except (json.JSONDecodeError, OSError):
            return None

    def is_duplicate(self, cycle: str) -> bool:
        return self.last_published_cycle() == cycle

    def record(self, rec: RunRecord) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        with self.log_path.open("a") as f:
            f.write(json.dumps(asdict(rec)) + "\n")
        if rec.outcome == "published":
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(
                json.dumps(
                    {"last_published_cycle": rec.cycle, "published_at": rec.finished_at}, indent=2
                )
            )
            tmp.replace(self.path)  # atomic: a failed run never touches this

    def prune_runs(self, runs_dir: Path, keep: int = 4) -> list[Path]:
        """Delete all but the newest `keep` per-cycle run directories."""
        if not runs_dir.exists():
            return []
        dirs = sorted((p for p in runs_dir.iterdir() if p.is_dir()), key=lambda p: p.name)
        old = dirs[:-keep] if keep > 0 else dirs
        for p in old:
            shutil.rmtree(p, ignore_errors=True)
        return old
