from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from ingest import apra, jsa, rba
from ingest.common import SourceFormatError, finalise

FIX = Path(__file__).parent / "fixtures"
RETRIEVED = pd.Timestamp("2026-10-01T00:00:00Z")


def read(name: str) -> bytes:
    return (FIX / name).read_bytes()


# --- RBA -------------------------------------------------------------------------------


def test_rba_parses_metadata_and_values():
    md, values = rba.parse_table(read("rba_f1_small.csv"))
    assert md.loc["FIRMMCRTD", "Units"] == "Per cent"
    assert md.loc["FIRMMCTRI", "Title"] == "Total Return Index"
    assert values["date"].min() == pd.Timestamp("2011-01-04")


def test_rba_blank_latest_is_missing_not_zero():
    obs = rba.to_observations(read("rba_f1_small.csv"), {"FIRMMCRTD": "rba.cash"}, RETRIEVED)
    last = obs.iloc[-1]
    assert last["period_end"] == pd.Timestamp("2026-09-30")
    assert last["observation_status"] == "missing"
    assert pd.isna(last["value"])
    assert (obs.loc[obs["observation_status"] == "observed", "value"] > 0).all()


def test_rba_genuine_zero_stays_observed():
    obs = rba.to_observations(read("rba_f1_small.csv"), {"FIRMMCRID": "rba.interbank"}, RETRIEVED)
    row = obs[obs["period_end"] == pd.Timestamp("2011-01-06")].iloc[0]
    assert row["observation_status"] == "observed" and row["value"] == 0.0


def test_rba_sparse_series_starts_at_first_observation():
    obs = rba.to_observations(read("rba_f1_small.csv"), {"FIRMMCCRT": "rba.change"}, RETRIEVED)
    assert obs["period_end"].min() == pd.Timestamp("2011-01-06")


def test_rba_release_date_from_metadata():
    obs = rba.to_observations(read("rba_f1_small.csv"), {"FIRMMCRTD": "rba.cash"}, RETRIEVED)
    assert (obs["source_released_at"] == pd.Timestamp("2026-09-30")).all()


def test_rba_unknown_series_fails_clearly():
    with pytest.raises(SourceFormatError, match="NOPE"):
        rba.to_observations(read("rba_f1_small.csv"), {"NOPE": "x"}, RETRIEVED)


def test_rba_missing_series_id_header_fails():
    broken = read("rba_f1_small.csv").replace(b"Series ID", b"Series Code")
    with pytest.raises(SourceFormatError, match="Series ID"):
        rba.parse_table(broken)


def test_rba_vintage_changes_when_history_revised():
    orig = read("rba_f1_small.csv")
    revised = orig.replace(b"05-Jan-2011,4.75", b"05-Jan-2011,4.50")
    a = rba.to_observations(orig, {"FIRMMCRTD": "rba.cash"}, RETRIEVED)
    b = rba.to_observations(revised, {"FIRMMCRTD": "rba.cash"}, RETRIEVED)
    assert a["vintage_id"].iloc[0] != b["vintage_id"].iloc[0]
    assert a["period_end"].max() == b["period_end"].max()


# --- APRA ------------------------------------------------------------------------------

HOUSEHOLDERS = {
    "apra.rev.householders": {
        "Data item": "Insurance revenue, by class of business",
        "Category": "Insurance revenue",
        "Subject": "Class of business performance",
        "Stock or flow": "Flow",
        "Class of business": "Householders",
        "Class of business category": "Short-tail property",
        "Class of business group": "Direct insurance",
    }
}


def test_apra_header_found_by_name_and_suppressed_is_null():
    obs = apra.to_observations(read("apra_database_small.xlsx"), HOUSEHOLDERS, RETRIEVED)
    assert list(obs["observation_status"]) == ["observed", "observed", "suppressed"]
    assert pd.isna(obs["value"].iloc[-1])
    assert obs["value"].iloc[0] == 3568000000


def test_apra_quarter_coverage():
    obs = apra.to_observations(read("apra_database_small.xlsx"), HOUSEHOLDERS, RETRIEVED)
    assert obs["period_start"].iloc[1] == pd.Timestamp("2024-01-01")
    assert obs["period_end"].iloc[1] == pd.Timestamp("2024-03-31")


def test_apra_unspecified_dimensions_must_be_blank():
    # The NSW row shares Data item prefix/class but has a State; the national selection
    # must not match it, and a selection naming the state must match only it.
    df = apra.parse_database(read("apra_database_small.xlsx"))
    nsw = apra.select(
        df,
        {
            **HOUSEHOLDERS["apra.rev.householders"],
            "Data item": "Insurance revenue, by class of business and state/territory",
            "State and territory": "New South Wales",
        },
    )
    assert len(nsw) == 1


def test_apra_renamed_header_fails_clearly(tmp_path):
    from openpyxl import load_workbook

    wb = load_workbook(FIX / "apra_database_small.xlsx")
    wb["Database"]["N2"] = "Amount"
    p = tmp_path / "broken.xlsx"
    wb.save(p)
    with pytest.raises(SourceFormatError):
        apra.parse_database(p.read_bytes())


