import test from "node:test";
import assert from "node:assert/strict";
import { recordView } from "../src/lib/record.ts";

// Shape copied from the live /api/results payload.
const data = {
  rows: [], verified: 22, unverified: 0, note: "",
  by_tier: {
    "1": { verified: 20, favourite_won: 16, log_loss: 0.5195801345358892 },
    "3": { verified: 2, favourite_won: 2, log_loss: 0.6142855913890192 },
  },
};

test("reads the Tier 1 record from the string-keyed by_tier map", () => {
  const v = recordView({ data, error: null, loading: false });
  assert.equal(v.kind, "ready");
  assert.equal(v.tier.verified, 20);
  assert.equal(v.line, "Model picked the winner in 16 of 20 graded Tier 1 matches.");
});

test("an in-flight /api/results fetch is loading, not 'no graded matches'", () => {
  assert.equal(recordView({ data: null, error: null, loading: true }).kind, "loading");
});

test("a failed fetch is an error, not an empty record", () => {
  const v = recordView({ data: null, error: "/api/results answered 500", loading: false });
  assert.deepEqual(v, { kind: "error", detail: "/api/results answered 500" });
});

test("empty only when the tier truly has no verified rows", () => {
  assert.equal(recordView({ data: { ...data, by_tier: {} }, error: null, loading: false }).kind, "empty");
  assert.equal(recordView({ data: { ...data, by_tier: { "1": { verified: 0, favourite_won: 0, log_loss: 0 } } }, error: null, loading: false }).kind, "empty");
});
