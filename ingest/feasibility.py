"""Milestone 0: fetch one series from each source live and test the IVI <-> exposure join.

Run: uv run python -m ingest.feasibility
"""

from __future__ import annotations

import pandas as pd

from ingest import apra, jsa, rba
from ingest.common import fetch, session

# Insurance-relevant ANZSCO unit groups present in both IVI and the JSA exposure data.
WATCH_CODES = ["1492", "2221", "2241", "5411", "5523", "5996", "6112"]


def summarise(name: str, obs: pd.DataFrame) -> None:
    for sid, g in obs.groupby("series_id"):
        obs_rows = g[g["observation_status"] == "observed"]
        last = obs_rows.iloc[-1]
        counts = g["observation_status"].value_counts().to_dict()
        print(
            f"  {sid}: {g['period_end'].min():%Y-%m-%d}..{g['period_end'].max():%Y-%m-%d} "
            f"n={len(g)} statuses={counts} latest={last['value']:,.2f} @ {last['period_end']:%Y-%m-%d}"
        )


def main() -> None:
    s = session()

    print("RBA F1")
    f1 = fetch(rba.table_url("f1"), s)
    summarise("rba", rba.to_observations(f1, {"FIRMMCRTD": "rba.f1.cash_rate_target.aus.orig"}))

    print("APRA QGIPS (current basis)")
    apra_url = apra.latest_database_url(fetch(apra.LANDING, s).decode("utf-8", "replace"))
    print(f"  file: {apra_url}")
    apra_obs = apra.to_observations(
        fetch(apra_url, s),
        {
            "apra.qgips.insurance_revenue.householders.direct.aasb17": {
                "Data item": "Insurance revenue, by class of business",
                "Category": "Insurance revenue",
                "Subject": "Class of business performance",
                "Stock or flow": "Flow",
                "Class of business": "Householders",
                "Class of business category": "Short-tail property",
                "Class of business group": "Direct insurance",
            }
        },
    )
    summarise("apra", apra_obs)

    print("JSA IVI (ANZSCO4, 3mma, original)")
    ivi_url = jsa.latest_ivi4_url(fetch(jsa.IVI_LANDING, s).decode("utf-8", "replace"))
    print(f"  file: {ivi_url}")
    ivi_bytes = fetch(ivi_url, s)
    summarise("ivi", jsa.ivi_to_observations(ivi_bytes, ["5996"]))
    print(f"  wholly suppressed unit groups (no code published): {jsa.suppressed_unit_groups(ivi_bytes)}")

    print("JSA Gen AI exposure")
    ex_url = jsa.latest_exposure_url(fetch(jsa.EXPOSURE_LANDING, s).decode("utf-8", "replace"))
    version, published = jsa.exposure_version_from_url(ex_url)
    print(f"  file: {ex_url} ({version})")
    ex = jsa.parse_exposure(fetch(ex_url, s), version, published)
    print(f"  {ex['occupation_code'].nunique()} unit groups, measures={sorted(ex['exposure_measure'].unique())}")

    print("Join: IVI (AUST, latest month) -> exposure")
    long = jsa.parse_ivi4(ivi_bytes)
    aust = long[(long["state"] == "AUST") & (long["code"] != "0")]
    latest = aust["month"].max()
    cur = aust[aust["month"] == latest].copy()
    cur["ads"] = pd.to_numeric(cur["raw"], errors="coerce")
    ivi_codes = set(cur.loc[cur["code"] != ".", "code"])
    ex_codes = set(ex["occupation_code"])
    joined = cur["code"].isin(ex_codes)
    print(f"  month={latest:%Y-%m} IVI unit groups with codes={len(ivi_codes)} exposure unit groups={len(ex_codes)}")
    print(
        f"  matched={len(ivi_codes & ex_codes)} IVI-only={sorted(ivi_codes - ex_codes)} "
        f"exposure-only={sorted(ex_codes - ivi_codes)}"
    )
    share = cur.loc[joined, "ads"].sum() / cur["ads"].sum()
    print(f"  share of occupation-coded ads with an exposure score: {share:.2%}")
    total_row = long[(long["state"] == "AUST") & (long["code"] == "0") & (long["month"] == latest)]
    total = pd.to_numeric(total_row["raw"]).iloc[0]
    print(f"  note: sum of occupation 3mma = {cur['ads'].sum():,.0f} vs published 'Australia Total' row = {total:,.0f}")

    titles = ex.drop_duplicates("occupation_code").set_index("occupation_code")["occupation_title"]
    wide = ex.pivot(index="occupation_code", columns="exposure_measure", values="score")
    print("  watchlist:")
    for c in WATCH_CODES:
        ads = cur.loc[cur["code"] == c, "ads"]
        print(
            f"    {c} {titles[c]}: aug={wide.loc[c, 'jsa_genai_augmentation']:.2f} "
            f"auto={wide.loc[c, 'jsa_genai_automation']:.2f} ads_3mma={ads.iloc[0]:,.0f}"
        )


if __name__ == "__main__":
    main()
