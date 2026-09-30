# Plan: Australian Economy, Insurance & AI-Jobs Dashboard

## Goal

Build a static dashboard that tracks three things:

1. Australian macroeconomic indicators.
2. General insurance industry conditions in Australia.
3. AI exposure, AI adoption and labour-market trends in Australia, with a focus on occupations relevant to insurance.

The dashboard describes what is happening. It does not claim to measure how much of any change AI caused.

It uses public data only. Data is fetched on a schedule, validated, and stored as Parquet, which is the single authoritative processed store. The site is rendered with Observable Framework and deployed to GitHub Pages by GitHub Actions. There is no server and no running cost.

## Constraints

- **Public data only.** Never add employer-internal data.
- **Python 3.12 for ingestion.** Use `uv`, and commit the lockfiles (`uv.lock` and `package-lock.json`).
- **Parquet is authoritative.** Generate DuckDB from the Parquet files locally for ad-hoc querying. Do not commit a `.duckdb` file.
- **Isolated sources.** Each source is its own module, so one broken source never blocks the others.
- **Verify before hardcoding.** Check every URL, dataflow ID, table ID and occupation code live before using it. Treat the IDs in this plan as starting points. Where a source only exposes a landing page, as APRA and JSA do, scrape the page for the latest file link.
- **Show provenance from the start.** Every chart shows its source link, units, reference period, and freshness from the first real release onward, not as a later polish step.

## Repo layout

```
.
├── ingest/
│   ├── common.py          # HTTP session, retries, hashing, staging/validation helpers
│   ├── registry.py        # loads + validates series registry
│   ├── abs.py  rba.py  apra.py  jsa.py  indeed.py
│   ├── exposure.py        # exposure scores + (later) crosswalks
│   └── run.py             # orchestrates sources, writes status
├── registry/
│   └── series.yaml        # series registry (see Data model)
├── data/
│   ├── raw/               # gitignored; snapshots archived as release assets
│   ├── parquet/
│   │   ├── observations/  # one file per source
│   │   ├── exposure_scores.parquet
│   │   ├── occupation_mappings.parquet
│   │   └── cat_events.parquet
│   ├── manual/            # hand-maintained CSVs (ICA events, watchlist)
│   └── status.json        # per-source status (see Workflow)
├── site/                  # Observable Framework project
│   └── src/ index.md macro.md insurance.md ai-jobs.md about.md data/
├── tests/
│   └── fixtures/          # small saved source files for parser tests
└── .github/workflows/update.yml
```

## Data model

### Series registry (`registry/series.yaml`)

The registry has one entry per `series_id`. Here, `series_id` names one complete dimensional series: the measure plus all of its dimensions. For example, `abs.lf.unemployment_rate.aus.sa` is the seasonally adjusted national unemployment rate.

Each entry records:

- the source's own series key
- the dimensions
- the unit
- the frequency
- the adjustment (original, seasonally adjusted, or trend)
- a definition
- any transformation applied, such as year-on-year growth
- the source URL
- the expected release cadence
- any structural break dates, such as APRA's July 2023 break

Every series in the Parquet output must appear in the registry, and each `series_id` must be unique.

### Observations

| column | notes |
|---|---|
| series_id | FK to registry |
| period_start, period_end | explicit coverage |
| value | nullable. Missing or suppressed values are never stored as 0. |
| observation_status | observed / provisional / suppressed / missing / unavailable |
| source_released_at | publisher's release date; nullable if unknown |
| retrieved_at | when the pipeline fetched it |
| vintage_id | hash of the source file it came from |

The primary key is (series_id, period_start, vintage_id).

### Revisions

Keep this lightweight. It is a personal dashboard, not a full real-time vintage database.

- Hash each series' full history on every run. Any change is a data change, even when the latest period stays the same.
- Keep the current vintage in `observations/`, and append superseded rows to `observations_history/`. This makes a past dashboard release reproducible.
- Archive raw source files as GitHub release assets, keyed by vintage_id, and never rely on CI caches for them.

### Separate tables

Exposure scores, occupation mappings, and catastrophe events do not fit the observation schema, so each gets its own table:

- `exposure_scores`: (occupation_code, classification_version, exposure_measure, score_version, score, published_at)
- `occupation_mappings`: (from_code, from_version, to_code, to_version, weight, weight_basis, is_ambiguous)
- `cat_events`: (event, start_date, end_date, region, peril, insured_loss_aud, source)

## Sources

