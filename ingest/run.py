"""Orchestrate all sources: fetch -> stage -> validate -> promote, and record status.

Run: uv run python -m ingest.run [--only SOURCE ...]

Guarantees:
- Each source is isolated: an exception in one never stops the others.
- A source's good data is replaced only after its staged output validates.
- Unchanged series are left byte-for-byte untouched, so a rerun with no new data produces no diff.
- status.json changes only on a status transition or a data change (no last_checked timestamps).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import shutil
import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd
import requests

from ingest import apra, jsa, rba
from ingest.common import SourceFormatError, SourceResult, session, utcnow, vintage_id
from ingest.registry import Registry, load

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

log = logging.getLogger("ingest")

COLLECTORS: dict[str, Callable[[list[dict], requests.Session], SourceResult]] = {
    "rba": rba.collect,
    "apra": apra.collect,
    "jsa_ivi": jsa.collect_ivi,
    "jsa_exposure": jsa.collect_exposure,
}

# Content columns: what counts as a data change. retrieved_at / vintage_id / release date are provenance.
OBS_CONTENT = ["series_id", "period_start", "period_end", "value", "observation_status"]
EXPOSURE_KEY = ["occupation_code", "classification_version", "exposure_measure", "score_version"]
EXPOSURE_CONTENT = [*EXPOSURE_KEY, "occupation_title", "score", "published_at"]
MAX_SHRINK = 0.8  # a series may not lose more than 20% of its periods in one release


class ValidationError(ValueError):
    pass


@dataclass
class Paths:
    root: Path

    @property
    def observations(self) -> Path:
        return self.root / "parquet" / "observations"

    @property
    def history(self) -> Path:
        return self.root / "parquet" / "observations_history"

    @property
    def exposure(self) -> Path:
        return self.root / "parquet" / "exposure_scores.parquet"

    @property
    def status(self) -> Path:
        return self.root / "status.json"

    @property
    def staging(self) -> Path:
        return self.root / "staging"

    @property
    def raw(self) -> Path:
        return self.root / "raw"


# --- hashing ---------------------------------------------------------------------------


def content_hash(df: pd.DataFrame, cols: list[str], sort: list[str]) -> str:
    if df.empty:
        return "empty"
    d = df[cols].sort_values(sort).reset_index(drop=True)
    return hashlib.sha256(pd.util.hash_pandas_object(d, index=False).values.tobytes()).hexdigest()


def series_hashes(obs: pd.DataFrame) -> dict[str, str]:
    return {sid: content_hash(g, OBS_CONTENT, ["period_start"]) for sid, g in obs.groupby("series_id", sort=True)}


# --- validation ------------------------------------------------------------------------


def validate_observations(staged: pd.DataFrame, source: str, reg: Registry, current: pd.DataFrame | None) -> None:
    expected = reg.ids_for_source(source)
    got = set(staged["series_id"])
    unregistered = got - expected
    if unregistered:
        raise ValidationError(f"unregistered series in output: {sorted(unregistered)}")
    absent = expected - got
    if absent:
        raise ValidationError(f"registered series missing from output: {sorted(absent)}")
    observed = staged[staged["observation_status"] == "observed"].groupby("series_id").size()
    empty = sorted(expected - set(observed.index))
    if empty:
        raise ValidationError(f"series with no observed values: {empty}")
    if staged.loc[staged["observation_status"] != "observed", "value"].notna().any():
        raise ValidationError("non-observed rows carry values")
    for e in reg.for_source(source):
        if e.get("valid_from"):
            early = staged[(staged["series_id"] == e["series_id"]) & (staged["period_start"] < e["valid_from"])]
            if not early.empty:
                raise ValidationError(f"{e['series_id']}: periods before valid_from {e['valid_from']} (series break)")
    if current is None or current.empty:
        return
    for sid, old in current.groupby("series_id"):
        if sid not in got:
            continue
        new = staged[staged["series_id"] == sid]
        if len(new) < MAX_SHRINK * len(old):
            raise ValidationError(f"{sid}: shrank from {len(old)} to {len(new)} periods")
        if new["period_end"].max() < old["period_end"].max():
            raise ValidationError(f"{sid}: latest period went backwards")


def validate_exposure(staged: pd.DataFrame, current: pd.DataFrame | None) -> None:
    if staged.empty:
        raise ValidationError("no exposure scores")
    if staged.duplicated(["occupation_code", "exposure_measure", "score_version"]).any():
        raise ValidationError("duplicate exposure scores")
    if not staged["score"].dropna().between(0, 1).all():
        raise ValidationError("exposure scores outside 0-1")
    if current is not None and len(staged) < MAX_SHRINK * len(current):
        raise ValidationError(f"exposure table shrank from {len(current)} to {len(staged)} rows")


# --- promotion -------------------------------------------------------------------------


def superseded_rows(old: pd.DataFrame, new: pd.DataFrame) -> pd.DataFrame:
    """Old rows that the new vintage revises or removes (unchanged periods are not history)."""
    key = ["series_id", "period_start"]
    m = old.merge(new[[*key, "period_end", "value", "observation_status"]], on=key, how="left", suffixes=("", "_n"))
    removed = m["observation_status_n"].isna()
    same_value = (m["value"] == m["value_n"]) | (m["value"].isna() & m["value_n"].isna())
    changed = ~removed & (
        ~same_value | (m["observation_status"] != m["observation_status_n"]) | (m["period_end"] != m["period_end_n"])
    )
    return old[(removed | changed).values]


def write_parquet(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    df.to_parquet(tmp, index=False)
    tmp.replace(path)


def promote_observations(staged: pd.DataFrame, source: str, paths: Paths) -> bool:
    """Merge staged into current per series. Returns True if anything changed."""
    cur_path = paths.observations / f"{source}.parquet"
    current = pd.read_parquet(cur_path) if cur_path.exists() else staged.iloc[0:0]
    old_h, new_h = series_hashes(current), series_hashes(staged)
    changed = {sid for sid in new_h if old_h.get(sid) != new_h[sid]} | (set(old_h) - set(new_h))
    if not changed:
        return False
    keep = current[~current["series_id"].isin(changed)]
    fresh = staged[staged["series_id"].isin(changed)]
    merged = pd.concat([keep, fresh], ignore_index=True).sort_values(["series_id", "period_start"])
    history = superseded_rows(current[current["series_id"].isin(changed)], fresh)
    if not history.empty:
        hist_path = paths.history / f"{source}.parquet"
        prior = pd.read_parquet(hist_path) if hist_path.exists() else history.iloc[0:0]
        all_hist = pd.concat([prior, history], ignore_index=True)
        all_hist = all_hist.drop_duplicates(["series_id", "period_start", "vintage_id"])
        write_parquet(all_hist.sort_values(["series_id", "period_start", "retrieved_at"]), hist_path)
    write_parquet(merged.reset_index(drop=True), cur_path)
    log.info("%s: %d series changed, %d rows to history", source, len(changed), len(history))
    return True


def promote_exposure(staged: pd.DataFrame, paths: Paths) -> bool:
    current = pd.read_parquet(paths.exposure) if paths.exposure.exists() else None
    new_h = content_hash(staged, EXPOSURE_CONTENT, EXPOSURE_KEY)
    if current is not None and content_hash(current, EXPOSURE_CONTENT, EXPOSURE_KEY) == new_h:
        return False
    if current is not None:
        # keep earlier score versions: a new JSA release must not erase the one charts were frozen on
        staged = pd.concat([current[~current["score_version"].isin(staged["score_version"])], staged])
    write_parquet(staged.sort_values(EXPOSURE_KEY).reset_index(drop=True), paths.exposure)
    return True


def archive_raw(source: str, raw_files: list[tuple[str, bytes]], paths: Paths) -> list[str]:
    """Save raw files as data/raw/<source>/<vintage>__<name>; release assets are uploaded by CI."""
    out = []
    for name, content in raw_files:
        p = paths.raw / source / f"{vintage_id(content)}__{name}"
        p.parent.mkdir(parents=True, exist_ok=True)
        if not p.exists():
            p.write_bytes(content)
        out.append(str(p.relative_to(paths.root.parent) if paths.root.parent in p.parents else p))
    return out


# --- status ----------------------------------------------------------------------------


def latest_period(source: str, reg: Registry, paths: Paths) -> str | None:
    if reg.sources[source]["table"] == "exposure_scores":
        if not paths.exposure.exists():
            return None
        pub = pd.read_parquet(paths.exposure)["published_at"].max()
        return None if pd.isna(pub) else f"{pub:%Y-%m-%d}"
    p = paths.observations / f"{source}.parquet"
    if not p.exists():
        return None
    df = pd.read_parquet(p)
    df = df[df["observation_status"] == "observed"]
    # the source is as fresh as its stalest registered series
    return f"{df.groupby('series_id')['period_end'].max().min():%Y-%m-%d}"


def is_overdue(latest: str | None, overdue_after_days: int | None, today: date) -> bool:
    if latest is None or overdue_after_days is None:
        return False
    return (today - date.fromisoformat(latest)).days > overdue_after_days


def update_status(
    prev: dict[str, Any], source: str, status: str, message: str | None, data_changed: bool, latest: str | None
) -> dict[str, Any]:
    today = utcnow().date().isoformat()
    old = prev.get(source, {})
    rec = dict(old)
    if old.get("status") != status:
        rec["status"] = status
        rec["since"] = today
        rec["message"] = message
    if data_changed:
        rec["last_data_change"] = today
    rec["latest_period"] = latest
    rec.setdefault("last_data_change", None)
    return rec


# --- orchestration ---------------------------------------------------------------------


def run_source(source: str, reg: Registry, paths: Paths, sess: requests.Session) -> tuple[str, str | None, bool]:
    """Returns (status, message, data_changed)."""
    entries = reg.for_source(source)
    table = reg.sources[source]["table"]
    try:
        result = COLLECTORS[source](entries, sess)
    except requests.RequestException as e:
        return "fetch_failed", f"{type(e).__name__}: {str(e)[:300]}", False
    except (SourceFormatError, ValueError, KeyError) as e:
        return "validation_failed", f"{type(e).__name__}: {str(e)[:300]}", False

    stage = paths.staging / source
    shutil.rmtree(stage, ignore_errors=True)
    stage.mkdir(parents=True)
    write_parquet(result.table, stage / "table.parquet")
    staged = pd.read_parquet(stage / "table.parquet")
    try:
        if table == "observations":
            cur_path = paths.observations / f"{source}.parquet"
            current = pd.read_parquet(cur_path) if cur_path.exists() else None
            validate_observations(staged, source, reg, current)
            changed = promote_observations(staged, source, paths)
        else:
            current = pd.read_parquet(paths.exposure) if paths.exposure.exists() else None
            validate_exposure(staged, current)
            changed = promote_exposure(staged, paths)
    except ValidationError as e:
        return "validation_failed", str(e)[:300], False
    finally:
        shutil.rmtree(stage, ignore_errors=True)
    if changed:
        archive_raw(source, result.raw_files, paths)
    return "ok", None, changed


def run(
    only: list[str] | None = None, paths: Paths | None = None, reg: Registry | None = None, today: date | None = None
) -> dict[str, Any]:
    paths = paths or Paths(DATA)
    reg = reg or load()
    today = today or utcnow().date()
    prev = json.loads(paths.status.read_text()) if paths.status.exists() else {}
    prev_sources = prev.get("sources", {})
    new_sources = dict(prev_sources)
    sess = session()
    for source in reg.sources:
        if only and source not in only:
            continue
        log.info("checking %s at %s", source, utcnow().isoformat())  # last_checked -> logs only
        try:
            status, message, changed = run_source(source, reg, paths, sess)
        except Exception as e:  # isolation: one broken source never blocks the others
            log.exception("%s crashed", source)
            status, message, changed = "validation_failed", f"{type(e).__name__}: {str(e)[:300]}", False
        latest = latest_period(source, reg, paths)
        if status == "ok" and is_overdue(latest, reg.sources[source]["overdue_after_days"], today):
            status, message = "overdue", f"no new data since {latest}"
        new_sources[source] = update_status(prev_sources, source, status, message, changed, latest)
        log.info("%s: %s%s", source, status, f" ({message})" if message else "")
    out = {"sources": dict(sorted(new_sources.items()))}
    if out != prev:
        paths.status.parent.mkdir(parents=True, exist_ok=True)
        paths.status.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n")
    return out


def blocking_sources(status: dict[str, Any], reg: Registry) -> list[str]:
    """Required sources that are invalid or have never produced data. These block publication."""
    bad = []
    for name, src in reg.sources.items():
        if not src["required"]:
            continue
        rec = status.get("sources", {}).get(name, {})
        if rec.get("status") == "validation_failed" or rec.get("latest_period") is None:
            bad.append(name)
    return bad


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", nargs="*", help="run only these sources")
    ap.add_argument("--check-publishable", action="store_true", help="exit 2 if a required source blocks publishing")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    reg = load()
    if args.check_publishable:
        paths = Paths(DATA)
        status = json.loads(paths.status.read_text()) if paths.status.exists() else {}
        bad = blocking_sources(status, reg)
        if bad:
            log.error("publication blocked by required sources: %s", bad)
            return 2
        return 0
    run(args.only, reg=reg)
    return 0


if __name__ == "__main__":
    sys.exit(main())
