# Australian Economy, Insurance & AI-Jobs Dashboard

A static dashboard tracking Australian macro indicators, general insurance industry conditions, and AI exposure alongside labour-market trends, built entirely from public data.

It is **descriptive, not causal**: it shows what is happening and does not estimate how much of any change AI caused.

- **Pipeline:** Python 3.12 + `uv`. Each source is an isolated module in `ingest/`. Outputs are validated against `registry/series.yaml` and stored as Parquet in `data/parquet/`, the authoritative store.
- **Site:** [Observable Framework](https://observablehq.com/framework/) in `site/`, deployed to GitHub Pages by `.github/workflows/update.yml` (daily).
- **Sources (so far):** RBA F1, APRA Quarterly General Insurance Performance Statistics (AASB 17 basis), JSA Internet Vacancy Index, JSA Gen AI Capacity Study exposure scores.

## Quick start

```bash
uv sync
uv run python -m ingest.run           # fetch, validate, promote; writes data/parquet + data/status.json
uv run pytest                         # tests (offline, fixture-based)
cd site && npm ci && npm run dev      # local preview
cd site && npm run build              # static build in site/dist (+ dist/fingerprint.txt)
```

Ad-hoc querying: `duckdb -c "select * from 'data/parquet/observations/*.parquet' limit 10"`. No `.duckdb` file is committed.

## How it stays honest

- Missing and suppressed values are stored as empty, never 0.
- Every series has a registry entry giving its units, frequency, adjustment, basis and breaks. Every chart shows its source, units, reference period and freshness.
- APRA's July 2023 reporting break is enforced. Current-basis series reject any pre-break period.
- Revisions to any past value are detected, and superseded rows are kept in `data/parquet/observations_history/`.
- A failed or malformed download keeps the last validated data and changes the source's status. An invalid required source blocks publication.

See `PLAN.md` for the design and `FINDINGS.md` for the source feasibility notes.

## Licences

Code: MIT (see `LICENSE`). Data remains under its publishers' licences: RBA (CC BY 4.0), APRA (CC BY 3.0 AU), JSA (CC BY 4.0). No endorsement is implied.
