---
title: About & methods
---

# About, sources and methods

```js
import {statusBadge} from "./components/charts.js";
const data = await FileAttachment("data/observations.json").json();
const status = await FileAttachment("data/status.json").json();
```

## Sources and licences

<div class="card">
<table class="status">
<thead><tr><th>Source</th><th>Licence</th><th>Required</th><th>Status</th><th>Overdue after</th></tr></thead>
<tbody>${Object.entries(status).map(([k, s]) => html`<tr>
  <td><a href=${s.landing_url} target="_blank" rel="noopener">${s.name}</a></td><td>${s.licence}</td>
  <td>${s.required ? "yes — blocks publication if invalid" : "no — published with a stale badge"}</td>
  <td>${statusBadge(s)}</td><td>${s.overdue_after_days == null ? "n/a (one-off release)" : `${s.overdue_after_days} days after latest period`}</td></tr>`)}</tbody>
</table>
</div>

APRA material: © Australian Prudential Regulation Authority, CC BY 3.0 AU. RBA material: © Reserve Bank of Australia, CC BY 4.0. JSA material: © Commonwealth of Australia, CC BY 4.0. No endorsement by any source is implied.

## Release calendar

- **RBA F1:** daily, on business days.
- **APRA Quarterly General Insurance Performance Statistics:** quarterly, about two months after quarter end.
- **JSA Internet Vacancy Index:** monthly, usually on the third Wednesday. JSA publishes the upcoming dates on the [IVI page](https://www.jobsandskills.gov.au/data/internet-vacancy-index).
- **JSA Gen AI exposure:** a one-off release (September 2025). New versions are added alongside the old one; they never replace it.

## Classification versions

- **IVI occupations:** ANZSCO 4-digit unit groups. JSA does not state the version inside the file; the titles match **ANZSCO v1.2** wording, so the version is recorded as *inferred*.
- **Gen AI exposure:** **ANZSCO v1.3** unit groups (357).
- The IVI and exposure data are joined on the 4-digit code, never the title. 350 of 351 coded IVI unit groups match, covering 99.9% of occupation-coded ads. 6399 (Other Sales Support Workers) has no exposure score. Seven unit groups are suppressed in the IVI.
- ANZSCO is being replaced by OSCA. Every occupation code carries its classification version.

## Methods

- Data is fetched on a schedule, written to a staging area, and validated against the [series registry](https://github.com/srepho/insurancedash/blob/main/registry/series.yaml) before it replaces the previous good data. A failed or malformed source keeps its last validated data, and its status changes.
- Missing, suppressed and unavailable values are stored as empty, never as zero, and appear as gaps in charts.
- Revisions: each series' full history is hashed on every run. When any past value changes, the superseded values move to a history table, so earlier releases can be reproduced.
- Derived measures, such as the claims ratio, are labelled as calculated by this dashboard. The registry records each derivation's formula, gross or net basis, and denominator.
- Indices on the AI & jobs page are computed in your browser from the published counts, with a selectable baseline.

## Known breaks and gaps

```js
const breaks = Object.entries(data.series).flatMap(([id, s]) => (s.breaks ?? []).map((b) => ({id, ...b})));
const uniq = [...new Map(breaks.map((b) => [b.date + b.description, b])).values()];
```

${uniq.map((b) => html`<div class="break-note"><strong>${b.date}</strong>: ${b.description} (affects ${breaks.filter((x) => x.date === b.date).length} series)</div>`)}

- The IVI has no seasonally adjusted series at the 4-digit level; only 3-month averages of original counts are published.
- APRA institution-level (insurer) statistics have not been published since June 2023.
- ABS monthly CPI sub-indices (insurance, motor repair) start in April 2024; longer history must use the quarterly CPI (milestone 2).

## Series registry

```js
const reg = Object.entries(data.series).map(([id, s]) => ({id, ...s, basis: s.measure_basis ? Object.values(s.measure_basis).filter(Boolean).join("; ") : ""}));
```

${Inputs.table(reg, {
  columns: ["id", "title", "unit", "frequency", "adjustment", "basis", "first", "last", "definition"],
  header: {id: "series_id", basis: "Measure basis"},
  width: {definition: 420, id: 300},
  select: false, rows: 30
})}
