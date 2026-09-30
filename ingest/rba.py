"""RBA statistical tables (CSV with multi-row metadata headers)."""

from __future__ import annotations

import csv
import io
from datetime import datetime

import pandas as pd

from ingest.common import SourceFormatError, SourceResult, fetch, finalise, utcnow, vintage_id

BASE = "https://www.rba.gov.au/statistics/tables/csv/{table}-data.csv"
META_LABELS = ("Title", "Description", "Frequency", "Type", "Units", "Source", "Publication date", "Series ID")
DATE_FORMATS = ("%d-%b-%Y", "%b-%Y", "%d/%m/%Y", "%Y-%m-%d")


def table_url(table: str) -> str:
    return BASE.format(table=table.lower())


def _parse_date(s: str) -> datetime | None:
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def parse_table(content: bytes) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (metadata, values).

    metadata: one row per RBA series id with the header labels as columns.
    values: long frame (rba_id, date, raw) including blank cells as raw == "".
    """
    rows = list(csv.reader(io.StringIO(content.decode("utf-8-sig"))))
    meta: dict[str, list[str]] = {}
    data_start = None
    for i, row in enumerate(rows):
        if not row or not row[0].strip():
            continue
        label = row[0].strip()
        if label in META_LABELS:
            meta[label] = [c.strip() for c in row[1:]]
            if label == "Series ID":
                data_start = i + 1
                break
    if data_start is None or "Series ID" not in meta:
        raise SourceFormatError("RBA: 'Series ID' header row not found")
    for label in ("Title", "Units", "Frequency"):
        if label not in meta:
            raise SourceFormatError(f"RBA: metadata row '{label}' not found")

    ids = meta["Series ID"]
    width = len(ids)
    md = pd.DataFrame({k: (v + [""] * width)[:width] for k, v in meta.items()})
    md = md[md["Series ID"] != ""].set_index("Series ID")

    records = []
    for row in rows[data_start:]:
        if not row or not row[0].strip():
            continue
        d = _parse_date(row[0].strip())
        if d is None:
            raise SourceFormatError(f"RBA: unparseable date {row[0]!r}")
        cells = (row[1:] + [""] * width)[:width]
        for sid, cell in zip(ids, cells, strict=True):
            if sid:
                records.append((sid, d, cell.strip()))
    values = pd.DataFrame(records, columns=["rba_id", "date", "raw"])
    return md, values


def to_observations(content: bytes, series: dict[str, str], retrieved_at=None) -> pd.DataFrame:
    """Build observations for {rba_series_id: our_series_id}.

    Blank cells after a series' first observation are recorded as `missing` (value NULL),
    never as zero. Blank cells before the first observation are outside the series' coverage.
    """
    md, values = parse_table(content)
    absent = [sid for sid in series if sid not in md.index]
    if absent:
        raise SourceFormatError(f"RBA: expected series not in table: {absent}")

    vid = vintage_id(content)
    retrieved_at = retrieved_at or utcnow()
    frames = []
    for rba_id, series_id in series.items():
        v = values[values["rba_id"] == rba_id].sort_values("date").reset_index(drop=True)
        num = pd.to_numeric(v["raw"].replace("", None), errors="coerce")
        if (v["raw"].ne("") & num.isna()).any():
            bad = v.loc[v["raw"].ne("") & num.isna(), "raw"].unique()[:5]
            raise SourceFormatError(f"RBA {rba_id}: non-numeric values {list(bad)}")
        first = num.first_valid_index()
        if first is None:
            raise SourceFormatError(f"RBA {rba_id}: no observations")
        v, num = v.loc[first:], num.loc[first:]
        pub = md.loc[rba_id].get("Publication date", "")
        released = _parse_date(pub) if pub else None
        frames.append(
            pd.DataFrame(
                {
                    "series_id": series_id,
                    "period_start": v["date"],
                    "period_end": v["date"],
                    "value": num,
                    "observation_status": ["observed" if pd.notna(x) else "missing" for x in num],
                    "source_released_at": pd.Timestamp(released) if released else pd.NaT,
                    "retrieved_at": pd.Timestamp(retrieved_at),
                    "vintage_id": vid,
                }
            )
        )
    return finalise(pd.concat(frames, ignore_index=True))


def collect(entries: list[dict], sess) -> SourceResult:
    """Fetch each RBA table named in the registry and extract its registered series."""
    by_table: dict[str, dict[str, str]] = {}
    for e in entries:
        by_table.setdefault(e["source_key"]["table"], {})[e["source_key"]["series_id"]] = e["series_id"]
    frames, raw_files = [], []
    for table, series in sorted(by_table.items()):
        content = fetch(table_url(table), sess)
        md, _ = parse_table(content)
        for rba_id in series:
            src = md.loc[rba_id].get("Source", "") if rba_id in md.index else ""
            if src and src != "RBA":
                raise SourceFormatError(f"RBA {rba_id}: sourced from {src}, not licensed under RBA CC BY")
        frames.append(to_observations(content, series))
        raw_files.append((f"{table}-data.csv", content))
    return SourceResult(finalise(pd.concat(frames, ignore_index=True)), raw_files)
