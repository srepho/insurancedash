# Milestone 0 — Source feasibility findings

Checked live on 2026-10-01. Reproduce with `uv run python -m ingest.feasibility`.

## Summary

| Source | Status | Series parsed | Coverage | Latest |
|---|---|---|---|---|
| RBA F1 | ✅ feasible | `FIRMMCRTD` cash rate target | 2011-01-04 → 2026-09-30 (daily) | 4.35% (29 Sep 2026); 30 Sep blank → stored as `missing` |
| APRA QGIPS (current basis) | ✅ feasible | Insurance revenue, Householders, direct | Dec 2023 → Jun 2026 (11 quarters) | $4.342bn (Jun Q 2026) |
| JSA IVI ANZSCO4 | ✅ feasible | 5996 Insurance Investigators, Loss Adjusters & Risk Surveyors, AUST | Mar 2006 → Aug 2026 (monthly, 3mma) | 631 ads (Aug 2026) |
| JSA Gen AI exposure | ✅ feasible | Augmentation + automation scores | 357 ANZSCO v1.3 unit groups | data pack dated 2025-09-03 |
| IVI ↔ exposure join | ✅ 99.9% of ads | 350 of 351 coded IVI unit groups match | — | — |

## RBA

- URL: `https://www.rba.gov.au/statistics/tables/csv/f1-data.csv` (pattern `{table}-data.csv`).
- UTF-8 **with BOM**; metadata rows `Title, Description, Frequency, Type, Units, Source, Publication date, Series ID`, with two blank lines between `Units` and `Source`. Parse by these labels, not row numbers.
- Rows are **ragged**: trailing empty cells are omitted, so pad to header width.
- The latest row can have blanks for series not yet published (30 Sep 2026 cash rate). These must be `missing`, not 0.
- `Publication date` row gives `source_released_at`.
- Sparse series (e.g. `FIRMMCCRT` change in cash rate) are mostly blank by design — only register series that are meant to be continuous, or treat sparse ones as event series.

## APRA

