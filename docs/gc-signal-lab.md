# Game Changers signal / newcomer lab (protocol frozen 2026-09-26, before scoring 2025-26)

Follow-up to `docs/gc-k-retune.md` (A73 proposes GC_K 48 -> 192). That retune
left two open questions: is the margin (map-share) signal right for the GC
pool, and do newcomers need special handling (GC has many one-off
open-qualifier teams; at K = 192 the < 40% buckets still ran hot for the
underdog). This lab asks both with **one** pre-registered selection and
**one** test, so the test years are not spent on a menu of comparisons.

## Protocol (fixed before any 2025-26 number for these variants is computed)

Data: production GC sequence `match_sequence(tiers=(3,))`, default flags
(SKIP_UNSCORED_FORFEITS off), one continuous replay from the first GC match.
Scored rows: `score_a != 0.5`. Tune: scored rows with `year <= 2024`. Test:
scored rows with `year >= 2025`.

Families (every configuration uses the 400-point logistic scale):

* **M, margin** (production signal): `maps_a / (maps_a + maps_b)`,
  K in {16, 24, 32, 48, 64, 96, 128, 192, 256, 384, 512}.
* **B, binary**: signal = `score_a` (1 / 0), same K grid.
* **N, newcomer seed**: margin signal; a team's first rating is `r0` instead
  of 1500, r0 in {1500, 1450, 1400, 1350, 1300, 1250, 1200},
  K in {64, 96, 128, 192, 256}.
* **P, provisional K**: margin signal; each side updates with its own K,
  `K * m` while that side has played fewer than 10 prior GC matches, else `K`,
  m in {1.5, 2, 3}, K in {64, 96, 128, 192, 256}. (Per-side K: the update is
  not zero-sum for provisional teams, as in USCF provisional ratings.)

Selection: the single configuration with the lowest mean tune log loss across
all families. The reference is the A73 candidate, family M at K = 192 (it is
the tune-years winner of family M by construction of gc-k-retune.md).

* If the selected configuration **is** M / K = 192: negative result, the test
  years are not scored for any variant.
* Otherwise score the selected configuration **once** on 2025-26 against the
  A73 candidate (M, K = 192) and, for context, production (M, K = 48).
  Paired per-match log-loss difference, t-statistic.

Decision rule: propose the selected configuration to the owner (it would
replace A73's change; it changes published GC probabilities) iff paired
t >= +2.0 **against M / K = 192** on 2025-26. Otherwise A73 stands as is and
this is recorded as negative.

Reported only, not decisive: per-year split (2025, 2026), Brier, the
calibration table, the tune loss of the best configuration in each family.

Caveat declared up front: 2025-26 GC was scored at K = 48 and K = 192 by
gc-k-retune.md and at K = 48 by forfeit-labels.md. Neither selected anything
in this lab's families, but the test years are no longer pristine for GC;
treat a borderline result accordingly.

### Amendment 1 (after the first tune run, before any test-year scoring)

Family N as written is degenerate: when *every* team's first rating is r0,
the whole pool is translated by r0 - 1500 and Elo is translation-invariant.
The first tune run confirmed it (N losses identical to M at every K, to 6
decimals). Replaced by **N'**: a team entering the pool is seeded at the
**current mean rating of already-rated teams + delta**, delta in
{-50, -100, -150, -200, -250, -300}, K in {64, 96, 128, 192, 256}. With
delta = 0 this is exactly production (zero-sum updates keep the mean at 1500).
Selection is re-run over all families on the tune years; nothing else changes.
The test years remain unscored for every variant in this lab. (Side effect,
noted: family P now also seeds newcomers at the current pool mean with
delta = 0; P's per-side K makes updates non-zero-sum, so its mean drifts from
1500. P tune losses moved in the 4th decimal; its best stays K=128, m=1.5.)

## Result

Run 2026-09-26 on the dev DB snapshot (11,688 GC matches).

Tune (years <= 2024, n = 5,779), best configuration per family:

* M margin: K = 192, 0.592724 (the A73 reference)
* B binary: K = 128, 0.610010 (binary loses to margin at every K >= 48, as in Tier 1)
* N' newcomer seed at pool mean + delta: K = 192, delta = -100, **0.587593**
  (interior in both K and delta; -50 0.588363, -150 0.590391)
* P provisional K: K = 128, m = 1.5, 0.592819 (ties M; m >= 2 worse)

Selected N' K=192 delta=-100 and scored it once on 2025-26 (n = 5,664):

* vs A73 reference (M, K=192): 0.603787 -> 0.603224, **paired t = +0.72**.
  Brier 0.20988 -> 0.20941.
* By year: 2025 (n = 3,298) t = +2.78; **2026 (n = 2,366) t = -2.49**
  (0.60627 -> 0.60907).
* vs production K=48: t = +4.99 (the K change carries the gain).

**Decision under the frozen rule: negative. A73 (margin, K=192, newcomers at
1500) stands.** The newcomer-seed gain on the tune years did not transfer, and
it reverses in 2026.

Finding for follow-up (descriptive, not selected on): in every GC year the
stored side 1 wins about 5 points more often than Elo predicts (2022-26:
0.599/0.587/0.612/0.597/0.613 vs mean p 0.536-0.557; the calibration table
above is hot for side 1 in every bucket below 70%). The stored order matches
the vlr.gg URL slug for all 10,009 slug-matchable GC rows, and all 6 logged
pre-match orientations match canonical, so side order looks like pre-match
information (bracket seeding). Tier 1 shows no such gap after 2022. Because
2025-26 side-1 rates were looked at here, a side-advantage test on 2025-26
is not clean; see docs/gc-side-advantage.md.