### Macro (ABS and RBA)

**ABS Data API** (SDMX, `https://data.api.abs.gov.au`). Find the dataflow IDs through the `/dataflow` endpoint, and filter by dimension keys in the query.

- Monthly CPI: headline, trimmed mean, and the insurance, motor vehicle repair & servicing, and spare parts sub-indices. ABS moved to a complete monthly CPI in late 2025, so confirm which dataflow is now primary.
- Labour Force (monthly): headline measures.
- Labour Force, Detailed (quarterly): employment by occupation and by industry.
- Wage Price Index, National Accounts, Household Spending Indicator, and building approvals.

**RBA tables:** F1 (cash rate), F11 (exchange rates), and D2 (credit). These CSVs have multi-row metadata headers.

### Insurance

**APRA Quarterly General Insurance Performance Statistics.**

- APRA's reporting basis changed from July 2023, and APRA warns that historical and current publications are not directly comparable. Store the two as separate series, show them as separate segments, and never splice them unless comparability is explicitly established.
- For every measure, record in the registry the exact published measure, whether it is gross or net, the denominator, and whether it covers one quarter or a rolling year. This applies especially to "claims" and "loss ratio".
- Institution-level statistics are reportedly on hiatus. Only build insurer benchmarking if they are available, and only after checking.

**CPI series.**

- Label the insurance CPI as **consumer insurance-price (premium) inflation**, not as claims inflation.
- Label the repair and spare parts CPI series as **partial claims-cost indicators**.
- Describe all CPI series as "available sooner" than APRA data. Do not describe them as "leading".

**ICA catastrophe history** is hand-maintained in `data/manual/`, with the refresh steps documented.

### AI and jobs

**Keep the four concepts separate.** Never merge them into a single "AI impact" score. They are:

1. Theoretical task exposure.
2. Observed AI usage.
3. Employer demand for AI skills.
4. Employment and job-ad outcomes.

**Primary exposure source: JSA's GenAI exposure spreadsheets**, published at the ANZSCO occupation level. Inspect them first, record the ANZSCO version they use, and make them the default wherever their coverage allows.

**Job ads come from the JSA Internet Vacancy Index.**

- The IVI's finest level is ANZSCO 4-digit.
- Its seasonally adjusted series are adjusted independently of each other, so they are **non-additive**. Never sum adjusted occupation series and present the result as a total. Use original series for any aggregation.
- Never present 6-digit roles as separately measured when they share one 4-digit IVI series.

**Employment comes from ABS Labour Force, Detailed.** Keep these two views separate:

- Occupations relevant to insurance, regardless of the industry they work in.
- Employment within the insurance industry.

**Indeed Hiring Lab** provides AU postings, and AI-mention share where published. This measures employer demand for AI skills.

**Research extensions (milestone 4), used as sensitivity checks against JSA:**

- The Anthropic Economic Index. Note that its "observed exposure" measure combines capability estimates with actual usage, which is a different construct from theoretical exposure.
- One academic index, such as Felten AIOE or Eloundou et al.
- The crosswalks these require. The verified BLS SOC–ISCO crosswalk uses **SOC 2010**, so the chain is O*NET-SOC → SOC 2018 → SOC 2010 → ISCO-08 → ANZSCO. Record every classification version, weight and ambiguous match. Aggregate to Australia using **Australian employment weights**, and document any US weights used inside the mapping itself.

**Insurance watchlist** (`data/manual/insurance_occupations.csv`).

- Include insurance agents and brokers, claims officers and loss adjusters, underwriters, actuaries, contact-centre workers, and insurance clerks.
- Look up the real ANZSCO codes rather than inventing them.
- For each role, record its measurement granularity: the IVI level, the Labour Force level, and the exposure-data level.

## Pages

**`index.md`: Overview.**

- Headline tiles, each with a source and a freshness badge.
- A panel showing source status.

**`macro.md`**

- Inflation against the RBA target band.
- The labour market.
- Real wages.
- The cash rate.
- AUD.
- Household spending.

**`insurance.md`**

- APRA measures by class of business, with a visible break at July 2023.
- Premium inflation (insurance CPI) as its own chart.
- The partial claims-cost indicators (repair and parts CPI).
- A catastrophe timeline shown alongside the property results.

**`ai-jobs.md`**