- Landing page: `https://www.apra.gov.au/quarterly-general-insurance-performance-statistics`. **The plan's implied URL (`/quarterly-general-insurance-statistics`) is a 404.**
- Files on the page (Aug 2026):
  - **Current basis**: `Quarterly general insurance performance statistics database September 2023 to June 2026.xlsx`
  - Historical: `... database (historical data) December 2002 to June 2023.xlsx` (+ a formatted version)
  - Institution-level: **only a historical file (Sep 2017 → Jun 2023)**. No current institution-level release → confirms hiatus. **Do not build insurer benchmarking.**
  - Specifications xlsx (maps each data item to its APRA Connect form/row — use this to fill the registry's gross/net, denominator and basis fields).
- The `Database` sheet is already **tidy long format**: `Reporting Period, Data item, Category, Subject, Stock or flow, Industry segment, Industry segment group, Class of business, Class of business category, Class of business group, Counterparty grade, State and territory, Stress scenario type, Value`. 29,455 rows.
- Suppressed values are `*` (6,708 rows) → `suppressed`, null value.
- Flow items are **discrete quarterly** values that APRA derives from year-to-date returns; "performance data … only available starting December 2023". Sep 2023 exists for stock items only.
- Class-of-business items have **blank Industry segment** (they are industry-wide). A selection must require every unnamed dimension to be blank, otherwise state breakdowns leak in — implemented in `apra.select`.
- 18 classes of business, including Householders, Domestic motor, Commercial motor, CTP, Fire and ISR, Cyber, etc.
- Available by class: Insurance revenue, Insurance service expense (incl. **Incurred claims**), Insurance service result, reinsurance items, **Gross written premium**, **Number of risks written**; incurred claims and revenue also by state.
- Note from APRA: GWP now **includes fire service levies** — a further reason not to splice against the old basis.
- Licence: CC BY 3.0 AU.

## JSA Internet Vacancy Index

- Landing page: `https://www.jobsandskills.gov.au/data/internet-vacancy-index` — scrape the `internet_vacancies_anzsco4_occupations_states_and_territories_-_<month>_<year>.xlsx` link.
- **WAF gotcha**: `www.jobsandskills.gov.au` resets the connection for a User-Agent containing a URL (`+https://…`). `Mozilla/5.0 (compatible; insurancedash/0.1)` works.
- The ANZSCO4 file has **one data sheet: `4 digit 3 month average`** — 3-month moving average of **original** counts. **There is no seasonally adjusted 4-digit series.** So the "never sum SA series" rule is automatically satisfied at 4-digit, but 3mma values must also not be summed and compared to the total:
  - sum of occupation 3mma (Aug 2026) = 213,541 vs published `Australia Total` row = 215,977.
- Wide layout: `ANZSCO_CODE, ANZSCO_TITLE, state` + one column per month (datetime headers). States: AUST + 8.
- `.` = suppressed. **7 unit groups are wholly suppressed and published with code `.`** (Legislators, Judicial and Other Legal Professionals, Defence groups, Other Hospitality Workers, Other Personal Service Workers). Must read codes as strings.
- **ANZSCO version not stated in the file.** Titles use ANZSCO v1.2 wording (e.g. 1311 "Advertising and Sales Managers", 2344 "Geologists and Geophysicists"); 4-digit codes otherwise align with v1.3. Recorded as `ANZSCO v1.2 (inferred from titles)` — worth confirming against the IVI methodology PDF.
- Release calendar is on the landing page (e.g. Sep 2026 data → 21 Oct 2026) — usable for "overdue" status.

## JSA Gen AI exposure

- Study page: `https://www.jobsandskills.gov.au/studies/generative-artificial-intelligence-capacity-study`. The occupation page's table is JS-rendered; the data is in `jsa_gen_ai_interactive_table_data_pack_20250903.xlsx`.
- Sheet `Occupation`, header on row 7 (found by name). **ANZSCO v1.3, unit group (4-digit) level**, 357 unit groups, no missing scores.
- Measures: **Augmentation exposure score** and **Automation exposure score** (0–1, task-average), each with a standard deviation. Also mobility, skill-change, hybridisation/specialisation, entry-level ad share.
- Missing values in non-score columns are `' - '`.
- The publication is 2025-09 → any use against pre-2025 data is a **retrospective classification** (label on charts).
- Also has an `Industry` sheet (ANZSIC division) with *job ads listing AI skills (%, Jan–May 2025)* and *worker profiles listing AI skills* — a one-off snapshot for concept 3 (employer demand for AI skills).

## IVI ↔ exposure join

- Both at 4-digit. 351 IVI unit groups carry codes; 357 exposure unit groups.
- Matched: **350**. IVI-only: **6399** Other Sales Support Workers (not in the exposure file). Exposure-only: the 7 IVI-suppressed groups.
- **99.91%** of occupation-coded ads (Aug 2026, 3mma) have an exposure score.
- 14 title differences are v1.2 vs v1.3 wording only → **join on code, never on title**.

### Insurance watchlist — what is measurable at 4-digit

| Code | Unit group | Aug-26 ads (3mma) | Augmentation | Automation |
|---|---|---|---|---|
| 1492 | Call/Contact Centre & Customer Service Managers | 581 | 0.71 | 0.53 |
| 2221 | Financial Brokers (incl. insurance brokers) | 227 | 0.75 | 0.47 |
| 2241 | Actuaries, Mathematicians & Statisticians | 135 | 0.77 | 0.58 |
| 5411 | Call or Contact Centre Workers | 1,397 | 0.73 | 0.75 |
| 5523 | Insurance, Money Market & Statistical Clerks | 39 | 0.74 | 0.68 |
| 5996 | Insurance Investigators, Loss Adjusters & Risk Surveyors | 631 | 0.73 | 0.44 |
| 6112 | Insurance Agents | 557 | 0.73 | 0.62 |

Granularity caveats for milestone 3:
- Actuaries share 2241 with mathematicians and statisticians; insurance brokers share 2221 with other financial brokers. The dashboard must say the series is the unit group, not the role.
- **Underwriters and claims officers have no dedicated unit group.** Their 6-digit ANZSCO codes (and therefore which 4-digit group carries them) have not been verified yet — look them up in the ABS ANZSCO browser before adding them. Not guessed here.

## ABS (checked early for milestone 2)

- Dataflows: **`CPI` v2.0.0 is now primary** (monthly and quarterly; latest 2026-08 / 2026-Q2, 8,467 series). `CPI_M` (monthly indicator) **stopped at 2025-09**. `CPI_Q` also current.
- `CPI` dimensions: `MEASURE.INDEX.TSEST.REGION.FREQ`. Region `50` = Australia; TSEST `10` original / `20` SA / `30` trend.
- Index codes: `10001` All groups, `999902` Trimmed mean, `999903` Weighted median, `115528`/`115529` Insurance (two codes — need to confirm which is the group vs expenditure class), `126670` Insurance and financial services, `40085` Maintenance and repair of motor vehicles, `40084` Spare parts and accessories.
- **Monthly sub-indices only start 2024-04** (29 obs to 2026-08); quarterly insurance CPI runs back to at least 2000-Q1. Treat monthly and quarterly as separate registry series; long history charts must use quarterly.
- ABS data contains **genuine zeros** (e.g. 0.0% monthly change). "No silent zeros" validation must be based on `observation_status`, not a ban on 0 values.

## Decisions / proposed changes to the plan

1. APRA landing URL corrected (above). No insurer benchmarking (institution-level hiatus confirmed).
2. IVI 4-digit is 3mma original only → no SA aggregation risk at 4-digit; store coverage as the 3-month window (`period_start` = first day of M-2). Rule extended: never sum 3mma unit groups to compare with the published total.
3. Carry two classification versions: IVI `ANZSCO v1.2 (inferred)`, exposure `ANZSCO v1.3`; join on 4-digit code.
4. HTTP User-Agent must not contain a URL (JSA WAF).
5. CPI: use `CPI` v2.0.0 dataflow; monthly from 2024-04, quarterly for history.

## Open questions for review

- Confirm the IVI ANZSCO version from the methodology PDF (or accept "inferred").
- Which APRA measures to headline in milestone 1/2: suggest insurance revenue, incurred claims, insurance service result and GWP for Householders, Domestic motor, Commercial motor, Fire & ISR. A loss-ratio-style measure would be *derived* (incurred claims ÷ insurance revenue, discrete quarter, gross of reinsurance) and must be labelled as ours, not APRA's.
- 6-digit ANZSCO codes for underwriters and claims officers.
