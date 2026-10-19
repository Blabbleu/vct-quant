import test from "node:test";
import assert from "node:assert/strict";
import { isTrustedQuote } from "../src/lib/gapPresentation.ts";
import { liquid } from "../src/lib/format.ts";
import { gapPresentation } from "../src/lib/gapPresentation.ts";

test("trusted quote uses inclusive spread and volume boundaries", () => {
  assert.equal(isTrustedQuote(0.1, 1000), true);
  assert.equal(isTrustedQuote(0.1, 999), false);
  assert.equal(isTrustedQuote(0.1001, 1000), false);
  assert.equal(isTrustedQuote(null, 1000), false);
  assert.equal(isTrustedQuote(0.1, null), false);
  assert.equal(isTrustedQuote(0.1, undefined), false);
});

test("liquid delegates to the shared trusted quote rule", () => {
  assert.equal(liquid(0.1, 1000), true);
  assert.equal(liquid(0.1, 999), false);
  assert.equal(liquid(0.1001, 1000), false);
  assert.equal(liquid(null, 1000), false);
  assert.equal(liquid(0.1, null), false);
  assert.equal(liquid(0.1, undefined), false);
});

test("gap presentation uses the shared trusted quote rule", () => {
  assert.equal(gapPresentation(0.62, 0.5, 0.1, 999).kind, "untrusted");
  assert.equal(gapPresentation(0.62, 0.5, 0.1, 1000).kind, "big");
});
