"""Shared helpers: HTTP session, hashing, header detection and the observation schema."""

from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime
from urllib.parse import urljoin

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Keep this plain: JSA's WAF resets connections for UAs containing a URL.
USER_AGENT = "Mozilla/5.0 (compatible; insurancedash/0.1)"

OBSERVATION_COLUMNS = [
    "series_id",
    "period_start",
    "period_end",
    "value",
    "observation_status",
    "source_released_at",
    "retrieved_at",
    "vintage_id",
]
OBSERVATION_STATUSES = {"observed", "provisional", "suppressed", "missing", "unavailable"}


class SourceFormatError(ValueError):
    """Raised when a source file no longer has the layout or headers we expect."""


def session() -> requests.Session:
    s = requests.Session()
    retry = Retry(total=4, backoff_factor=1.5, status_forcelist=(429, 500, 502, 503, 504))
    s.mount("https://", HTTPAdapter(max_retries=retry))
    s.headers["User-Agent"] = USER_AGENT
    return s


def fetch(url: str, sess: requests.Session | None = None, timeout: tuple[int, int] = (15, 90)) -> bytes:
    resp = (sess or session()).get(url, timeout=timeout)
    resp.raise_for_status()
    return resp.content


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def vintage_id(data: bytes) -> str:
    """Short, stable identifier for the source file a set of observations came from."""
    return sha256(data)[:16]


def utcnow() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def find_links(html: str, base_url: str, pattern: str) -> list[tuple[str, str]]:
    """Return (absolute_url, link_text) for every <a> whose href matches `pattern` (regex)."""
    out = []
    for m in re.finditer(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', html, re.S | re.I):
        href, text = m.groups()
        if re.search(pattern, href, re.I):
            text = re.sub(r"<[^>]+>", " ", text)
            out.append((urljoin(base_url, href.replace("&amp;", "&")), " ".join(text.split())))
    return out


def find_header_row(raw: pd.DataFrame, required: list[str], max_scan: int = 50) -> int:
    """Locate the row in a header-less sheet that contains every `required` label."""
    want = {r.strip().lower() for r in required}
    for i in range(min(max_scan, len(raw))):
        cells = {str(v).strip().lower() for v in raw.iloc[i].tolist() if pd.notna(v)}
        if want <= cells:
            return i
    raise SourceFormatError(f"header row with {sorted(want)} not found in first {max_scan} rows")


def require_columns(df: pd.DataFrame, required: list[str], source: str) -> None:
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise SourceFormatError(f"{source}: expected columns missing: {missing}")


def month_end(ts: pd.Series) -> pd.Series:
    return (ts + pd.offsets.MonthEnd(0)).dt.normalize()


def quarter_start(ts: pd.Series) -> pd.Series:
    return ts.dt.to_period("Q").dt.start_time


def finalise(df: pd.DataFrame) -> pd.DataFrame:
    """Enforce the observation schema and its invariants before anything is written."""
    require_columns(df, OBSERVATION_COLUMNS, "observations")
    df = df[OBSERVATION_COLUMNS].copy()
    df["value"] = pd.to_numeric(df["value"], errors="raise").astype("float64")
    bad = set(df["observation_status"].unique()) - OBSERVATION_STATUSES
    if bad:
        raise ValueError(f"unknown observation_status values: {bad}")
    observed = df["observation_status"].isin({"observed", "provisional"})
    if df.loc[observed, "value"].isna().any():
        raise ValueError("observed rows must have a value")
    if df.loc[~observed, "value"].notna().any():
        raise ValueError("suppressed/missing/unavailable rows must have a null value, never 0")
    if df.duplicated(["series_id", "period_start", "vintage_id"]).any():
        raise ValueError("duplicate primary key (series_id, period_start, vintage_id)")
    return df.sort_values(["series_id", "period_start"]).reset_index(drop=True)