def test_apra_picks_current_basis_link_only():
    html = """
    <a href="/system/files/2026-08/db.xlsx">Quarterly general insurance performance statistics database September 2023 to June 2026</a>
    <a href="/system/files/2025-06/hist.xlsx">Quarterly general insurance performance statistics database (historical data) December 2002 to June 2023</a>
    <a href="/system/files/2025-06/inst.xlsx">Quarterly general insurance institution-level statistics database (historical data)</a>
    """
    assert apra.latest_database_url(html) == "https://www.apra.gov.au/system/files/2026-08/db.xlsx"


def test_apra_no_current_link_fails():
    with pytest.raises(SourceFormatError):
        apra.latest_database_url('<a href="/x.xlsx">database (historical data)</a>')


# --- JSA IVI ---------------------------------------------------------------------------


def test_ivi_codes_kept_as_strings_and_dot_is_suppressed():
    obs = jsa.ivi_to_observations(read("ivi_anzsco4_small.xlsx"), ["5996"], retrieved_at=RETRIEVED)
    assert set(obs["series_id"]) == {"jsa.ivi.ads_3mma.anzsco4_5996.aust.orig"}
    last = obs.iloc[-1]
    assert last["observation_status"] == "suppressed" and pd.isna(last["value"])
    assert (obs["observation_status"] == "observed").sum() == 13


def test_ivi_three_month_coverage():
    obs = jsa.ivi_to_observations(read("ivi_anzsco4_small.xlsx"), ["6112"], retrieved_at=RETRIEVED)
    first = obs.iloc[0]
    assert first["period_start"] == pd.Timestamp("2024-11-01")
    assert first["period_end"] == pd.Timestamp("2025-01-31")


def test_ivi_state_filter():
    obs = jsa.ivi_to_observations(read("ivi_anzsco4_small.xlsx"), ["5996"], state="NSW", retrieved_at=RETRIEVED)
    assert set(obs["series_id"]) == {"jsa.ivi.ads_3mma.anzsco4_5996.nsw.orig"}
    assert (obs["value"] == 200.0).all()


def test_ivi_total_series_id():
    obs = jsa.ivi_to_observations(read("ivi_anzsco4_small.xlsx"), ["0"], retrieved_at=RETRIEVED)
    assert set(obs["series_id"]) == {"jsa.ivi.ads_3mma.total.aust.orig"}


def test_ivi_unknown_code_fails():
    with pytest.raises(SourceFormatError, match="9999"):
        jsa.ivi_to_observations(read("ivi_anzsco4_small.xlsx"), ["9999"], retrieved_at=RETRIEVED)


def test_ivi_wholly_suppressed_groups():
    assert jsa.suppressed_unit_groups(read("ivi_anzsco4_small.xlsx")) == ["Legislators"]


def test_ivi_link_scrape():
    html = (
        '<a href="/sites/default/files/2026-09/internet_vacancies_anzsco4_occupations_states_and_territories_'
        '-_august_2026.xlsx">x</a><a href="/sites/default/files/2026-09/internet_vacancies_anzsco2_occupations'
        '_states_and_territories_-_august_2026.xlsx">y</a>'
    )
    assert jsa.latest_ivi4_url(html).endswith("anzsco4_occupations_states_and_territories_-_august_2026.xlsx")


# --- JSA exposure ----------------------------------------------------------------------


def test_exposure_parse():
    ex = jsa.parse_exposure(read("jsa_exposure_small.xlsx"), "jsa_genai_capacity_20250903", "2025-09-03")
    assert len(ex) == 6  # 3 occupations x 2 measures
    assert set(ex["classification_version"]) == {"ANZSCO v1.3"}
    agents = ex[(ex["occupation_code"] == "6112") & (ex["exposure_measure"] == "jsa_genai_automation")]
    assert agents["score"].iloc[0] == pytest.approx(0.62)


def test_exposure_version_from_url():
    v, d = jsa.exposure_version_from_url("/files/2025-09/jsa_gen_ai_interactive_table_data_pack_20250903.xlsx")
    assert (v, d) == ("jsa_genai_capacity_20250903", "2025-09-03")


# --- observation schema invariants -----------------------------------------------------


def _obs(**over):
    row = {
        "series_id": "s",
        "period_start": pd.Timestamp("2025-01-01"),
        "period_end": pd.Timestamp("2025-01-31"),
        "value": 1.0,
        "observation_status": "observed",
        "source_released_at": pd.NaT,
        "retrieved_at": RETRIEVED,
        "vintage_id": "v",
    }
    row.update(over)
    return pd.DataFrame([row])


def test_finalise_rejects_zero_for_missing():
    with pytest.raises(ValueError, match="never 0"):
        finalise(_obs(value=0.0, observation_status="suppressed"))


def test_finalise_rejects_observed_without_value():
    with pytest.raises(ValueError, match="must have a value"):
        finalise(_obs(value=None))


def test_finalise_rejects_duplicate_key():
    with pytest.raises(ValueError, match="duplicate"):
        finalise(pd.concat([_obs(), _obs(value=2.0)]))


def test_finalise_rejects_unknown_status():
    with pytest.raises(ValueError, match="unknown"):
        finalise(_obs(observation_status="estimated"))
