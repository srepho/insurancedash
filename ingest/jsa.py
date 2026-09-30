"""Jobs and Skills Australia: Internet Vacancy Index (IVI) and Gen AI exposure scores."""

from __future__ import annotations

import datetime as dt
import io
import re

import pandas as pd

from ingest.common import (
    SourceFormatError,
    finalise,
    find_header_row,
    find_links,
    month_end,
    require_columns,
    utcnow,
    vintage_id,
)

IVI_LANDING = "https://www.jobsandskills.gov.au/data/internet-vacancy-index"
IVI4_SHEET = "4 digit 3 month average"
IVI4_ID_COLUMNS = ["ANZSCO_CODE", "ANZSCO_TITLE", "state"]
IVI_SUPPRESSED = "."
# JSA does not state the version inside the IVI file. Titles match ANZSCO v1.2 wording
# (e.g. 1311 "Advertising and Sales Managers"); 4-digit codes align with v1.3 except 6399.
IVI_CLASSIFICATION = "ANZSCO v1.2 (inferred from titles)"

EXPOSURE_LANDING = "https://www.jobsandskills.gov.au/studies/generative-artificial-intelligence-capacity-study"
EXPOSURE_SHEET = "Occupation"
EXPOSURE_CLASSIFICATION = "ANZSCO v1.3"
EXPOSURE_MEASURES = {
    "Augmentation exposure score": "jsa_genai_augmentation",
    "Automation exposure score": "jsa_genai_automation",
}


def latest_ivi4_url(html: str) -> str:
    links = find_links(html, IVI_LANDING, r"internet_vacancies_anzsco4_occupations_states_and_territories.*\.xlsx")
    if len(links) != 1:
        raise SourceFormatError(f"JSA IVI: expected one ANZSCO4 states file link, found {len(links)}")
    return links[0][0]


def latest_exposure_url(html: str) -> str:
    links = find_links(html, EXPOSURE_LANDING, r"gen_ai_interactive_table_data_pack.*\.xlsx")
    if len(links) != 1:
        raise SourceFormatError(f"JSA exposure: expected one data pack link, found {len(links)}")
    return links[0][0]


def parse_ivi4(content: bytes) -> pd.DataFrame:
    """Long frame: code, title, state, month (month start), raw value (str/float)."""
    raw = pd.read_excel(io.BytesIO(content), sheet_name=IVI4_SHEET, header=None, dtype=object)
    h = find_header_row(raw, IVI4_ID_COLUMNS)
    header = raw.iloc[h].tolist()
    df = raw.iloc[h + 1 :].copy()
    df.columns = [c.strip() if isinstance(c, str) else c for c in header]
    require_columns(df, IVI4_ID_COLUMNS, "JSA IVI")
    months = [c for c in df.columns if isinstance(c, (dt.datetime, pd.Timestamp))]
    if len(months) < 12:
        raise SourceFormatError(f"JSA IVI: only {len(months)} month columns found")
    df = df.dropna(subset=["ANZSCO_TITLE"])
    df["ANZSCO_CODE"] = df["ANZSCO_CODE"].map(lambda c: str(c).strip().split(".")[0] if str(c).strip() != "." else ".")
    long = df.melt(id_vars=IVI4_ID_COLUMNS, value_vars=months, var_name="month", value_name="raw")
    long = long.rename(columns={"ANZSCO_CODE": "code", "ANZSCO_TITLE": "title"})
    long["month"] = pd.to_datetime(long["month"])
    return long


def ivi_series_id(code: str, state: str) -> str:
    occ = "total" if code == "0" else f"anzsco4_{code}"
    return f"jsa.ivi.ads_3mma.{occ}.{state.lower()}.orig"


