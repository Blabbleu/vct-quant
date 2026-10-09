import test from "node:test";
import assert from "node:assert/strict";
import { bracketKickoff, bracketRoundSub, localShort, playedDate, relative, stageSpan, utc, utcShort } from "../src/lib/format.ts";
import { execFileSync } from "node:child_process";

test("UTC formatters treat zoneless ISO timestamps as UTC", () => {
  const zoneless = "2026-10-08T09:00:00";
  const explicitUtc = `${zoneless}Z`;
  assert.equal(utc(zoneless), utc(explicitUtc));
  assert.equal(utcShort(zoneless), utcShort(explicitUtc));
  assert.equal(utcShort(zoneless), "Oct 8, 09:00 UTC");
});

test("played date is stable across viewer time zones", () => {
  const script = `import { playedDate } from './src/lib/format.ts'; console.log(playedDate('2026-10-08'));`;
  const inZone = (TZ) => execFileSync(process.execPath, ["--experimental-strip-types", "--input-type=module", "--eval", script], {
    cwd: new URL("..", import.meta.url), env: { ...process.env, TZ }, encoding: "utf8",
  }).trim();
  assert.equal(playedDate("2026-10-08"), "Played Oct 8");
  assert.equal(inZone("America/New_York"), "Played Oct 8");
});

test("UTC formatters use their null fallback for invalid input", () => {
  assert.equal(utc("not a date"), "an unknown time");
  assert.equal(utcShort("not a date"), "Time TBD");
});

test("bracket kickoffs and round days stay UTC across viewer time zones", () => {
  const script = `import { bracketKickoff, bracketRoundSub } from './src/lib/format.ts';
const starts = ['2026-10-08T23:30:00', '2026-10-08T23:30:00Z', '2026-10-09T01:30:00+02:00'];
console.log(JSON.stringify({ kickoffs: starts.map(bracketKickoff), rounds: starts.map(s => bracketRoundSub([s], [3])) }));`;
  const inZone = (TZ) => JSON.parse(execFileSync(process.execPath, ["--experimental-strip-types", "--input-type=module", "--eval", script], {
    cwd: new URL("..", import.meta.url), env: { ...process.env, TZ }, encoding: "utf8",
  }));
  const utcOutput = inZone("UTC");
  const nyOutput = inZone("America/New_York");
  assert.deepEqual(nyOutput, utcOutput);
  assert.deepEqual(utcOutput.kickoffs, ["Oct 8 · 23:30", "Oct 8 · 23:30", "Oct 8 · 23:30"]);
  assert.deepEqual(utcOutput.rounds, ["Oct 8 · Bo3", "Oct 8 · Bo3", "Oct 8 · Bo3"]);
});

test("stage spans stay UTC across viewer time zones", () => {
  const script = `import { stageSpan } from './src/lib/format.ts';
console.log(JSON.stringify([
  stageSpan('2026-10-07', '2026-10-08'),
  stageSpan('2026-10-09T00:30:00Z', '2026-10-09T23:00:00Z'),
  stageSpan('2026-09-30', '2026-10-02'),
  stageSpan(null, null),
]));`;
  const inZone = (TZ) => JSON.parse(execFileSync(process.execPath, ["--experimental-strip-types", "--input-type=module", "--eval", script], {
    cwd: new URL("..", import.meta.url), env: { ...process.env, TZ }, encoding: "utf8",
  }));
  const utcOutput = inZone("UTC");
  assert.deepEqual(inZone("America/New_York"), utcOutput);
  assert.deepEqual(utcOutput, ["Oct 7–8", "Oct 9", "Sep 30–Oct 2", ""]);
});

test("local short kickoffs follow the viewer time zone and parse zoneless UTC", () => {
  const script = `import { localShort } from './src/lib/format.ts';
console.log(JSON.stringify([
  localShort('2026-10-09T18:00:00Z'),
  localShort('2026-10-09T18:00:00'),
  localShort(null),
  localShort('not a date'),
]));`;
  const inZone = (TZ) => JSON.parse(execFileSync(process.execPath, ["--experimental-strip-types", "--input-type=module", "--eval", script], {
    cwd: new URL("..", import.meta.url), env: { ...process.env, TZ }, encoding: "utf8",
  }));
  const utcOutput = inZone("UTC");
  const nyOutput = inZone("America/New_York");
  assert.ok(utcOutput[0].includes("18:00"));
  assert.ok(utcOutput[1].includes("18:00"));
  assert.ok(nyOutput[0].includes("14:00") && nyOutput[0].includes("Oct 9"));
  assert.ok(nyOutput[1].includes("14:00") && nyOutput[1].includes("Oct 9"));
  assert.equal(utcOutput[2], "Time TBD");
  assert.equal(utcOutput[3], "Time TBD");
});

test("bracket malformed and null starts fall back or are ignored while retaining Bo labels", () => {
  assert.equal(bracketKickoff(null), "Time TBD");
  assert.equal(bracketKickoff("not a date"), "Time TBD");
  assert.equal(bracketRoundSub(["not a date", null], [3]), "Bo3");
});

test("relative times rounded to zero minutes say now", () => {
  const now = Date.parse("2026-10-08T09:00:00Z");
  assert.equal(relative("2026-10-08T08:59:40Z", now), "now");
  assert.equal(relative("2026-10-08T09:00:00Z", now), "now");
});
