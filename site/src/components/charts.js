// Shared chart, table-view and provenance components.
// Colour follows the entity: callers pass series in a fixed order and slot i is always --series-(i+1).
import * as Plot from "npm:@observablehq/plot";
import {html} from "npm:htl";

const STATUS_LABEL = {
  ok: "Up to date",
  overdue: "Overdue",
  fetch_failed: "Fetch failed — showing last good data",
  validation_failed: "Invalid source — showing last good data",
  never_run: "No data yet"
};

export function seriesColors() {
  const cs = getComputedStyle(document.documentElement);
  return [1, 2, 3, 4].map((i) => cs.getPropertyValue(`--series-${i}`).trim());
}

function css(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

/** Rows for the given series ids, dated at period end. Non-observed values stay null (gaps, never 0). */
export function seriesRows(data, series, transform = (v) => v) {
  const label = new Map(series.map((s) => [s.id, s.label]));
  return data.rows
    .filter((r) => label.has(r.id))
    .map((r) => ({
      id: r.id,
      label: label.get(r.id),
      date: new Date(r.end),
      start: new Date(r.start),
      value: r.value == null ? null : transform(r.value),
      status: r.status
    }));
}

export const fmt = {
  pct: (v) => (v == null ? "–" : `${v.toFixed(2)}%`),
  pct0: (v) => (v == null ? "–" : `${v.toFixed(0)}%`),
  audbn: (v) => (v == null ? "–" : `$${v.toFixed(2)}bn`),
  count: (v) => (v == null ? "–" : Math.round(v).toLocaleString("en-AU")),
  index: (v) => (v == null ? "–" : v.toFixed(1)),
  date: (d) => d.toLocaleDateString("en-AU", {year: "numeric", month: "short", day: "numeric", timeZone: "UTC"}),
  month: (d) => d.toLocaleDateString("en-AU", {year: "numeric", month: "short", timeZone: "UTC"}),
  quarter: (d) => `${["Mar", "Jun", "Sep", "Dec"][Math.floor(d.getUTCMonth() / 3)]} qtr ${d.getUTCFullYear()}`
};

/**
 * Single-axis line chart with legend (>= 2 series), direct end labels, crosshair tooltip.
 * opts: {series:[{id,label}], y:{label, format}, xFormat, curve, zero, extraMarks, height, width}
 */
export function lineChart(rows, opts) {
  const {series, width, height = 280, y = {}, xFormat = fmt.month, curve = "linear", zero = false} = opts;
  const colors = seriesColors();
  const domain = series.map((s) => s.label);
  const range = domain.map((_, i) => colors[i]);
  const multi = series.length > 1;
  const last = [];
  for (const s of series) {
    const pts = rows.filter((r) => r.label === s.label && r.value != null);
    if (pts.length) last.push(pts[pts.length - 1]);
  }
  // Direct end labels: spread vertically so labels for series ending close together never overlap.
  const vals = rows.map((r) => r.value).filter((v) => v != null);
  const span = (Math.max(...vals, zero ? 0 : -Infinity) - Math.min(...vals, zero ? 0 : Infinity)) || 1;
  const gap = (span * 16) / (height - 60);
  const labels = last.map((d) => ({...d, labelY: d.value})).sort((a, b) => a.labelY - b.labelY);
  for (let i = 1; i < labels.length; i++) {
    labels[i].labelY = Math.max(labels[i].labelY, labels[i - 1].labelY + gap);
  }
  const quarterly = opts.xFormat === fmt.quarter;
  const ticks = quarterly ? [...new Set(rows.map((r) => +r.date))].sort().map((t) => new Date(t)) : undefined;
  return Plot.plot({
    width,
    height,
    marginRight: multi ? 130 : 70,
    marginLeft: 56,
    style: {fontSize: "12px", color: css("--text-secondary"), background: "transparent"},
    x: quarterly
      ? {type: "utc", label: null, ticks: width < 640 ? ticks.filter((_, i) => i % 2 === 0) : ticks,
         tickFormat: (d) => fmt.quarter(d).replace(" qtr ", "\n")}
      : {type: "utc", label: null, grid: false},
    y: {label: y.label ?? null, grid: true, zero, tickFormat: y.tickFormat},
    color: {domain, range, legend: multi},
    marks: [
      ...(opts.extraMarks ?? []),
      zero ? Plot.ruleY([0], {stroke: css("--baseline")}) : null,
      Plot.line(rows, {x: "date", y: "value", z: "label", stroke: "label", strokeWidth: 2, curve}),
      Plot.dot(last, {x: "date", y: "value", fill: "label", r: 4, stroke: css("--surface-1"), strokeWidth: 2}),
      Plot.text(labels, {
        x: "date",
        y: "labelY",
        text: (d) => (multi ? d.label : y.format(d.value)),
        dx: 8,
        textAnchor: "start",
        fill: css("--text-primary"),
        fontSize: 11
      }),
      Plot.ruleX(rows, Plot.pointerX({x: "date", stroke: css("--baseline")})),
      Plot.tip(
        rows.filter((r) => r.value != null),
        Plot.pointerX({
          x: "date",
          y: "value",
          stroke: "label",
          title: (d) => `${d.label}\n${xFormat(d.date)}: ${y.format(d.value)}`
        })
      )
    ]
  });
}

/** Collapsible table twin of a chart (every value reachable without hover or colour). */
export function tableView(rows, {valueFormat, dateFormat = fmt.month}) {
  const labels = [...new Set(rows.map((r) => r.label))];
  const byDate = new Map();
  for (const r of rows) {
    const k = +r.date;
    if (!byDate.has(k)) byDate.set(k, {date: r.date});
    byDate.get(k)[r.label] = r.value == null ? `(${r.status})` : valueFormat(r.value);
  }
  const body = [...byDate.values()].sort((a, b) => b.date - a.date);
  return html`<details class="table-view"><summary>Table view (${body.length} periods)</summary>
    <table><thead><tr><th>Period ending</th>${labels.map((l) => html`<th>${l}</th>`)}</tr></thead>
    <tbody>${body.map(
      (row) => html`<tr><td>${dateFormat(row.date)}</td>${labels.map((l) => html`<td>${row[l] ?? ""}</td>`)}</tr>`
    )}</tbody></table></details>`;
}

export function statusBadge(src) {
  const s = src?.status ?? "never_run";
  return html`<span class="badge ${s}" title=${src?.message ?? ""}>${STATUS_LABEL[s] ?? s}</span>`;
}

/** Provenance line: source link, units, reference period, freshness. Shown under every chart. */
export function provenance(data, status, ids, {unitNote} = {}) {
  const metas = ids.map((id) => data.series[id]).filter(Boolean);
  if (!metas.length) return html`<div class="prov">No registered series.</div>`;
  const src = status[metas[0].source];
  const first = metas.map((m) => m.first).filter(Boolean).sort()[0];
  const last = metas.map((m) => m.last).filter(Boolean).sort().at(-1);
  const units = [...new Set(metas.map((m) => m.unit))].join(", ");
  const sep = html`<span class="sep">·</span>`;
  return html`<div class="prov">
    Source: <a href=${metas[0].source_url} target="_blank" rel="noopener">${src?.name ?? metas[0].source}</a>
    ${sep} Unit: ${unitNote ?? units}
    ${sep} Period: ${first ?? "–"} to ${last ?? "–"} (${metas[0].frequency}, ${metas[0].adjustment})
    ${sep} Data last changed: ${src?.last_data_change ?? "–"}
    ${sep} ${statusBadge(src)}
  </div>`;
}
