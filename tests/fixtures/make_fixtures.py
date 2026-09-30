"""Regenerate the small parser fixtures. Layouts mirror the live files as of 2026-09.

Run: uv run python tests/fixtures/make_fixtures.py
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from openpyxl import Workbook

HERE = Path(__file__).parent

RBA_F1 = """﻿F1 INTEREST RATES AND YIELDS – MONEY MARKET
Title,Cash Rate Target,Change in the Cash Rate Target,Interbank Overnight Cash Rate,Total Return Index
Description,Cash Rate Target on date,Change in the Cash Rate Target (in percentage points),Interbank Overnight Cash Rate on date,Total Return Index
Frequency,Daily,as announced,Daily,Daily
Type,Original,Original,Original,Original
Units,Per cent,Per cent,Per cent,Index 04-Jan-2011=100


Source,RBA,RBA,RBA,RBA
Publication date,30-Sep-2026,30-Sep-2026,30-Sep-2026,30-Sep-2026
Series ID,FIRMMCRTD,FIRMMCCRT,FIRMMCRID,FIRMMCTRI
04-Jan-2011,4.75,,4.75,100.000000
05-Jan-2011,4.75,,4.75,100.013014
06-Jan-2011,4.75,-0.25,0.00,100.026029
29-Sep-2026,4.35,,4.35,146.595205
30-Sep-2026,,,,146.612676
"""


def apra(path: Path) -> None:
    wb = Workbook()
    wb.active.title = "Cover"
    ws = wb.create_sheet("Database")
    ws.append([])  # a blank row above the header, to prove header detection is by name
    ws.append(
        [
            "Reporting Period",
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
            "Value",
        ]
    )
    rev = ("Insurance revenue, by class of business", "Insurance revenue", "Class of business performance", "Flow")
    cob = ("Householders", "Short-tail property", "Direct insurance")
    for d, v in [
        (dt.datetime(2023, 12, 31), 3568000000),
        (dt.datetime(2024, 3, 31), 3657000000),
        (dt.datetime(2024, 6, 30), "*"),
    ]:
        ws.append([d, *rev, None, None, *cob, None, None, None, v])
    # state breakdown of the same item: must not be picked up by a national selection
    ws.append(
        [
            dt.datetime(2024, 3, 31),
            "Insurance revenue, by class of business and state/territory",
            "Insurance revenue",
            "Class of business performance",
            "Flow",
            None,
            None,
            *cob,
            None,
            "New South Wales",
            None,
            1265000000,
        ]
    )
    ws.append(
        [
            dt.datetime(2024, 3, 31),
            "Other income items",
            "Insurance financial result",
            "Financial performance",
            "Flow",
            "Total industry",
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            "*",
        ]
    )
    wb.save(path)


def ivi(path: Path) -> None:
    wb = Workbook()
    wb.active.title = "Notes"
    wb.active.append(["Four digit data is presented in three month moving average terms"])
    ws = wb.create_sheet("4 digit 3 month average")
    months = [dt.datetime(2025, m, 1) for m in range(1, 13)] + [dt.datetime(2026, 1, 1), dt.datetime(2026, 2, 1)]
    ws.append(["ANZSCO_CODE", "ANZSCO_TITLE", "state", *months])
    ws.append(["0", "Australia Total", "AUST", *[200000 + i for i in range(14)]])
    ws.append(
        [
            "5996",
            "Insurance Investigators, Loss Adjusters and Risk Surveyors",
            "AUST",
            *[600 + i / 3 for i in range(13)],
            ".",
        ]
    )
    ws.append(["6112", "Insurance Agents", "AUST", *[500.0] * 14])
    ws.append([".", "Legislators", "AUST", *["."] * 14])
    ws.append(["5996", "Insurance Investigators, Loss Adjusters and Risk Surveyors", "NSW", *[200.0] * 14])
    wb.save(path)


def exposure(path: Path) -> None:
    wb = Workbook()
    wb.active.title = "Contents"
    ws = wb.create_sheet("Occupation")
    for _ in range(4):
        ws.append([])
    ws.append(["Table 1 - Occupation (ANZSCO v1.3 Unit level) data on AI exposures"])
    ws.append([])
    ws.append(
        [
            "ANZSCO unit code",
            "ANZSCO unit title",
            "Occupation matrix group",
            "Augmentation exposure score",
            "Augmentation standard deviation",
            "Automation exposure score",
            "Automation standard deviation",
        ]
    )
    ws.append([1113, "Legislators", "Legal and Insurance", 0.63, 0.1, 0.26, 0.05])
    ws.append(
        [
            5996,
            "Insurance Investigators, Loss Adjusters and Risk Surveyors",
            "Legal and Insurance",
            0.73,
            0.1,
            0.44,
            0.1,
        ]
    )
    ws.append([6112, "Insurance Agents", "Legal and Insurance", 0.73, 0.1, 0.62, 0.1])
    ws.append(["Source: JSA"])
    wb.save(path)


if __name__ == "__main__":
    (HERE / "rba_f1_small.csv").write_text(RBA_F1, encoding="utf-8")
    apra(HERE / "apra_database_small.xlsx")
    ivi(HERE / "ivi_anzsco4_small.xlsx")
    exposure(HERE / "jsa_exposure_small.xlsx")
    print("fixtures written to", HERE)
