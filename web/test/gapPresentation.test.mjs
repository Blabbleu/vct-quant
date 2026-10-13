import test from "node:test";
import assert from "node:assert/strict";
import { gapPresentation } from "../src/lib/gapPresentation.ts";

test("wide live-like quote preserves delta without an edge classification", () => {
  const result = gapPresentation(0.382203, 0.5, 0.9);
  assert.equal(result.kind, "wide");
  assert.ok(Math.abs(result.gapPoints - -11.7797) < 1e-9);
  assert.equal(result.kind === "wide", true);
});

test("spread at the threshold remains trusted", () => {
  assert.deepEqual(gapPresentation(0.62, 0.5, 0.1), { kind: "big", gapPoints: 12 });
});

test("spread above the threshold is wide", () => {
  assert.equal(gapPresentation(0.62, 0.5, 0.100001).kind, "wide");
});

test("trusted gaps classify BIG GAP and AGREE at their boundaries", () => {
  assert.equal(gapPresentation(0.61, 0.5, 0.1).kind, "big");
  assert.equal(gapPresentation(0.509, 0.5, 0.1).kind, "agree");
});

test("missing market has the no-price state", () => {
  assert.deepEqual(gapPresentation(0.6, null, 0.9), { kind: "no-price" });
});
