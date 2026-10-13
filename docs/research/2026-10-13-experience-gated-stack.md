# Pre-match experience gate for the frozen stack and fast/slow shadow

## Pre-registration (written before scoring 2025 or 2026)

**Hypothesis and data.** A team with little prior Tier-1 experience may benefit from a different mix of the frozen three-input stack and the fixed fast/slow shadow than an experienced team. Reuse `stack_fastslow.load()` and its pre-match component forecasts. Replay the complete `match_sequence` in ascending match ID and, before updating either team's count for each Tier-1 fixture, record the smaller of their prior Tier-1 appearance counts. Every Tier-1 appearance increments the count after its fixture, regardless of outcome; Tier-2 fixtures do not. Match ID is the chronology key. Reject null, duplicate or unordered IDs and identical team IDs in a fixture. A reversed team-A/team-B orientation must leave the experience group unchanged and complement the forecast.

**Frozen fitting rule.** Eligible fitting rows are decisive Tier-1 matches in 2023–24. Fit the existing no-intercept three-input stack on those rows with `stack_ensemble.fit`: inputs are the logits of production Elo, round-share and lineup probabilities, mean log loss plus its existing `0.001/2` squared-distance penalty to `[1,0,0]`. Fit the prior four-input stack on the same rows with `stack_fastslow.fit_frozen`, for a fixed comparator only. Let `p3` and `pfs` be the three-input and fixed fast/slow probabilities. The gate uses the convex **logit** blend `sigmoid(w logit(p3) + (1-w) logit(pfs))`, with `0 ≤ w ≤ 1`. First fit one global `w0` on all fitting rows by mean binary log loss. Then fit a separate `w` for each group by minimizing its mean binary log loss plus `0.01/2 × (w-w0)^2`. The penalty is fixed now, before test scoring. Use bounded scalar optimization over `[0,1]`; evaluate both endpoints and the optimizer result and choose minimum objective, breaking objective ties within `1e-12` by proximity to `w0`, then by smaller `w`. The same tie policy applies to the global fit, using 0.5 as its proximity anchor. These are the only blend parameters.

The split threshold is the median of the fitting rows' minimum prior counts, using the ordinary midpoint median if needed. `count ≤ median` is low experience; `count > median` is high. No 2025 or 2026 label, count distribution, or metric can change the threshold, penalty or weights. Reject an empty training group.

**Alignment and evaluation.** Require one-to-one equality of match IDs between the loaded component frame and count replay, and preserve `stack_fastslow.load()`'s outcome, Elo and probability checks. Score only decisive Tier-1 rows in 2025 and 2026-to-date, separately, on identical IDs for production Elo, frozen three-input stack, fixed fast/slow, prior frozen four-input fit, and this gate. All probabilities are team-A oriented. Report exclusions, group sizes and per-group log losses. The primary metric is paired per-match log-loss difference `(Elo loss − gate loss)` and its paired t statistic. Secondary metrics are Brier, accuracy, ten-bin calibration and ECE, with bins `[0,.1), …, [.9,1]` and `p ≥ .5` predicting team A; ties at `.5` therefore predict team A. Compare all models on the same rows.

**Frozen decision rule.** WIN requires gate paired `t > +2` versus Elo and gate `ECE ≤ Elo ECE` in **both** test years. If both t values are positive but WIN fails, verdict is **NOT PROVEN**. Any nonpositive t gives **REJECTED**. Both test years have been previously consulted in related studies and are retrospective checks, not independent holdouts. Even WIN would not authorize production deployment.

## Results

Snapshot: copied database available on 2026-10-13. Full-sequence one-to-one match alignment and Elo parity checks passed through `stack_fastslow.load()`. The fit has 333 decisive Tier-1 matches in 2023 and 436 in 2024 (769 total). The training median minimum prior appearance count is **41**, so low is `≤ 41` and high is `> 41`; their training sizes are **389** and **380**. No decisive Tier-1 test row was excluded after alignment: 504 in 2025 and 618 in 2026. Non-decisive rows, Tier-2 matches, and years outside the fixed split are ineligible; other sequence rows still contribute to the prerequisite pre-match model replays, while only prior Tier-1 appearances contribute to the gate count. The existing component fallbacks handle absent map or lineup detail without dropping rows. The 2026 snapshot contains four more matches than an earlier three-input note.

Frozen three-input weights `[0.81958736309159, -0.08542947719469174, 0.12807082551261592]`; prior four-input comparator weights `[0.12208378558670421, -0.039917678301894854, 0.010050583396203489, 0.8705421166229297]`. Global training blend weight `w0 = 0.012156659004919627`; low-experience weight `0.49185936026968036`; high-experience weight `4.2300630066830894e-13` (effectively zero). The gate weights multiply the three-input logit; the complement multiplies fast/slow. Paired t uses per-match Elo loss minus model loss.

