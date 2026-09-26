# Game Changers K retune (protocol frozen 2026-09-26, before scoring 2025-26)

## Why

Game Changers (tier 3) is its own Elo rating pool (`match_sequence(tiers=(3,))`),
and its K is `features.build.GC_K = 48.0`, a placeholder copied from Tier 1
("Placeholder until scripts/benchmark_gc.py retunes it"). CLAUDE.md: retune K
whenever the training signal or pool changes. GC forecasts are published on the
desk (GC fixtures in `upcoming_tier1.parquet`, `/results`, the ops panel), so a
mistuned K costs published accuracy. `scripts/benchmark_gc.py` is left untouched
(its TODO block is the owner's exercise); this lab lives in
`scripts/gc_k_lab.py`.

## Protocol (fixed before the test years are scored)

* Data: production GC sequence, `match_sequence(tiers=(3,))` with the current
  default flags (SKIP_UNSCORED_FORFEITS off), margin signal
  `maps_a / (maps_a + maps_b)` exactly as production. One continuous replay
  from the first GC match; K is constant across the replay.
* Scored rows: `score_a != 0.5` (draws / 0-0 forfeits carry no binary label).
* Tune: scored matches with `year <= 2024`. Grid
  K in {16, 24, 32, 48, 64, 96, 128, 192, 256}. Pick the K with the lowest mean
  log loss. If the pick sits on a grid edge, extend the grid on the tune years
  only (x1.5 steps) until it does not, still before looking at 2025-26.
* Test: scored matches with `year >= 2025`, scored ONCE at the tuned K against
  production K = 48. Paired per-match log-loss difference, t-statistic.
* Decision rule: propose the tuned K as the new GC_K (owner approval, it changes
  published GC probabilities) iff the tuned K != 48 **and** paired t >= +2.0 on
  2025-26. Otherwise GC_K stays 48 and the result is recorded as negative.
* Not decisive, reported only: per-year test split (2025, 2026), Brier,
  calibration table at both K, and the same comparison with
  SKIP_UNSCORED_FORFEITS on (A72 pending), to show the two changes do not
  interact.

Caveat declared up front: the forfeit-label audit (docs/forfeit-labels.md)
already scored GC 2025-26 at K = 48 for a different question. That did not
select K, so 2025-26 remains untouched for this parameter.

## Result

(filled in after the single test run; see below)
