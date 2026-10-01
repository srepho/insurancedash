// IVI observations already average three months. Use non-overlapping windows.
export const BASELINES = [
  {label: "3 months to Nov 2022 (ChatGPT release)", from: "2022-09-01", to: "2022-11-30", ends: ["2022-11-30"]},
  {label: "12 months to Nov 2022", from: "2021-12-01", to: "2022-11-30", ends: ["2022-02-28", "2022-05-31", "2022-08-31", "2022-11-30"]},
  {label: "3 months to Nov 2019 (pre-COVID)", from: "2019-09-01", to: "2019-11-30", ends: ["2019-11-30"]}
];

export function baselineValue(rows, baseline) {
  const values = baseline.ends.map((end) => rows.filter((r) => +r.date === +new Date(end)));
  if (values.some((matches) => matches.length !== 1 || !Number.isFinite(matches[0].value))) return null;
  return values.reduce((sum, matches) => sum + matches[0].value, 0) / values.length;
}
