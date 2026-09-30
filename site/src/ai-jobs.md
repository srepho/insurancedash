---
title: AI & jobs
---

# AI exposure and the labour market

<div class="caveat">
<strong>Read this first.</strong> Exposure is not displacement. A high exposure score means Gen AI could perform or assist many of an occupation's tasks. It does not mean jobs are being lost. This page describes trends side by side and makes no causal claim. Four concepts are kept separate throughout: theoretical task exposure, observed AI usage, employer demand for AI skills, and employment and job-ad outcomes.
</div>

```js
import {fmt, lineChart, provenance, seriesRows, tableView} from "./components/charts.js";
const data = await FileAttachment("data/observations.json").json();
const status = await FileAttachment("data/status.json").json();
const exposure = await FileAttachment("data/exposure.json").json();
const IVI = [
  {id: "jsa.ivi.ads_3mma.anzsco4_5996.aust.orig", label: "Loss adjusters (5996)"},
  {id: "jsa.ivi.ads_3mma.total.aust.orig", label: "All occupations"}
];
```

## Job ads, indexed to a baseline

```js
const BASELINES = [
  {label: "3 months to Nov 2022 (ChatGPT release)", from: "2022-09-01", to: "2022-11-30"},
  {label: "12 months to Nov 2022", from: "2021-12-01", to: "2022-11-30"},
  {label: "3 months to Nov 2019 (pre-COVID)", from: "2019-09-01", to: "2019-11-30"},
  {label: "Single month: Nov 2022", from: "2022-11-01", to: "2022-11-30"}
];
const baseline = view(Inputs.select(BASELINES, {label: "Baseline", format: (b) => b.label, width: 340}));
```

```js
const raw = seriesRows(data, IVI);
const base = new Map(IVI.map((s) => {
  const v = raw.filter((r) => r.label === s.label && r.value != null && r.date >= new Date(baseline.from) && r.date <= new Date(baseline.to + "T23:59:59"));
  return [s.label, v.length ? v.reduce((a, r) => a + r.value, 0) / v.length : null];
}));
const indexed = raw.map((r) => ({...r, value: r.value == null || !base.get(r.label) ? null : (100 * r.value) / base.get(r.label)}));
const baselineMark = Plot.rectX([baseline], {x1: (d) => new Date(d.from), x2: (d) => new Date(d.to), fill: "currentColor", fillOpacity: 0.08});
```

<div class="card">
  <h2>Online job ads, index (baseline = 100)</h2>
  ${resize((width) => lineChart(indexed, {series: IVI, width, y: {label: "index", format: fmt.index}, extraMarks: [baselineMark, Plot.ruleY([100], {stroke: "var(--baseline)"})]}))}
  ${tableView(indexed, {valueFormat: fmt.index})}
  ${provenance(data, status, IVI.map((s) => s.id), {unitNote: "index of job ads (3-month moving average, original series); shaded band = baseline window"})}
</div>

Absolute counts are shown alongside, on separate axes, because the two series differ in scale by a factor of several hundred.

<div class="grid grid-cols-2">
${IVI.map((s) => {
  const rows = raw.filter((r) => r.label === s.label);
  return html`<div class="card"><h3>${s.id.includes("5996") ? "Loss adjusters, insurance investigators & risk surveyors (ANZSCO 5996)" : s.label}</h3>
    ${resize((width) => lineChart(rows, {series: [s], width, height: 220, zero: true, y: {label: "job ads (3mma)", format: fmt.count}}))}
    ${tableView(rows, {valueFormat: fmt.count})}
    ${provenance(data, status, [s.id])}</div>`;
})}
</div>

<div class="break-note">The IVI 4-digit data is a 3-month moving average of original, not seasonally adjusted, counts. Unit groups are not summed: the 3-month averages of the occupations do not add up to the published total. ANZSCO 5996 is a unit group, and this is the finest level the IVI measures. Its 6-digit roles are not separately measured.</div>

## Gen AI exposure of insurance-relevant occupations

```js
const WATCH = ["1492", "2221", "2241", "5411", "5523", "5996", "6112"];
const byCode = d3.group(exposure.filter((d) => WATCH.includes(d.occupation_code)), (d) => d.occupation_code);
const version = [...new Set(exposure.map((d) => `${d.score_version} (published ${d.published_at}, ${d.classification_version})`))];
const watchRows = WATCH.map((c) => {
  const g = byCode.get(c) ?? [];
  const m = Object.fromEntries(g.map((d) => [d.exposure_measure, d.score]));
  return {code: c, title: g[0]?.occupation_title ?? "(not in exposure data)", augmentation: m.jsa_genai_augmentation, automation: m.jsa_genai_automation};
});
```

<div class="card">
${Inputs.table(watchRows, {
  columns: ["code", "title", "augmentation", "automation"],
  header: {code: "ANZSCO", title: "Unit group", augmentation: "Augmentation exposure (0–1)", automation: "Automation exposure (0–1)"},
  format: {augmentation: (v) => v?.toFixed(2), automation: (v) => v?.toFixed(2)},
  select: false, rows: 8
})}
<div class="prov">Source: <a href="https://www.jobsandskills.gov.au/studies/generative-artificial-intelligence-capacity-study" target="_blank" rel="noopener">JSA Gen AI Capacity Study</a> · Score version: ${version.join("; ")} · These are theoretical task exposure scores, not observed usage. Applying them to periods before 2025 is a <strong>retrospective classification</strong>. Several unit groups are broader than the insurance role: 2241 includes mathematicians and statisticians, and 2221 includes all financial brokers.</div>
</div>

<div class="break-note">Coming in milestone 3: the full insurance watchlist, with job ads, employment, exposure, measurement granularity and mapping coverage for each role, plus the exposure-versus-change scatter. Coming in milestone 4: the AI-mention share of job postings (Indeed Hiring Lab) and alternative exposure indices as sensitivity checks.</div>
