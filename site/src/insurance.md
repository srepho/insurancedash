---
title: Insurance
---

# General insurance

```js
import {fmt, lineChart, provenance, seriesRows, tableView} from "./components/charts.js";
const data = await FileAttachment("data/observations.json").json();
const status = await FileAttachment("data/status.json").json();
const CLASSES = [
  ["householders", "Householders"],
  ["domestic_motor", "Domestic motor"],
  ["commercial_motor", "Commercial motor"],
  ["fire_isr", "Fire and ISR"]
];
const ids = (measure, prefix = "apra.qgips") => CLASSES.map(([k, label]) => ({id: `${prefix}.${measure}.${k}.direct.aasb17`, label}));
const bn = (v) => v / 1e9;
const qOpts = {xFormat: fmt.quarter};
```

<div class="break-note">
<strong>Series break, July 2023.</strong> APRA moved to a new reporting framework and AASB 17 from 1 July 2023 and warns that current and historical publications are not directly comparable. Only the current basis is shown here. Quarterly flow data starts in the December quarter 2023. Pre-July 2023 history will appear as a separate segment and is never joined to these series. From July 2023, gross written premium also includes fire service and other state levies.
</div>

```js
const ratio = ids("claims_ratio", "derived.apra");
const ratioRows = seriesRows(data, ratio);
```

<div class="card">
  <h2>Claims ratio by class (derived)</h2>
  <p class="prov" style="border:0;margin:0 0 .4rem;padding:0">Calculated by this dashboard, not published by APRA: incurred claims ÷ insurance revenue for the same quarter, direct business, gross of reinsurance. Above 100% means claims incurred in the quarter exceeded the insurance revenue recognised.</p>
  ${resize((width) => lineChart(ratioRows, {series: ratio, width, zero: true, y: {label: "per cent", format: fmt.pct0}, ...qOpts}))}
  ${tableView(ratioRows, {valueFormat: fmt.pct0, dateFormat: fmt.quarter})}
  ${provenance(data, status, ratio.map((s) => s.id))}
</div>

```js
const claims = ids("incurred_claims");
const claimsRows = seriesRows(data, claims, (v) => -bn(v));
```

<div class="card">
  <h2>Incurred claims by class</h2>
  ${resize((width) => lineChart(claimsRows, {series: claims, width, zero: true, y: {label: "A$ billion per quarter", format: fmt.audbn}, ...qOpts}))}
  ${tableView(claimsRows, {valueFormat: fmt.audbn, dateFormat: fmt.quarter})}
  ${provenance(data, status, claims.map((s) => s.id), {unitNote: "A$ billion per quarter; APRA publishes claims as a negative expense, shown here as positive"})}
</div>

```js
const result = ids("insurance_service_result");
const resultRows = seriesRows(data, result, bn);
```

<div class="card">
  <h2>Insurance service result, net of reinsurance</h2>
  ${resize((width) => lineChart(resultRows, {series: result, width, zero: true, y: {label: "A$ billion per quarter", format: fmt.audbn}, ...qOpts}))}
  ${tableView(resultRows, {valueFormat: fmt.audbn, dateFormat: fmt.quarter})}
  ${provenance(data, status, result.map((s) => s.id), {unitNote: "A$ billion per quarter"})}
</div>

## Premium volume: insurance revenue and gross written premium

Two measures on one axis (same unit). Revenue is recognised over the coverage period; gross written premium is booked when written.

```js
function classPair(k, label) {
  const s = [
    {id: `apra.qgips.insurance_revenue.${k}.direct.aasb17`, label: "Insurance revenue"},
    {id: `apra.qgips.gross_written_premium.${k}.direct.aasb17`, label: "Gross written premium"}
  ];
  const rows = seriesRows(data, s, bn);
  return html`<div class="card"><h3>${label}</h3>
    ${resize((width) => lineChart(rows, {series: s, width, height: 220, zero: true, y: {label: "A$ bn / quarter", format: fmt.audbn}, ...qOpts}))}
    ${tableView(rows, {valueFormat: fmt.audbn, dateFormat: fmt.quarter})}
    ${provenance(data, status, s.map((x) => x.id), {unitNote: "A$ billion per quarter"})}</div>`;
}
```

<div class="grid grid-cols-2">
  ${CLASSES.map(([k, label]) => classPair(k, label))}
</div>

<div class="break-note">Coming in milestone 2: premium inflation (insurance CPI) and the partial claims-cost indicators (motor repair and spare parts CPI), plus a catastrophe timeline alongside the property results. Insurer-level benchmarking is not planned: APRA's institution-level statistics have not been published since June 2023.</div>
