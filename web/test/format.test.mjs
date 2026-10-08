import test from "node:test";
import assert from "node:assert/strict";
import { relative, utc, utcShort } from "../src/lib/format.ts";

test("UTC formatters treat zoneless ISO timestamps as UTC", () => {
  const zoneless = "2026-10-08T09:00:00";
  const explicitUtc = `${zoneless}Z`;
  assert.equal(utc(zoneless), utc(explicitUtc));
  assert.equal(utcShort(zoneless), utcShort(explicitUtc));
  assert.equal(utcShort(zoneless), "Oct 8, 09:00 UTC");
});

test("UTC formatters use their null fallback for invalid input", () => {
  assert.equal(utc("not a date"), "an unknown time");
  assert.equal(utcShort("not a date"), "Time TBD");
});

test("relative times rounded to zero minutes say now", () => {
  const now = Date.parse("2026-10-08T09:00:00Z");
  assert.equal(relative("2026-10-08T08:59:40Z", now), "now");
  assert.equal(relative("2026-10-08T09:00:00Z", now), "now");
});
