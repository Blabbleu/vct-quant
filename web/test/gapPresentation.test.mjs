import test from "node:test";
import assert from "node:assert/strict";
import { gapPresentation } from "../src/lib/gapPresentation.ts";

test("wide live-like quote preserves delta without an edge classification", () => {
  const result = gapPresentation(0.382203, 0.5, 0.9);
  assert.equal(result.kind, "wide");
  assert.ok(Math.abs(result.gapPoints - -11.7797) < 1e-9);
  assert.equal(result.kind === "wide", true);
});

test("liquidity boundary requires 1000 volume at a 0.10 spread", () => {
  assert.deepEqual(gapPresentation(0.62, 0.5, 0.1, 1000), { kind: "big", gapPoints: 12 });
  assert.equal(gapPresentation(0.62, 0.5, 0.1, 999.99).kind, "untrusted");
});

test("spread above the threshold is wide", () => {
  assert.equal(gapPresentation(0.62, 0.5, 0.100001, 1000).kind, "wide");
});

test("trusted gaps classify BIG GAP and AGREE at their boundaries", () => {
  assert.equal(gapPresentation(0.61, 0.5, 0.1, 1000).kind, "big");
  assert.equal(gapPresentation(0.509, 0.5, 0.1, 1000).kind, "agree");
});

test("missing volume is untrusted and missing market stays no-price", () => {
  assert.equal(gapPresentation(0.62, 0.5, 0.04, null).kind, "untrusted");
  assert.equal(gapPresentation(0.62, null, 0.04, 1000).kind, "no-price");
});

test("missing market has the no-price state", () => {
  assert.deepEqual(gapPresentation(0.6, null, 0.9), { kind: "no-price" });
});
