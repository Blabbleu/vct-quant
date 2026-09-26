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

Run 2026-09-26 on the dev DB snapshot (11,688 GC matches),
`python scripts/gc_k_lab.py tune`, then `test --k 192`.

Tune (years <= 2024, n = 5,779 scored), mean log loss:

| K | 16 | 24 | 32 | 48 | 64 | 96 | 128 | **192** | 256 |
|---|---|---|---|---|---|---|---|---|---|
| loss | .6635 | .6534 | .6450 | .6318 | .6218 | .6081 | .5998 | **.5927** | .5945 |

Pick K = 192 (interior, no grid extension needed).

Test (2025-26, n = 5,664 scored, scored once):

* K = 48 **0.622389** -> K = 192 **0.603787**, paired **t = +5.09**;
  Brier 0.21747 -> 0.20988.
* 2025: n = 3,298, 0.6250 -> 0.6020, t = +5.09. 2026: n = 2,366,
  0.6187 -> 0.6063, t = +2.05.
* With SKIP_UNSCORED_FORFEITS on (A72): n = 5,652, 0.622556 -> 0.603818,
  t = +5.09. The two changes do not interact.

**Decision under the frozen rule: propose GC_K = 192** (owner approval; it
changes published GC probabilities and the desk's GC backtest block).

Calibration on the test years: K = 48 is badly *under*confident (60-70%
bucket won 77%, 80-90% won 96%): a K of 48 cannot keep up with a pool whose
strength spread is wide and whose one-off open-qualifier teams lose repeatedly.
At K = 192 the 60-100% buckets are within 5 points (70-80: .748 vs .744,
90-100: .951 vs .947); the low buckets (< 40%) still run hot for the
underdog (10-20% predicted, 28.5% won).

Descriptive neighbours (NOT a re-selection; the pick stays 192): on the test
years K = 96 scores 0.6056 (t = +11.44), K = 128 0.6017 (t = +9.16),
K = 256 0.6148 (t = +1.53, 2026 t = -0.16). The optimum on later data
has drifted a little lower than on the tune years and the loss rises faster
above 192 than below, so K = 192 sits near the steep edge. Every K in 96-192
beats 48 in both test years. If the owner prefers a margin of safety, 128 is
the conservative alternative, but choosing it now would be selection on the
test period; the pre-registered proposal is 192.

Not tested here: a margin-free (binary) GC signal, per-season decay, and
GC shadows (ensemble/shrink are Tier-1-only by design).