- A scatter of exposure against change in job ads or employment by occupation. The exposure-score version and group memberships are frozen and labelled on the chart. Scores published after 2022 that are applied to earlier data are labelled as a **retrospective classification**.
- A baseline selector that offers windows, such as a 3-month average, as well as single dates. The default is the 3 months to November 2022.
- Indexed job-ad trends for exposure groups, showing the full history before November 2022 and **absolute counts alongside** the index.
- The insurance watchlist, showing job ads, employment, exposure, granularity, and mapping coverage for each role.
- The AI-mention share of job postings.
- A permanent caveat box: exposure is not displacement, and this page is descriptive, not causal.

**`about.md`**

- The source list and licences.
- The release calendar.
- Classification versions.
- Methods.
- Known breaks and gaps.

## Update workflow (GitHub Actions)

The workflow runs on a daily cron, plus `workflow_dispatch`.

It keeps three kinds of change separate:

- **Data change:** the content hash of any processed series or table has changed. This includes revisions.
- **Status change:** a source has moved between ok, fetch_failed, validation_failed, and overdue. "Overdue" means the expected release date has passed with no new data, which is different from a failed fetch. Only transitions count, and they are written to `status.json`.
- **Site or code change:** anything under `site/`, `ingest/`, or `registry/` has changed.

Routine `last_checked` timestamps go to workflow logs only. They are excluded from every hash and from `status.json`, so an unchanged run produces no diff.

Each run follows these steps:

1. **Ingest into staging.** Each source is written to a staging directory and then validated against the schema and registry. Validation checks that there are no silent zeros, that the expected series are present, and that parsing by header name succeeded. Only a source that passes validation replaces its good data. A failed or malformed source keeps its last validated data, and its status changes.
2. **Compute the build fingerprint.** This is a hash of the data, status, and site/code inputs.
3. **Compare against the last successful deploy.** Compare the fingerprint with the one recorded for the **last successful deploy**, not with the previous run. If they match, exit. If they differ, commit, build, and deploy. This means a failed deploy is retried on the next run without needing a new source update.
4. **Clear the Observable loader cache** (`site/src/.observablehq/cache`) before building whenever the data fingerprint has changed. Observable can reuse cached loader output without noticing that an input Parquet file has changed.
5. **Block publication** if the site build fails or any source marked `required: true` in the registry is invalid. Optional sources that fail are published with a stale badge.
6. **Record the new fingerprint** as last-deployed only after the deploy has succeeded.

## Milestones

Complete these in order, and stop for review after each one:

0. **Source feasibility.**
   - Parse one RBA series, one current-basis APRA measure, and one JSA IVI occupation series.
   - Load the JSA exposure spreadsheet, and test whether IVI occupations join to it: check the ANZSCO versions, the granularity, and the coverage.
   - Write up the findings before building anything else.
1. **Working dashboard.** Deploy those real series with the registry, units, periods, source links, status and freshness badges, validation, and the full update workflow.
2. **Macro and insurance.** Expand the indicator sets once the definitions and breaks are settled.
3. **Insurance watchlist.** Add IVI job ads and Labour Force employment against JSA exposure, with explicit granularity and coverage.
4. **Research extensions.** Add the Anthropic and academic indices, the crosswalk pipeline, comparisons between exposure measures, baseline sensitivity, Indeed data, and AI adoption sources.

## Acceptance criteria

**Pipeline**

- `uv run python -m ingest.run` works from a clean clone, and an immediate rerun produces no diff.
- A revision to an older observation is detected even when the latest period is unchanged.
- A failed or malformed download preserves the last validated data and sets the source's status.
- Missing or suppressed observations are never stored or shown as zero.

**Build and deploy**

- Changing a Parquet input changes the rendered chart, despite loader caching.
- A failed deploy is retried on the next run with no new source data.
- A failed build or an invalid required source blocks publication.

**Data rules**

- Every series appears in the registry, and every `series_id` is unique.
- APRA series before and after July 2023 are never joined into a single series.
- No aggregate is computed from independently seasonally adjusted IVI series.

**Watchlist and crosswalks**

- Every watchlist role displays its measurement granularity and mapping coverage.
- Crosswalk tests, which apply from milestone 4, check hand-verified mappings, report coverage honestly, and confirm no employment is double counted.

## Gotchas

- RBA CSVs have metadata header rows and mixed date formats.
- APRA and JSA xlsx layouts change between releases. Parse by header name, and fail clearly if the headers change.
- ANZSCO is being replaced by OSCA. Carry the classification version on every occupation code.
- Keep the repo small. Gitignore raw files and archive snapshots as release assets.