| Year | Model | n | Log loss | Brier | Accuracy | Paired t vs Elo | ECE |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 2025 | Elo | 504 | 0.64135 | 0.22549 | 0.63690 | +0.00 | 0.04234 |
| 2025 | three-input | 504 | 0.63730 | 0.22369 | 0.63492 | +1.66 | 0.03729 |
| 2025 | fast/slow | 504 | 0.63404 | 0.22162 | 0.62302 | +1.27 | 0.05100 |
| 2025 | four-input | 504 | 0.63387 | 0.22165 | 0.62698 | +1.42 | 0.03120 |
| 2025 | experience gate | 504 | 0.63355 | 0.22155 | 0.63095 | +1.55 | 0.04383 |
| 2026 | Elo | 618 | 0.66311 | 0.23483 | 0.60841 | +0.00 | 0.06458 |
| 2026 | three-input | 618 | 0.65967 | 0.23369 | 0.61812 | +1.36 | 0.06692 |
| 2026 | fast/slow | 618 | 0.65941 | 0.23364 | 0.63107 | +0.73 | 0.06945 |
| 2026 | four-input | 618 | 0.65868 | 0.23333 | 0.63916 | +0.94 | 0.06889 |
| 2026 | experience gate | 618 | 0.66044 | 0.23404 | 0.62945 | +0.58 | 0.06779 |

### Experience subgroups

The cells are mean log loss on each group’s identical match IDs. The high-experience gate is effectively fast/slow because its trained three-input weight is near zero.

| Year | Group | n | Elo | Three-input | Fast/slow | Four-input | Experience gate |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 2025 | low | 212 | 0.60804 | 0.60866 | 0.60840 | 0.60796 | 0.60725 |
| 2025 | high | 292 | 0.66554 | 0.65809 | 0.65265 | 0.65267 | 0.65265 |
| 2026 | low | 189 | 0.66035 | 0.66114 | 0.65103 | 0.65175 | 0.65438 |
| 2026 | high | 429 | 0.66432 | 0.65902 | 0.66310 | 0.66173 | 0.66310 |

### Ten-bin calibration

Each cell is `n / mean forecast / observed team-A win rate`; `—` is an empty bin. Bins are `[0,.1)`, …, `[.9,1]`.

| Year | Model | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2025 | Elo | 2/0.097/0.000 | 21/0.156/0.190 | 40/0.248/0.300 | 61/0.350/0.475 | 93/0.451/0.398 | 101/0.550/0.564 | 93/0.648/0.645 | 60/0.748/0.683 | 32/0.846/0.844 | 1/0.902/1.000 |
| 2025 | three-input | 1/0.096/0.000 | 16/0.157/0.188 | 40/0.254/0.250 | 58/0.354/0.500 | 101/0.455/0.396 | 117/0.550/0.547 | 86/0.649/0.640 | 56/0.746/0.732 | 29/0.835/0.897 | — |
| 2025 | fast/slow | 2/0.079/0.500 | 20/0.154/0.100 | 39/0.254/0.333 | 54/0.360/0.407 | 103/0.451/0.466 | 105/0.542/0.476 | 96/0.642/0.698 | 55/0.748/0.709 | 27/0.839/0.889 | 3/0.914/0.667 |
| 2025 | four-input | 2/0.085/0.500 | 18/0.156/0.111 | 42/0.257/0.310 | 53/0.364/0.415 | 103/0.453/0.456 | 110/0.544/0.509 | 96/0.645/0.667 | 50/0.749/0.740 | 28/0.836/0.893 | 2/0.913/0.500 |
| 2025 | experience gate | 2/0.093/0.500 | 17/0.151/0.059 | 42/0.251/0.310 | 53/0.359/0.434 | 104/0.451/0.442 | 107/0.545/0.505 | 97/0.643/0.691 | 49/0.746/0.714 | 31/0.834/0.871 | 2/0.920/0.500 |
| 2026 | Elo | 1/0.099/0.000 | 18/0.152/0.222 | 48/0.254/0.354 | 102/0.356/0.265 | 104/0.450/0.442 | 123/0.551/0.545 | 145/0.644/0.538 | 54/0.746/0.648 | 23/0.832/0.739 | — |
| 2026 | three-input | — | 14/0.159/0.214 | 46/0.257/0.348 | 94/0.356/0.255 | 119/0.451/0.403 | 135/0.554/0.563 | 143/0.642/0.524 | 52/0.743/0.692 | 15/0.830/0.867 | — |
| 2026 | fast/slow | 2/0.082/0.000 | 14/0.154/0.143 | 44/0.253/0.341 | 93/0.354/0.323 | 114/0.452/0.325 | 135/0.549/0.563 | 126/0.647/0.548 | 67/0.739/0.672 | 22/0.833/0.727 | 1/0.912/1.000 |
| 2026 | four-input | 2/0.087/0.000 | 12/0.152/0.167 | 45/0.255/0.333 | 90/0.355/0.300 | 117/0.451/0.316 | 145/0.551/0.566 | 124/0.648/0.573 | 62/0.738/0.661 | 20/0.829/0.750 | 1/0.904/1.000 |
| 2026 | experience gate | 1/0.097/0.000 | 14/0.150/0.143 | 47/0.254/0.362 | 91/0.357/0.275 | 117/0.453/0.359 | 132/0.550/0.553 | 128/0.647/0.562 | 66/0.738/0.652 | 22/0.832/0.773 | — |

**Verdict: NOT PROVEN.** The gate’s paired t versus Elo is +1.55 in 2025 and +0.58 in 2026, both below +2. Its ECE exceeds Elo in both years (0.04383 versus 0.04234; 0.06779 versus 0.06458). The 2025 low group has 212 matches and a small gain, while the 2026 low group has 189 matches and the gate trails fast/slow there (0.65438 versus 0.65103). Neither group offers a basis to override the frozen yearly decision. Both years were previously consulted; no production change is supported.
