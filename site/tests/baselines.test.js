import {test} from "node:test";
import assert from "node:assert/strict";
import {BASELINES, baselineValue} from "../src/components/baselines.js";

const row = (end, value) => ({date: new Date(end), value});

test("three-month baseline uses November's published average without smoothing again", () => {
  assert.equal(baselineValue([row("2022-09-30", 900), row("2022-10-31", 800), row("2022-11-30", 700)], BASELINES[0]), 700);
});

test("annual baseline weights each month once through four disjoint windows", () => {
  const rows = [row("2022-02-28", 100), row("2022-05-31", 200), row("2022-08-31", 300), row("2022-11-30", 400), row("2022-10-31", 999)];
  assert.equal(baselineValue(rows, BASELINES[1]), 250);
  assert.equal(baselineValue(rows.slice(1), BASELINES[1]), null);
});

test("missing, suppressed or duplicate baseline points do not silently change the window", () => {
  assert.equal(baselineValue([], BASELINES[0]), null);
  assert.equal(baselineValue([row("2022-11-30", null)], BASELINES[0]), null);
  assert.equal(baselineValue([row("2022-11-30", 1), row("2022-11-30", 2)], BASELINES[0]), null);
});
