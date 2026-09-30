"""JSA Gen AI exposure scores (one row per occupation x measure x score version)."""

import sys

import pandas as pd
from _common import PARQUET

df = pd.read_parquet(PARQUET / "exposure_scores.parquet")
df["published_at"] = df["published_at"].dt.strftime("%Y-%m-%d")
df.to_json(sys.stdout, orient="records")
