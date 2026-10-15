import test from "node:test";
import assert from "node:assert/strict";
import {
  stageParts, stageShort, stageLabel, formatCountdown, groupByDay, eventContext, selectFixtures,
  pickHit, justFinished, biggestMisses, stageTimeline, nextPlayoffSeries, isPlayoffBracketComplete,
} from "../src/lib/matchesData.ts";

const fx = (id, start, series = "Playoffs: Upper Quarterfinals", extra = {}) => ({
  match_id: id, start, event: "Valorant Champions 2026", series, best_of: 3, ...extra,
});
const row = (id, at, pA, winner, ll = 0.5) => ({
  match_id: id, scheduled_at: at, p_a: pA, log_loss: ll,
  result: { status: "verified", winner, maps_a: 2, maps_b: 0 },
});

test("selection falls back to all when an event disappears from a refreshed slate", () => {
  const champions = [fx(1, "2026-10-07T09:00:00Z")];
  const selected = selectFixtures(champions, "Game Changers 2026 Americas LCQ");
  assert.equal(selected.event, "all");
  assert.deepEqual(selected.fixtures, champions);
});

test("selection recovers to all when the refreshed slate is empty", () => {
  assert.deepEqual(selectFixtures([], "Game Changers 2026 Americas LCQ"), { event: "all", fixtures: [] });
});

