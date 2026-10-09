import test from "node:test";
import assert from "node:assert/strict";
import { openingSectionCopy } from "../src/lib/championsCopy.ts";

const opening = Array.from({ length: 4 }, (_, index) => ({
  match_id: 754730 + index,
  sides: [{ team_id: index * 2 + 1 }, { team_id: index * 2 + 2 }],
  result: null,
}));

function withResults(count) {
  return opening.map((match, index) => index < count
    ? { ...match, result: { winner_team_id: match.sides[0].team_id, scores: [2, 1] } }
    : match);
}

test("opening section copy reports no played matches", () => {
  assert.deepEqual(openingSectionCopy(withResults(0), []), {
    chip: "DRAWN · ROUTING TBD", played: 0, total: 4,
  });
});

test("opening section copy reports partial results", () => {
  assert.deepEqual(openingSectionCopy(withResults(2), []), {
    chip: "2/4 PLAYED", played: 2, total: 4,
  });
});

test("opening section copy reports a complete set of results", () => {
  assert.deepEqual(openingSectionCopy(withResults(4), []), {
    chip: "COMPLETE", played: 4, total: 4,
  });
});

test("an unverified result is not counted as played", () => {
  assert.deepEqual(openingSectionCopy(withResults(2), [754730]), {
    chip: "1/4 PLAYED", played: 1, total: 4,
  });
});
