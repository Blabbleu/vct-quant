# Champions group qualification odds

`src/vct_quant/group_odds.py`, served inside `/api/champions/2766` as a
`qualification` block per group and shown on `/champions/2766`.

## What it is

A derivation of the primary forecast, not a new model. For each four-team
double-elimination group (opening ×2 → winners' / elimination → decider):

* played series come from the verified `champions_status` results (exact IDs,
  Bo3 score, winner flags); a result that does not match its bracket slot
  raises rather than routing;
* every remaining series is an independent draw with
  `expected_score(elo_a, elo_b)` from the same Tier-1/Tier-2 replay
  `predict_upcoming` uses (`match_sequence(tiers=(1, 2))`, `margin_signal`,
  `elo_k`), so each pairwise probability equals the fixture board's number;
* the ≤ 2⁵ paths are enumerated exactly (no Monte Carlo noise). Outputs per
  team: `p_qualify` (sums to 2 per group) and `p_first` (winners'-match
  victor, sums to 1).

Verified on the 2026-09-26 dev snapshot: the pairwise function reproduced the
cached `p_team_a_win` of all 8 known-pair fixtures with difference 0.0;
replay takes ~0.2 s.

## Limits

* Ratings are held fixed for the rest of the group. Real Elo moves after each
  result, so this slightly understates path dependence. Correct for the
  first-order question "how likely is each team to get out", not a claim of
  calibration beyond the primary forecast's own.
* Groups with an unverified completed row, or an entrant with no rated
  official history, are **withheld**, not guessed.
* No title odds. Playoff seeding and lower-bracket crossover are not
  source-verified until the Oct 4 draw (see `docs/champions-2026-bracket.md`).
* Primary forecasts are untouched: this reads ratings, emits nothing into the
  fixture cache or prediction log.

## Snapshot reading (2026-09-26 07:30 UTC, before B openers)

* A: 100 Thieves 73%, T1 67%, FUT 48%, JD Gaming 12%
* B: Global Esports 66%, LOUD 66%, Vitality 43%, EDG 25%
* C (G2, PRX won openers): Paper Rex 82%, G2 80%, Liquid 30%, TYLOO 8%
* D (KC, NRG won openers): NRG 85%, Karmine Corp 69%, NS RedForce 37%, XLG 10%
