---
title: Macro
---

# Macroeconomy

```js
import {fmt, lineChart, provenance, seriesRows, tableView} from "./components/charts.js";
const data = await FileAttachment("data/observations.json").json();
const status = await FileAttachment("data/status.json").json();
const cash = [{id: "rba.f1.cash_rate_target.aus.orig", label: "Cash rate target"}];
const cashRows = seriesRows(data, cash);
```

<div class="card">
  <h2>RBA cash rate target</h2>
  ${resize((width) => lineChart(cashRows, {series: cash, width, curve: "step-after", zero: true, y: {label: "per cent", format: fmt.pct}, xFormat: fmt.date}))}
  ${tableView(cashRows.filter((r, i, a) => i === 0 || r.value !== a[i - 1].value || r.status !== "observed"), {valueFormat: fmt.pct, dateFormat: fmt.date})}
  ${provenance(data, status, cash.map((s) => s.id))}
</div>

<div class="break-note">The table view lists only the dates on which the target changed (and any blank days). Inflation against the RBA target band, the labour market, real wages, the AUD and household spending arrive in milestone 2.</div>