def ivi_to_observations(content: bytes, codes: list[str], state: str = "AUST", retrieved_at=None) -> pd.DataFrame:
    """Observations for the given ANZSCO 4-digit codes (original series, 3-month moving average).

    Coverage is explicit: a value labelled month M averages months M-2..M, so period_start is
    the first day of M-2 and period_end the last day of M.
    """
    long = parse_ivi4(content)
    long = long[long["state"] == state]
    absent = sorted(set(codes) - set(long["code"]))
    if absent:
        raise SourceFormatError(f"JSA IVI: codes not found for {state}: {absent}")
    sel = long[long["code"].isin(codes)].copy()
    if sel.duplicated(["code", "month"]).any():
        raise SourceFormatError("JSA IVI: duplicate code/month rows")
    suppressed = sel["raw"].astype("string").str.strip().eq(IVI_SUPPRESSED).fillna(False)
    value = pd.to_numeric(sel["raw"].where(~suppressed), errors="coerce")
    bad = value.isna() & ~suppressed & sel["raw"].notna()
    if bad.any():
        raise SourceFormatError(f"JSA IVI: non-numeric values {sel.loc[bad, 'raw'].unique()[:5].tolist()}")
    status = pd.Series("observed", index=sel.index)
    status[suppressed] = "suppressed"
    status[value.isna() & ~suppressed] = "missing"
    out = pd.DataFrame(
        {
            "series_id": [ivi_series_id(c, state) for c in sel["code"]],
            "period_start": sel["month"] - pd.DateOffset(months=2),
            "period_end": month_end(sel["month"]),
            "value": value,
            "observation_status": status,
            "source_released_at": pd.NaT,
            "retrieved_at": pd.Timestamp(retrieved_at or utcnow()),
            "vintage_id": vintage_id(content),
        }
    )
    return finalise(out)


def suppressed_unit_groups(content: bytes, state: str = "AUST") -> list[str]:
    """Titles of IVI rows published with no code and no data (whole series suppressed)."""
    long = parse_ivi4(content)
    rows = long[(long["state"] == state) & (long["code"] == IVI_SUPPRESSED)]
    return sorted(rows["title"].str.strip().unique())


def parse_exposure(content: bytes, score_version: str, published_at: str | None) -> pd.DataFrame:
    """exposure_scores table: one row per (occupation, measure)."""
    raw = pd.read_excel(io.BytesIO(content), sheet_name=EXPOSURE_SHEET, header=None, dtype=object)
    h = find_header_row(raw, ["ANZSCO unit code", "ANZSCO unit title", *EXPOSURE_MEASURES])
    df = raw.iloc[h + 1 :].copy()
    df.columns = [str(c).strip() for c in raw.iloc[h]]
    df = df[pd.to_numeric(df["ANZSCO unit code"], errors="coerce").notna()]
    df["occupation_code"] = df["ANZSCO unit code"].astype(int).astype(str)
    if not df["occupation_code"].str.fullmatch(r"\d{4}").all():
        raise SourceFormatError("JSA exposure: occupation codes are not 4-digit unit groups")
    if df["occupation_code"].duplicated().any():
        raise SourceFormatError("JSA exposure: duplicate occupation codes")
    frames = []
    for col, measure in EXPOSURE_MEASURES.items():
        score = pd.to_numeric(df[col], errors="coerce")
        if not score.dropna().between(0, 1).all():
            raise SourceFormatError(f"JSA exposure: {col} outside 0-1")
        frames.append(
            pd.DataFrame(
                {
                    "occupation_code": df["occupation_code"],
                    "occupation_title": df["ANZSCO unit title"].str.strip(),
                    "classification_version": EXPOSURE_CLASSIFICATION,
                    "exposure_measure": measure,
                    "score_version": score_version,
                    "score": score,
                    "published_at": pd.Timestamp(published_at) if published_at else pd.NaT,
                }
            )
        )
    return pd.concat(frames, ignore_index=True)


def exposure_version_from_url(url: str) -> tuple[str, str | None]:
    m = re.search(r"(\d{8})", url)
    date = f"{m.group(1)[:4]}-{m.group(1)[4:6]}-{m.group(1)[6:]}" if m else None
    return (f"jsa_genai_capacity_{m.group(1)}" if m else "jsa_genai_capacity_unknown"), date
