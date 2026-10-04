"""Forecast data classes (see specs/001-free-flying-forecast/data-model.md)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

Verdict = str  # "ok" | "good" | "strong" | "poor" | "turbulent" | "dangerous"
# Listed in the order the Guide shows them. Strong is powerful, not simply "better": it demands experience.
VERDICTS = ("ok", "good", "strong", "poor", "turbulent", "dangerous")
SHEAR_CLASSES = ("light", "moderate", "strong")
# 2: grades renamed Good/Great/Pumping to Ok/Good/Strong (2026-10-04)
# 3: estimated gusts, AUSRASP wind and sunshine added (2026-10-05); older files still read
SCHEMA_VERSION = 3
# Verdict names used by forecast files made with schema 1
LEGACY_VERDICTS = {"good": "ok", "great": "good", "pumping": "strong"}
DETAILED_DAYS = 4  # days 1 to 4: 2-hour blocks
OUTLOOK_DAYS = 3  # days 5 to 7: one low-confidence summary per day


@dataclass
class Wind:
    dir_deg: float
    kph: float


@dataclass
class ForecastBlock:
    start: str  # ISO 8601 with offset
    wind_ground: Wind
    wind_aloft: Wind
    shear: str
    thermal_height_m: float
    thermal_quality_pct: int
    updraft_ms: float
    temp_ground_c: float
    temp_air_c: float
    verdict_pg: Verdict = "poor"
    verdict_hg: Verdict = "poor"
    reasons: list[str] = field(default_factory=list)  # for paragliders
    reasons_hg: list[str] = field(default_factory=list)  # for hang gliders
    rain_mm_h: float = 0.0
    cape_j_kg: float = 0.0
    gust_kph: float = 0.0
    wind_launch: Wind | None = None  # wind at launch altitude (interpolated)
    # Where the thermal height and updraft came from: "ausrasp" (its run start in thermal_run) or "gfs"
    thermal_source: str = "gfs"
    thermal_run: str = ""
    # Estimated gusts (kph) at launch and at the top of the thermals; None in older forecasts
    gust_launch_kph: float | None = None
    gust_aloft_kph: float | None = None
    # AUSRASP's 10 m wind and its wind at the top of the thermals (kph), when it was read
    wind_ausrasp_kph: float | None = None
    wind_top_kph: float | None = None
    # Share of possible sunshine reaching the ground (percent) and where it came from
    sun_pct: int | None = None
    sun_source: str = ""  # "ausrasp" or "gfs"


@dataclass
class DailyOutlook:
    date: str
    wind: Wind
    verdict: Verdict  # paraglider
    confidence: str = "low"
    rain_mm_h: float = 0.0
    cape_j_kg: float = 0.0
    verdict_hg: Verdict = ""  # hang glider; empty in forecasts made before it existed
    thermal_source: str = "gfs"


@dataclass
class Forecast:
    site: str
    model: str
    cycle: str
    generated_at: str
    rules_version: int
    blocks: list[ForecastBlock] = field(default_factory=list)
    outlook: list[DailyOutlook] = field(default_factory=list)
    schema: int = SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Forecast:
        if d.get("schema", 1) < 2:  # an older file: translate its grade names
            d = _modernise(d)
        blocks = [
            ForecastBlock(
                **{
                    **{k: v for k, v in b.items() if k != "xc_rating"},  # dropped 2026-10-04
                    "wind_ground": Wind(**b["wind_ground"]),
                    "wind_aloft": Wind(**b["wind_aloft"]),
                    "wind_launch": Wind(**b["wind_launch"]) if b.get("wind_launch") else None,
                }
            )
            for b in d.get("blocks", [])
        ]
        outlook = [DailyOutlook(**{**o, "wind": Wind(**o["wind"])}) for o in d.get("outlook", [])]
        return cls(
            site=d["site"],
            model=d["model"],
            cycle=d["cycle"],
            generated_at=d["generated_at"],
            rules_version=d["rules_version"],
            blocks=blocks,
            outlook=outlook,
            schema=d.get("schema", SCHEMA_VERSION),
        )


def _modernise(d: dict[str, Any]) -> dict[str, Any]:
    """A copy of a schema 1 forecast with its grades under the current names."""

    def fix(row: dict[str, Any], keys: tuple[str, ...]) -> dict[str, Any]:
        return {**row, **{k: LEGACY_VERDICTS.get(row[k], row[k]) for k in keys if k in row}}

    return {
        **d,
        "blocks": [fix(b, ("verdict_pg", "verdict_hg")) for b in d.get("blocks", [])],
        "outlook": [fix(o, ("verdict", "verdict_hg")) for o in d.get("outlook", [])],
        "schema": 2,
    }