test("selection preserves an event that remains in the refreshed slate", () => {
  const champions = [fx(1, "2026-10-07T09:00:00Z"), fx(2, "2026-10-08T09:00:00Z", "Playoffs: Lower Round 1", { event: "Valorant Champions 2026" })];
  const gc = [fx(3, "2026-10-09T09:00:00Z", "Group Stage", { event: "Game Changers 2026 Americas LCQ" })];
  const selected = selectFixtures([...champions, ...gc], "Valorant Champions 2026");
  assert.equal(selected.event, "Valorant Champions 2026");
  assert.deepEqual(selected.fixtures, champions);
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

test("justFinished uses the current 48-hour window without padding", () => {
  const now = Date.parse("2026-10-15T12:00:00Z");
  const rows = [
    row(1, "2026-10-14T11:00:00Z", 0.6, "a"), row(2, "2026-10-14T09:00:00Z", 0.6, "a"),
    row(3, "2026-10-11T11:00:00Z", 0.6, "a"), row(4, "2026-10-11T09:00:00Z", 0.6, "a"),
  ];
  assert.deepEqual(justFinished(rows, { now }).map(r => r.match_id), [1, 2]);
  assert.deepEqual(justFinished(rows, { now: now + 3 * 86_400_000 }), []);
  assert.deepEqual(justFinished([]), []);
  assert.equal(justFinished([rows[0]], { now }).length, 1);
});

test("justFinished includes the exact 48-hour boundary and excludes one millisecond older", () => {
  const now = Date.parse("2026-10-15T12:00:00Z");
  const rows = [
    row(1, "2026-10-15T11:59:00Z", 0.6, "a"),
    row(2, "2026-10-13T12:00:00Z", 0.6, "a"),
    row(3, "2026-10-13T11:59:59.999Z", 0.6, "a"),
  ];
  assert.deepEqual(justFinished(rows, { now }).map(r => r.match_id), [1, 2]);
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

test("stageTimeline includes completed openers with a played date", () => {
  const po = {
    opening: [{ match_id: 1, stage: "Upper Quarterfinals", start: null, played_on: "2026-10-07", best_of: 3 }],
    schedule: [{ match_id: 2, stage: "Grand Final", start: null, best_of: 5 }],
  };
  const t = stageTimeline(po, null, Date.parse("2026-10-08T00:00:00Z"));
  assert.deepEqual(t.map(s => [s.stage, s.start, s.end, s.matches, s.past]), [
    ["Upper Quarterfinals", "2026-10-07", "2026-10-07", 1, true],
  ]);
});

const side = (name, p_win = 0.5) => ({ name, p_win });
const playoffSlot = (match_id, stage, start, sides, extra = {}) => ({
  match_id, stage, start, sides, best_of: 3, ...extra,
});

test("nextPlayoffSeries filters played, unverified and unnamed slots, then sorts and limits", () => {
  const po = {
    opening: [
      playoffSlot(10, "Upper Quarterfinals", null, [side("A"), side("B")], { result: { winner_team_id: 1 } }),
    ],
    schedule: [
      playoffSlot(4, "Upper Semifinals", "2026-10-10T09:00:00Z", [side("C"), side("D")]),
      playoffSlot(3, "Lower Round 1", "2026-10-09T12:00:00Z", [side("E"), side("F")]),
      playoffSlot(2, "Lower Round 1", "2026-10-09T12:00:00Z", [side("G"), side("H")]),
      playoffSlot(1, "Lower Round 1", "2026-10-09T09:00:00Z", [side("I"), side("J")], { result: null }),
      playoffSlot(5, "Lower Round 1", "2026-10-09T08:00:00Z", [side("K"), side("")]),
      { match_id: 6, stage: "Lower Round 1", start: "2026-10-09T07:00:00Z", sides: null },
    ],
    unverified_match_ids: [1],
  };
  assert.deepEqual(nextPlayoffSeries(po, 3).map(s => s.match_id), [2, 3, 4]);
  assert.deepEqual(nextPlayoffSeries(po).map(s => s.match_id), [2, 3, 4]);
});

test("nextPlayoffSeries falls back to opening sorted as the pre-draw slate", () => {
  const po = {
    opening: [
      playoffSlot(8, "Upper Quarterfinals", null, [side("A"), side("B")]),
      playoffSlot(4, "Upper Quarterfinals", "2026-10-07T12:00:00Z", [side("C"), side("D")]),
      playoffSlot(2, "Upper Quarterfinals", "2026-10-07T09:00:00Z", [side("E"), side("F")]),
    ],
    schedule: [playoffSlot(1, "Lower Round 1", "2026-10-09T09:00:00Z", null)],
  };
  assert.deepEqual(nextPlayoffSeries(po).map(s => s.match_id), [2, 4, 8]);
  assert.deepEqual(nextPlayoffSeries(po, 2).map(s => s.match_id), [2, 4]);
});

test("opening fallback excludes completed, unnamed and unverified slots", () => {
  const po = { opening: [
    playoffSlot(1, "Upper Quarterfinals", "2026-10-07T08:00:00Z", [side("Done A"), side("Done B")], { result: { winner_team_id: 1 } }),
    playoffSlot(2, "Upper Quarterfinals", "2026-10-07T09:00:00Z", [side("A"), side("B")]),
    playoffSlot(3, "Upper Quarterfinals", "2026-10-07T10:00:00Z", [side("C"), side("D")]),
    playoffSlot(4, "Upper Quarterfinals", "2026-10-07T11:00:00Z", [side("TBD"), side("")]),
    playoffSlot(5, "Upper Quarterfinals", "2026-10-07T12:00:00Z", [side("E"), side("F")]),
  ], schedule: [], unverified_match_ids: [5] };
  assert.deepEqual(nextPlayoffSeries(po, 1).map(s => s.match_id), [2]);
  assert.deepEqual(nextPlayoffSeries(po).map(s => s.match_id), [2, 3]);
});

test("completed bracket needs opening and schedule results including a verified Grand Final", () => {
  const opening = Array.from({ length: 4 }, (_, i) => playoffSlot(i + 1, "Upper Quarterfinals", null, [side("A"), side("B")], { result: { winner_team_id: 1 } }));
  const schedule = ["Upper Semifinals", "Lower Semifinals", "Final", "Grand Final"].map((stage, i) => playoffSlot(i + 5, stage, null, null, { result: { winner_team_id: 1 } }));
  const complete = { opening, schedule };
  assert.deepEqual(nextPlayoffSeries(complete), []);
  assert.equal(isPlayoffBracketComplete(complete), true);
  assert.equal(isPlayoffBracketComplete({ opening: [], schedule: [] }), false);
  assert.equal(isPlayoffBracketComplete({ opening, schedule: [] }), false);
  assert.equal(isPlayoffBracketComplete({ opening, schedule: schedule.map((s, i) => i === 3 ? { ...s, result: null } : s) }), false);
  assert.equal(isPlayoffBracketComplete({ opening, schedule, unverified_match_ids: [8] }), false);
});
