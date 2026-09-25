# Completed/TBD placeholder sensitivity (read-only)

**Decision rule frozen before scoring retrospective 2025–26 Tier-1 rows.**
Compare the current Elo replay with a replay excluding exactly match IDs 10802
(Kaggle) and 97028 (event), which are labeled completed but have a TBD side.
Do not retune K or any other parameter. Score only the same genuinely resolved
Tier-1 match IDs in 2025–26, after both excluded IDs, with known binary winners.
Report n, paired per-match log-loss difference (current minus exclusion), paired
t, and maximum probability delta. Positive t favors exclusion. This is a
retrospective **data-correction diagnostic**, not an untouched holdout or a
promotion test: years through 2026 have already informed model selection. An
improvement is not grounds to change primary forecasts without a separate
approval. A worsening also cannot make a fabricated result valid; reconcile the
upstream match identities before proposing any correction. Never edit the live
DB or the live prediction log for this audit.

The fixed exclusion set comes from `scripts/placeholder_audit.py`; it is not
chosen by the comparison's score. Current additive DB state can differ from a
clean rebuild, so only claim a counterfactual on this snapshot. **A TBD name
alone does not prove a match was unplayed**; the source reconciliation below
supersedes the provisional assumption that both rows were invalid.

## Snapshot result (2026-09-25)

`python -m scripts.placeholder_scoring` on the refreshed dev DB snapshot:
2025–26 n=1,096 resolved Tier-1 matches, current log loss 0.658685279,
excluding both 0.658685307, paired t=−0.076 (positive favors exclusion),
max absolute probability delta 0.000025730. Exclusion is fractionally worse;
this is far below meaningful forecast resolution. **This joint exclusion is not
an appropriate data repair**: ID 10802 has a played-map result with an anonymous
team name; ID 97028 is a separate winner-ingestion defect. Do not edit the live
DB; a primary correction requires a separate source-specific review and approval.

## Source reconciliation (read-only, 2026-09-25)

- [Match 10802](https://www.vlr.gg/10802):
  `data/raw/kaggle/all_ids/all_matches_games_ids.csv` maps `TBD vs HONK`
  (2021 Europe Stage 1 Challengers 2, open-qualifier round of 256) to game
  18745. `data/raw/kaggle/vct_2021/matches/scores.csv` says HONK won 13–10;
  `maps_scores.csv` has the same Ascent round score and `overview.csv` records
  player stats for both sides. The DB has one Ascent map, a 0–1 series and
  HONK as winner. This is a **played match under an unresolved/anonymous team
  name**, not an unplayed placeholder. Excluding it would discard an observed
  HONK win; recovering the TBD side's identity is a separate problem. The
  event replay's broad TBD-name filter does not remove this Kaggle-owned row
  from the current additive DB or a Kaggle-first rebuild.
- [Match 97028](https://www.vlr.gg/97028): archived event response
  `data/raw/vlrgg/event_matches_800_20260918T205532Z.json` reports IlluZion
  `0` versus TBD `–`, **with IlluZion marked winner**. Archived detail
  `data/raw/vlrgg/match_details_97028_20260924T170852Z.json` says
  `forfeited by TBD`, IlluZion `is_winner=true`, and no maps. The existing
  additive DB instead has IlluZion `is_winner=false`, TBD `is_winner=true`,
  with a missing TBD score. The event loader inferred winner using `score_a >
  score_b`; `0 > NaN` became false, then its inverse marked TBD the winner.
  The current replay filter skips this missing-score row on a fresh event
  load, but cannot remove the already-loaded DB row. A safe corrective policy
  must explicitly handle scoreless forfeits and existing rows, not simply
  delete every TBD-named result.

These are two different provenance cases. The combined loss comparison above
measures sensitivity, **not** whether either source result is true or whether
one blanket exclusion policy is suitable. No primary forecast or DB write was
made.
