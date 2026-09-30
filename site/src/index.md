---
title: Overview
---

# Australian economy, insurance & AI-jobs

A descriptive dashboard built from public data. It shows what is happening; it does not estimate how much of any change AI caused.

```js
import {fmt, statusBadge} from "./components/charts.js";
const data = await FileAttachment("data/observations.json").json();
const status = await FileAttachment("data/status.json").json();
```

```js
function latest(id) {
  const rows = data.rows.filter((r) => r.id === id && r.value != null);
  return rows.at(-1);
}
function tile({label, id, format, periodFormat = (r) => r.end, note}) {
  const r = latest(id);
  const meta = data.series[id];
  const src = status[meta.source];
  return html`<div class="card tile">
    <div class="label">${label}</div>
    <div class="value">${r ? format(r.value) : "–"}</div>
    <div class="sub">${r ? periodFormat(r) : "no data"}${note ? html` · ${note}` : ""}</div>
    <div class="prov"><a href=${meta.source_url} target="_blank" rel="noopener">${src.name}</a><br>${statusBadge(src)}</div>
  </div>`;
}
const q = (r) => `Quarter ending ${fmt.month(new Date(r.end))}`;
const m3 = (r) => `3 months to ${fmt.month(new Date(r.end))}`;
```

<div class="grid grid-cols-4">
  ${tile({label: "RBA cash rate target", id: "rba.f1.cash_rate_target.aus.orig", format: fmt.pct, periodFormat: (r) => `As at ${fmt.date(new Date(r.end))}`})}
  ${tile({label: "Householders claims ratio (derived)", id: "derived.apra.claims_ratio.householders.direct.aasb17", format: fmt.pct0, periodFormat: q, note: "incurred claims ÷ insurance revenue"})}
  ${tile({label: "Online job ads, all occupations", id: "jsa.ivi.ads_3mma.total.aust.orig", format: fmt.count, periodFormat: (r) => `Month of ${fmt.month(new Date(r.end))}`})}
  ${tile({label: "Job ads: loss adjusters & insurance investigators", id: "jsa.ivi.ads_3mma.anzsco4_5996.aust.orig", format: fmt.count, periodFormat: m3, note: "ANZSCO 5996"})}
</div>

## Source status

```js
const order = ["validation_failed", "fetch_failed", "overdue", "never_run", "ok"];
const rowsS = Object.entries(status).sort((a, b) => order.indexOf(a[1].status) - order.indexOf(b[1].status));
```

<div class="card">
<table class="status">
  <thead><tr><th>Source</th><th>Status</th><th>Since</th><th>Latest period</th><th>Data last changed</th><th>Required</th><th>Note</th></tr></thead>
  <tbody>${rowsS.map(([k, s]) => html`<tr>
    <td><a href=${s.landing_url} target="_blank" rel="noopener">${s.name}</a></td>
    <td>${statusBadge(s)}</td><td>${s.since ?? "–"}</td><td>${s.latest_period ?? "–"}</td>
    <td>${s.last_data_change ?? "–"}</td><td>${s.required ? "yes" : "no"}</td><td>${s.message ?? ""}</td></tr>`)}</tbody>
</table>
<div class="prov">"Overdue" means the expected release date has passed with no new data — different from a failed fetch. When a fetch or validation fails, the last validated data stays on the site.</div>
</div>
