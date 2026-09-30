"""Load and validate the series registry (registry/series.yaml)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

REGISTRY_PATH = Path(__file__).resolve().parent.parent / "registry" / "series.yaml"

SERIES_FIELDS = {
    "series_id",
    "source",
    "title",
    "source_key",
    "dimensions",
    "unit",
    "frequency",
    "adjustment",
    "definition",
    "measure_basis",
    "transformation",
    "source_url",
    "release_cadence",
    "breaks",
}
SOURCE_FIELDS = {"name", "landing_url", "licence", "required", "overdue_after_days", "table"}
FREQUENCIES = {"daily", "monthly", "quarterly", "annual"}
ADJUSTMENTS = {"original", "seasonally adjusted", "trend"}


class RegistryError(ValueError):
    pass


@dataclass(frozen=True)
class Registry:
    sources: dict[str, dict[str, Any]]
    series: list[dict[str, Any]]

    def by_id(self) -> dict[str, dict[str, Any]]:
        return {s["series_id"]: s for s in self.series}

    def for_source(self, source: str) -> list[dict[str, Any]]:
        return [s for s in self.series if s["source"] == source]

    def ids_for_source(self, source: str) -> set[str]:
        return {s["series_id"] for s in self.for_source(source)}


def validate(raw: dict[str, Any]) -> Registry:
    errors: list[str] = []
    sources = raw.get("sources") or {}
    series = raw.get("series") or []
    for name, src in sources.items():
        missing = SOURCE_FIELDS - set(src)
        if missing:
            errors.append(f"source {name}: missing fields {sorted(missing)}")
        if not isinstance(src.get("required"), bool):
            errors.append(f"source {name}: 'required' must be true/false")

    seen: set[str] = set()
    for i, s in enumerate(series):
        sid = s.get("series_id", f"<entry {i}>")
        missing = SERIES_FIELDS - set(s)
        if missing:
            errors.append(f"{sid}: missing fields {sorted(missing)}")
        if sid in seen:
            errors.append(f"{sid}: duplicate series_id")
        seen.add(sid)
        if s.get("source") not in sources:
            errors.append(f"{sid}: unknown source {s.get('source')!r}")
        if s.get("frequency") not in FREQUENCIES:
            errors.append(f"{sid}: frequency {s.get('frequency')!r} not in {sorted(FREQUENCIES)}")
        if s.get("adjustment") not in ADJUSTMENTS:
            errors.append(f"{sid}: adjustment {s.get('adjustment')!r} not in {sorted(ADJUSTMENTS)}")
        t = s.get("transformation")
        if t and t.get("type") == "ratio":
            for ref in ("numerator", "denominator"):
                if t.get(ref) not in {x.get("series_id") for x in series}:
                    errors.append(f"{sid}: transformation {ref} {t.get(ref)!r} is not a registered series")
        if s.get("source_key") is None and not t:
            errors.append(f"{sid}: needs a source_key or a transformation")
        for b in s.get("breaks") or []:
            if not {"date", "description"} <= set(b):
                errors.append(f"{sid}: breaks need date and description")
    if errors:
        raise RegistryError("invalid registry:\n  " + "\n  ".join(errors))
    return Registry(sources=sources, series=series)


def load(path: Path = REGISTRY_PATH) -> Registry:
    return validate(yaml.safe_load(path.read_text(encoding="utf-8")))
