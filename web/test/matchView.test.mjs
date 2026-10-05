import test from "node:test";
import assert from "node:assert/strict";
import { favouriteSide, sideView, spreadLabels } from "../src/lib/matchView.ts";

test("match 753448: favourite T1 with model 62.0 and market 53.5 gives a +8.5 gap on the T1 side", () => {
  const pA = 0.37960206697389304, marketA = 0.465;
  const side = favouriteSide(pA);
  assert.equal(side, "b");
  const v = sideView(pA, marketA, side);
  assert.equal(v.side, "b");
  assert.equal(v.model.toFixed(3), "0.620");
  assert.equal(v.market.toFixed(3), "0.535");
  assert.equal(v.gapPts.toFixed(1), "8.5");
});

test("the gap flips sign with the side, magnitude unchanged", () => {
  const a = sideView(0.38, 0.465, "a"), b = sideView(0.38, 0.465, "b");
  assert.ok(a.gapPts < 0 && b.gapPts > 0);
  assert.ok(Math.abs(a.gapPts + b.gapPts) < 1e-9);
});

test("no market means no market and no gap", () => {
  const v = sideView(0.7, null, "a");
  assert.equal(v.market, null);
  assert.equal(v.gapPts, null);
});

test("favourite is team A at exactly 50%", () => { assert.equal(favouriteSide(0.5), "a"); });

test("spreadLabels keeps labels at least the gap apart and inside bounds", () => {
  const out = spreadLabels([100, 103], 14, 10, 200);
  assert.ok(Math.abs(out[0] - out[1]) >= 14 - 1e-9);
  const edge = spreadLabels([198, 199], 14, 10, 200);
  assert.ok(edge.every(y => y <= 200 && y >= 10) && Math.abs(edge[0] - edge[1]) >= 14 - 1e-9);
  assert.deepEqual(spreadLabels([50, 120], 14, 10, 200), [50, 120]);
  assert.equal(spreadLabels([], 14, 0, 10).length, 0);
});

test("spreadLabels preserves which label is which", () => {
  const out = spreadLabels([120, 118], 14, 10, 200);
  assert.ok(out[0] > out[1]);
});
