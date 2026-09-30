"""Pipeline behaviour: staging, validation, revisions, status transitions. Offline (fake collectors)."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pandas as pd
import pytest
import requests

from ingest import run as runmod
from ingest.common import SourceFormatError, SourceResult, derive_ratios, finalise
from ingest.registry import RegistryError, load, validate

RETRIEVED = pd.Timestamp("2026-10-01T00:00:00Z")
TODAY = date(2026, 10, 1)


def series_entry(sid, source="src", **extra):
    return {
        "series_id": sid,
        "source": source,
        "title": sid,
        "source_key": {"k": sid},
        "dimensions": {},
        "unit": "x",
        "frequency": "monthly",
        "adjustment": "original",
        "definition": "d",
        "measure_basis": None,
        "transformation": None,
        "source_url": "u",
        "release_cadence": "c",
        "breaks": [],
        **extra,
    }


def make_registry(required=True, overdue_after_days=60, extra_series=()):
    return validate(
        {
            "sources": {
                "src": {
                    "name": "S",
                    "landing_url": "u",
                    "licence": "l",
                    "required": required,
                    "overdue_after_days": overdue_after_days,
                    "table": "observations",
                },
            },
            "series": [series_entry("a"), series_entry("b"), *extra_series],
        }
    )


def obs(values: dict[str, list], start="2026-01-01", vintage="v1", statuses=None):
    rows = []
    for sid, vals in values.items():
        for i, v in enumerate(vals):
            ps = pd.Timestamp(start) + pd.DateOffset(months=i)
            st = (statuses or {}).get((sid, i), "observed" if v is not None else "missing")
            rows.append(
                {
                    "series_id": sid,
                    "period_start": ps,
                    "period_end": ps + pd.offsets.MonthEnd(0),
                    "value": v,
                    "observation_status": st,
                    "source_released_at": pd.NaT,
                    "retrieved_at": RETRIEVED,
                    "vintage_id": vintage,
                }
            )
    return finalise(pd.DataFrame(rows))


@pytest.fixture
def env(tmp_path, monkeypatch):
    paths = runmod.Paths(tmp_path / "data")
    state = {"result": None, "exc": None}

    def fake(entries, sess):
        if state["exc"]:
            raise state["exc"]
        return state["result"]

    monkeypatch.setattr(runmod, "COLLECTORS", {"src": fake})

    def go(result=None, exc=None, reg=None, today=TODAY):
        state["result"], state["exc"] = result, exc
        return runmod.run(paths=paths, reg=reg or make_registry(), today=today)

    return paths, go


def files_snapshot(root: Path) -> dict[str, bytes]:
    return {str(p.relative_to(root)): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()}


# --- acceptance: pipeline --------------------------------------------------------------


def test_rerun_with_same_data_changes_nothing(env):
    paths, go = env
    go(SourceResult(obs({"a": [1.0, 2.0], "b": [3.0, 4.0]}), [("f.csv", b"x")]))
    before = files_snapshot(paths.root)
    # new retrieval time and new vintage id, identical content
    again = obs({"a": [1.0, 2.0], "b": [3.0, 4.0]}, vintage="v2")
    again["retrieved_at"] = pd.Timestamp("2026-10-02T00:00:00Z")
    go(SourceResult(again, [("f.csv", b"x")]))
    assert files_snapshot(paths.root) == before


def test_revision_to_older_period_detected_with_same_latest(env):
    paths, go = env
    go(SourceResult(obs({"a": [1.0, 2.0, 3.0], "b": [1.0, 1.0, 1.0]})))
    out = go(SourceResult(obs({"a": [1.5, 2.0, 3.0], "b": [1.0, 1.0, 1.0]}, vintage="v2")))
    cur = pd.read_parquet(paths.observations / "src.parquet")
    hist = pd.read_parquet(paths.history / "src.parquet")
    assert cur.loc[cur["series_id"] == "a", "value"].tolist() == [1.5, 2.0, 3.0]
    assert set(cur.loc[cur["series_id"] == "a", "vintage_id"]) == {"v2"}
    assert set(cur.loc[cur["series_id"] == "b", "vintage_id"]) == {"v1"}  # untouched series keeps vintage
    # only the revised period goes to history, not the whole series
    assert hist[["series_id", "value", "vintage_id"]].values.tolist() == [["a", 1.0, "v1"]]
    assert out["sources"]["src"]["latest_period"] == "2026-03-31"


def test_status_to_missing_is_a_revision(env):
    paths, go = env
    go(SourceResult(obs({"a": [1.0, 2.0], "b": [1.0, 1.0]})))
    go(SourceResult(obs({"a": [None, 2.0], "b": [1.0, 1.0]}, statuses={("a", 0): "suppressed"}, vintage="v2")))
    hist = pd.read_parquet(paths.history / "src.parquet")
    assert len(hist) == 1 and hist["observation_status"].iloc[0] == "observed"


def test_fetch_failure_keeps_data_and_sets_status(env):
    paths, go = env
    go(SourceResult(obs({"a": [1.0], "b": [2.0]})))
    before = (paths.observations / "src.parquet").read_bytes()
    out = go(exc=requests.ConnectionError("down"))
    assert out["sources"]["src"]["status"] == "fetch_failed"
    assert (paths.observations / "src.parquet").read_bytes() == before


def test_malformed_source_keeps_data_and_sets_status(env):
    paths, go = env
    go(SourceResult(obs({"a": [1.0], "b": [2.0]})))
    before = (paths.observations / "src.parquet").read_bytes()
    out = go(exc=SourceFormatError("header 'Value' not found"))
    assert out["sources"]["src"]["status"] == "validation_failed"
    assert "Value" in out["sources"]["src"]["message"]
    assert (paths.observations / "src.parquet").read_bytes() == before


def test_unexpected_crash_is_isolated(env):
    _, go = env
    out = go(exc=ZeroDivisionError("boom"))
    assert out["sources"]["src"]["status"] == "validation_failed"


def test_missing_registered_series_fails_validation(env):
    paths, go = env
    out = go(SourceResult(obs({"a": [1.0]})))
    assert out["sources"]["src"]["status"] == "validation_failed"
    assert "b" in out["sources"]["src"]["message"]
    assert not (paths.observations / "src.parquet").exists()


def test_unregistered_series_fails_validation(env):
    _, go = env
    out = go(SourceResult(obs({"a": [1.0], "b": [1.0], "zzz": [1.0]})))
    assert out["sources"]["src"]["status"] == "validation_failed"
    assert "zzz" in out["sources"]["src"]["message"]


def test_all_missing_series_fails_validation(env):
    _, go = env
    out = go(SourceResult(obs({"a": [None, None], "b": [1.0, 1.0]})))
    assert out["sources"]["src"]["status"] == "validation_failed"


def test_truncated_download_rejected(env):
    paths, go = env
    go(SourceResult(obs({"a": [1.0] * 10, "b": [1.0] * 10})))
    out = go(SourceResult(obs({"a": [1.0] * 3, "b": [1.0] * 10}, vintage="v2")))
    assert out["sources"]["src"]["status"] == "validation_failed"
    assert len(pd.read_parquet(paths.observations / "src.parquet")) == 20


def test_valid_from_blocks_pre_break_periods(env):
    _, go = env
    reg = validate(
        {
            "sources": {
                "src": {
                    "name": "S",
                    "landing_url": "u",
                    "licence": "l",
                    "required": True,
                    "overdue_after_days": None,
                    "table": "observations",
                }
            },
            "series": [series_entry("a", valid_from="2026-02-01"), series_entry("b")],
        }
    )
    out = go(SourceResult(obs({"a": [1.0, 2.0], "b": [1.0, 1.0]})), reg=reg)
    assert out["sources"]["src"]["status"] == "validation_failed"
    assert "valid_from" in out["sources"]["src"]["message"]


# --- status ----------------------------------------------------------------------------


def test_status_since_changes_only_on_transition(env, monkeypatch):
    paths, go = env
    go(SourceResult(obs({"a": [1.0], "b": [2.0]})))
    s1 = json.loads(paths.status.read_text())["sources"]["src"]
    go(exc=requests.ConnectionError("down"))
    monkeypatch.setattr(runmod, "utcnow", lambda: pd.Timestamp("2026-12-25T00:00:00Z").to_pydatetime())
    s3 = go(exc=requests.ConnectionError("still down, different text"))["sources"]["src"]
    assert s3["status"] == "fetch_failed"
    assert s3["since"] == s1["since"]  # no new transition on the second failure
    assert s3["message"] == "ConnectionError: down"  # message frozen at the transition


def test_overdue_when_no_new_data(env):
    _, go = env
    out = go(SourceResult(obs({"a": [1.0], "b": [2.0]})), today=date(2026, 6, 1))
    assert out["sources"]["src"]["status"] == "overdue"  # Jan 2026 data, 60-day threshold


def test_blocking_only_for_required_invalid_sources(env):
    _, go = env
    out = go(exc=SourceFormatError("bad"))
    assert runmod.blocking_sources(out, make_registry(required=True)) == ["src"]
    assert runmod.blocking_sources(out, make_registry(required=False)) == []


def test_fetch_failure_with_existing_data_does_not_block(env):
    _, go = env
    go(SourceResult(obs({"a": [1.0], "b": [2.0]})))
    out = go(exc=requests.ConnectionError("down"))
    assert runmod.blocking_sources(out, make_registry()) == []


# --- derived ratios --------------------------------------------------------------------


def test_derived_ratio_unavailable_when_input_suppressed():
    base = obs({"claims": [-80.0, None], "rev": [100.0, 100.0]}, statuses={("claims", 1): "suppressed"})
    entry = series_entry(
        "ratio",
        source_key=None,
        transformation={"type": "ratio", "numerator": "claims", "denominator": "rev", "scale": -100},
    )
    d = derive_ratios(base, [entry])
    assert d["value"].iloc[0] == pytest.approx(80.0)
    assert d["observation_status"].iloc[1] == "unavailable" and pd.isna(d["value"].iloc[1])


# --- registry --------------------------------------------------------------------------


def test_real_registry_is_valid_and_unique():
    reg = load()
    ids = [s["series_id"] for s in reg.series]
    assert len(ids) == len(set(ids))


def test_registry_rejects_duplicates():
    with pytest.raises(RegistryError, match="duplicate"):
        make_registry(extra_series=[series_entry("a")])


def test_registry_rejects_dangling_ratio():
    bad = series_entry("r", source_key=None, transformation={"type": "ratio", "numerator": "a", "denominator": "nope"})
    with pytest.raises(RegistryError, match="nope"):
        make_registry(extra_series=[bad])


def test_real_registry_apra_series_are_current_basis_only():
    for s in load().series:
        if s["source"] == "apra":
            assert s["valid_from"] == "2023-07-01" and s["series_id"].endswith(".aasb17")


def test_real_registry_ivi_series_are_original_not_seasonally_adjusted():
    for s in load().series:
        if s["source"] == "jsa_ivi":
            assert s["adjustment"] == "original"
