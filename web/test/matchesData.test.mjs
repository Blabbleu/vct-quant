import test from "node:test";
import assert from "node:assert/strict";
import {
  stageParts, stageShort, stageLabel, formatCountdown, groupByDay, eventContext,
  pickHit, justFinished, biggestMisses, stageTimeline,
} from "../src/lib/matchesData.ts";

const fx = (id, start, series = "Playoffs: Upper Quarterfinals", extra = {}) => ({
  match_id: id, start, event: "Valorant Champions 2026", series, best_of: 3, ...extra,
});
const row = (id, at, pA, winner, ll = 0.5) => ({
  match_id: id, scheduled_at: at, p_a: pA, log_loss: ll,
  result: { status: "verified", winner, maps_a: 2, maps_b: 0 },
});

test("stage names are split and shortened so the card header never truncates them", () => {
  assert.deepEqual(stageParts("Playoffs: Upper Quarterfinals"), { phase: "Playoffs", stage: "Upper Quarterfinals" });
  assert.deepEqual(stageParts("Grand Final"), { phase: null, stage: "Grand Final" });
  assert.equal(stageShort("Playoffs: Upper Quarterfinals"), "Upper QF");
  assert.equal(stageShort("Playoffs: Lower Round 1"), "Lower R1");
  assert.equal(stageShort("Playoffs: Upper Semifinals"), "Upper SF");
  assert.equal(stageLabel({ series: "Playoffs: Upper Quarterfinals", best_of: 3 }), "Upper QF \u00B7 Bo3");
  assert.equal(stageLabel({ series: "Playoffs: Grand Final", best_of: null }), "Grand Final");
});

test("countdown formats days, hours and minutes, and reads LIVE at or after kick-off", () => {
  const H = 3_600_000;
  assert.equal(formatCountdown(2 * 24 * H + 14 * H + 3 * 60_000 + 59_000), "2D 14H 03M");
  assert.equal(formatCountdown(5 * H + 7 * 60_000 + 9_000), "05H 07M 09S");
  assert.equal(formatCountdown(61_000), "01M 01S");
  assert.equal(formatCountdown(0), "LIVE");
  assert.equal(formatCountdown(-5), "LIVE");
  assert.equal(formatCountdown(NaN), "LIVE");
});

test("groupByDay keeps order and groups on the formatted day label", () => {
  const items = [fx(1, "2026-10-07T09:00:00Z"), fx(2, "2026-10-07T12:00:00Z"), fx(3, "2026-10-08T09:00:00Z")];
  const g = groupByDay(items, d => d.toISOString().slice(0, 10));
  assert.deepEqual(g.map(x => [x.label, x.items.map(i => i.match_id)]), [["2026-10-07", [1, 2]], ["2026-10-08", [3]]]);
});

test("eventContext reports the soonest event, its stages, size and days", () => {
  const items = [
    fx(3, "2026-10-08T09:00:00Z"), fx(1, "2026-10-07T09:00:00Z"), fx(2, "2026-10-07T12:00:00Z"),
    fx(9, "2026-10-09T09:00:00Z", "Playoffs: Lower Round 1", { event: "Other" }),
  ];
  const c = eventContext(items, d => d.toISOString().slice(0, 10));
  assert.equal(c.next.match_id, 1);
  assert.equal(c.event, "Valorant Champions 2026");
  assert.equal(c.phase, "Playoffs");
  assert.deepEqual(c.stages, ["Upper Quarterfinals"]);
  assert.equal(c.matches, 3);
  assert.equal(c.days, 2);
  assert.deepEqual(c.bestOf, [3]);
  assert.equal(eventContext([], () => ""), null);
});

test("pickHit compares the model's side (>= 50%) with the verified winner", () => {
  assert.equal(pickHit(row(1, "x", 0.6, "a")), true);
  assert.equal(pickHit(row(1, "x", 0.6, "b")), false);
  assert.equal(pickHit(row(1, "x", 0.4, "b")), true);
  assert.equal(pickHit({ p_a: 0.6, result: { status: "unverified", winner: null } }), null);
});

test("justFinished takes the last 48h of results, within [min, max], and an even count", () => {
  const rows = [
    row(1, "2026-10-04T11:00:00Z", 0.6, "a"), row(2, "2026-10-04T09:00:00Z", 0.6, "a"),
    row(3, "2026-10-03T11:00:00Z", 0.6, "a"), row(4, "2026-10-03T09:00:00Z", 0.6, "a"),
    row(5, "2026-10-02T12:00:00Z", 0.6, "a"), row(6, "2026-10-01T12:00:00Z", 0.6, "a"),
    row(7, "2026-09-30T12:00:00Z", 0.6, "a"), row(8, "2026-09-29T12:00:00Z", 0.6, "a"),
  ];
  // 5 rows fall inside 48h of the newest (47h for #5); the count is then rounded up to an even 6.
  assert.deepEqual(justFinished(rows).map(r => r.match_id), [1, 2, 3, 4, 5, 6]);
  assert.deepEqual(justFinished(rows, { hours: 24 }).map(r => r.match_id), [1, 2, 3, 4]);
  assert.deepEqual(justFinished(rows, { hours: 200, min: 4, max: 6 }).map(r => r.match_id), [1, 2, 3, 4, 5, 6]);
  assert.deepEqual(justFinished(rows.slice(0, 3), { min: 4 }).map(r => r.match_id), [1, 2, 3]);
  assert.deepEqual(justFinished([]), []);
  const odd = justFinished(rows, { hours: 60, min: 3, max: 7 });
  assert.equal(odd.length, 6);
  // nothing left to pad with: an odd list stays odd rather than inventing a row
  assert.equal(justFinished(rows.slice(0, 5), { hours: 60, min: 3, max: 7 }).length, 5);
});

test("biggestMisses lists only wrong picks, worst log loss first", () => {
  const rows = [row(1, "2026-10-04T00:00:00Z", 0.7, "b", 1.2), row(2, "2026-10-03T00:00:00Z", 0.7, "a", 0.3), row(3, "2026-10-02T00:00:00Z", 0.6, "b", 0.9)];
  assert.deepEqual(biggestMisses(rows, 5).map(r => r.match_id), [1, 3]);
});

test("stageTimeline orders the feed's stages by date, merges matches and marks current/past", () => {
  const po = {
    opening: [
      { match_id: 1, stage: "Upper Quarterfinals", start: "2026-10-07T09:00:00+00:00", best_of: 3 },
      { match_id: 2, stage: "Upper Quarterfinals", start: "2026-10-08T09:00:00+00:00", best_of: 3 },
    ],
    schedule: [{ match_id: 3, stage: "Grand Final", start: "2026-10-18T06:00:00+00:00", best_of: 5 }],
  };
  const t = stageTimeline(po, "Playoffs: Upper Quarterfinals", Date.parse("2026-10-09T00:00:00Z"));
  assert.deepEqual(t.map(s => [s.stage, s.matches, s.current, s.past]), [["Upper Quarterfinals", 2, true, true], ["Grand Final", 1, false, false]]);
  assert.deepEqual(stageTimeline(undefined, null), []);
});
