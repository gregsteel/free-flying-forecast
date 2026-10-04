"""A record of every forecast made for each day, kept so it can be compared with what happened.

Each local date has one file, `history/<date>.jsonl`. A line is one snapshot: when the forecast
was made, which model cycle and AUSRASP runs it used, and that date's blocks in full (winds,
estimated gusts, sunshine, thermals and both grades). A rebuild that changes nothing for a date is
not written again. See docs/verification.md for how the record is meant to be used.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from pathlib import Path
from zoneinfo import ZoneInfo

from .models import Forecast


def history_file(history_dir: Path, date: str) -> Path:
    return history_dir / f"{date}.jsonl"


def _digest(blocks: list[dict]) -> str:
    return hashlib.sha1(json.dumps(blocks, sort_keys=True).encode()).hexdigest()[:12]


def record(history_dir: Path, fc: Forecast, tz: str) -> list[str]:
    """Append a snapshot of `fc` to the file of each local date it has blocks for. Returns the
    dates written (a date whose blocks are the same as the last snapshot's is left alone)."""
    from datetime import datetime

    zone = ZoneInfo(tz)
    by_date: dict[str, list[dict]] = {}
    for b in fc.blocks:
        date = datetime.fromisoformat(b.start).astimezone(zone).date().isoformat()
        by_date.setdefault(date, []).append(asdict(b))
    written = []
    for date, blocks in sorted(by_date.items()):
        digest = _digest(blocks)
        path = history_file(history_dir, date)
        if path.exists():
            last = path.read_text().splitlines()[-1:]
            if last and json.loads(last[0]).get("digest") == digest:
                continue
        history_dir.mkdir(parents=True, exist_ok=True)
        line = {
            "issued": fc.generated_at,
            "cycle": fc.cycle,
            "model": fc.model,
            "rules_version": fc.rules_version,
            "thermal_runs": sorted({b["thermal_run"] for b in blocks if b["thermal_run"]}),
            "digest": digest,
            "blocks": blocks,
        }
        with path.open("a") as f:
            f.write(json.dumps(line) + "\n")
        written.append(date)
    return written


def read_day(history_dir: Path, date: str) -> list[dict]:
    """Every snapshot kept for a date, oldest first. Empty when there is none."""
    path = history_file(history_dir, date)
    if not path.exists():
        return []
    return [json.loads(x) for x in path.read_text().splitlines() if x.strip()]
