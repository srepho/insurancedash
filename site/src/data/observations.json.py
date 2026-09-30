"""All current observations plus registry metadata, for charts and provenance."""

import json
import sys

import pandas as pd
from _common import PARQUET

from ingest.registry import load

reg = load()
frames = [pd.read_parquet(p) for p in sorted((PARQUET / "observations").glob("*.parquet"))]
obs = pd.concat(frames, ignore_index=True).sort_values(["series_id", "period_start"])
rows = [
    {
        "id": r.series_id,
        "start": f"{r.period_start:%Y-%m-%d}",
        "end": f"{r.period_end:%Y-%m-%d}",
        "value": None if pd.isna(r.value) else round(float(r.value), 6),
        "status": r.observation_status,
    }
    for r in obs.itertuples()
]
meta = {}
for s in reg.series:
    g = obs[(obs["series_id"] == s["series_id"]) & (obs["observation_status"] == "observed")]
    meta[s["series_id"]] = {
        **{
            k: s.get(k)
            for k in (
                "title",
                "source",
                "unit",
                "frequency",
                "adjustment",
                "definition",
                "measure_basis",
                "transformation",
                "source_url",
                "release_cadence",
                "breaks",
                "dimensions",
                "valid_from",
            )
        },
        "first": None if g.empty else f"{g['period_end'].min():%Y-%m-%d}",
        "last": None if g.empty else f"{g['period_end'].max():%Y-%m-%d}",
        "retrieved_at": None if g.empty else f"{g['retrieved_at'].max():%Y-%m-%d}",
    }
json.dump({"series": meta, "rows": rows}, sys.stdout, separators=(",", ":"))
