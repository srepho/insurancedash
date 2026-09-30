"""APRA Quarterly General Insurance Performance Statistics.

Only the current basis (AASB 17 / new reporting framework, from 1 July 2023) is handled
here. The historical (pre-July 2023) database is a different series family and must never
be spliced onto these series.
"""

from __future__ import annotations

import io
import re

import pandas as pd

from ingest.common import (
    SourceFormatError,
    SourceResult,
    derive_ratios,
    fetch,
    finalise,
    find_header_row,
    find_links,
    month_end,
    quarter_start,
    require_columns,
    utcnow,
    vintage_id,
)

LANDING = "https://www.apra.gov.au/quarterly-general-insurance-performance-statistics"
SHEET = "Database"
DIMENSIONS = [
    "Data item",
    "Category",
    "Subject",
    "Stock or flow",
    "Industry segment",
    "Industry segment group",
    "Class of business",
    "Class of business category",
    "Class of business group",
    "Counterparty grade",
    "State and territory",
    "Stress scenario type",
]
REQUIRED = ["Reporting Period", *DIMENSIONS, "Value"]
SUPPRESSED = "*"


def latest_database_url(html: str) -> str:
    """Pick the current-basis database xlsx (not the historical or institution-level ones)."""
    links = [
        (u, t)
        for u, t in find_links(html, LANDING, r"\.xlsx")
        if re.search(r"performance statistics database", t, re.I) and not re.search(r"historical", t, re.I)
    ]
    if not links:
        raise SourceFormatError("APRA: current-basis database link not found on landing page")
    if len(links) > 1:
        raise SourceFormatError(f"APRA: ambiguous database links: {[t for _, t in links]}")
    return links[0][0]


def parse_database(content: bytes | str) -> pd.DataFrame:
    src = io.BytesIO(content) if isinstance(content, bytes) else content
    raw = pd.read_excel(src, sheet_name=SHEET, header=None)
    h = find_header_row(raw, ["Reporting Period", "Data item", "Value"])
    df = raw.iloc[h + 1 :].copy()
    df.columns = [str(c).strip() for c in raw.iloc[h]]
    require_columns(df, REQUIRED, "APRA Database")
    df = df.dropna(subset=["Reporting Period", "Data item"]).reset_index(drop=True)
    df["Reporting Period"] = pd.to_datetime(df["Reporting Period"])
    return df


def select(df: pd.DataFrame, filters: dict[str, str | None]) -> pd.DataFrame:
    """Exact-match every dimension. Dimensions not named in `filters` must be blank, so a
    selection can never silently pick up state or segment breakdowns."""
    unknown = set(filters) - set(DIMENSIONS)
    if unknown:
        raise ValueError(f"APRA: unknown dimensions {unknown}")
    mask = pd.Series(True, index=df.index)
    for dim in DIMENSIONS:
        want = filters.get(dim)
        mask &= df[dim].isna() if want is None else df[dim].astype("string").str.strip().eq(want)
    return df[mask]


def to_observations(content: bytes, series: dict[str, dict[str, str | None]], retrieved_at=None) -> pd.DataFrame:
    """Build observations for {our_series_id: {dimension: value}}."""
    df = parse_database(content)
    vid = vintage_id(content)
    retrieved_at = retrieved_at or utcnow()
    frames = []
    for series_id, filters in series.items():
        sel = select(df, filters).sort_values("Reporting Period")
        if sel.empty:
            raise SourceFormatError(f"APRA: no rows for {series_id} with {filters}")
        if sel["Reporting Period"].duplicated().any():
            raise SourceFormatError(f"APRA: filters for {series_id} are not unique per period")
        raw = sel["Value"]
        suppressed = raw.astype("string").str.strip().eq(SUPPRESSED).fillna(False)
        value = pd.to_numeric(raw.where(~suppressed), errors="coerce")
        bad = value.isna() & ~suppressed & raw.notna()
        if bad.any():
            raise SourceFormatError(f"APRA {series_id}: non-numeric values {raw[bad].unique()[:5].tolist()}")
        status = pd.Series("observed", index=sel.index)
        status[suppressed] = "suppressed"
        status[value.isna() & ~suppressed] = "missing"
        frames.append(
            pd.DataFrame(
                {
                    "series_id": series_id,
                    "period_start": quarter_start(sel["Reporting Period"]),
                    "period_end": month_end(sel["Reporting Period"]),
                    "value": value,
                    "observation_status": status,
                    "source_released_at": pd.NaT,
                    "retrieved_at": pd.Timestamp(retrieved_at),
                    "vintage_id": vid,
                }
            )
        )
    return finalise(pd.concat(frames, ignore_index=True))


def collect(entries: list[dict], sess) -> SourceResult:
    content = fetch(latest_database_url(fetch(LANDING, sess).decode("utf-8", "replace")), sess)
    direct = {e["series_id"]: e["source_key"] for e in entries if e.get("source_key")}
    obs = to_observations(content, direct)
    derived = derive_ratios(obs, entries)
    return SourceResult(finalise(pd.concat([obs, derived], ignore_index=True)), [("qgips_database.xlsx", content)])
