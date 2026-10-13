# Frozen fast/slow Elo as a fourth stack input

## Pre-registration (written before scoring 2025 or 2026)

Hypothesis: the already frozen organization versus form time-scale signal in fast/slow Elo adds information to the three-input Tier-1 stack. Replay `match_sequence` in match-ID order using `margin_signal`, Tier-1-only K=16 and K=256 (K=0 for Tier 2), and compute each probability before that match updates ratings. Set `p_fs = sigmoid(0.7 logit(p_16) + 0.3 logit(p_256))`. These values are fixed from the existing shadow; neither K nor blend weights will be tuned here.

Use `stack_ensemble.load_components` for production Elo, round-share series, and lineup probabilities, and `stack_ensemble.fit` for one no-intercept four-input stack. The inputs, in order, are `[logit(p_elo), logit(p_rs), logit(p_ls), logit(p_fs)]`. Fit once on decisive Tier-1 matches in 2023–24 with the existing mean log-loss objective, penalty 0.001, and anchor `[1,0,0,0]`. Also fit the existing three-input stack on the same training rows, then freeze both sets of weights. There is no refit or selection on test years.

Require exactly one row per match ID in each component, identical match-ID sets, consistent team-A outcome and production Elo probability, and finite probabilities. Refuse duplicates, missing rows, orientation disagreement, or baseline disagreement rather than silently dropping them. Score the four models on the same decisive Tier-1 rows in each year: production Elo, standalone frozen fast/slow, the frozen three-input stack, and the new four-input stack. Report any exclusions. The primary comparison is paired per-match log loss of the new stack against production Elo in 2025 and 2026-to-date separately. Also report Brier score, accuracy, ten-bin calibration, ECE, and sample size for every model.

**Frozen verdict rule:** WIN iff the new stack's paired t against Elo exceeds +2 in **each** test year and its ECE is no worse than Elo in each year. Otherwise NOT PROVEN if both yearly t values are positive; REJECTED otherwise. Both 2025 and 2026 have been repeatedly consulted in earlier research, so these are retrospective checks, not an independent holdout. A WIN here alone does not authorize a production change.

## Results

Snapshot: the copied database available on 2026-10-13. The one-to-one alignment and production Elo parity checks passed across the full match sequence. Training used 333 decisive Tier-1 matches from 2023 and 436 from 2024. No Tier-1 draw or nonbinary row was excluded in 2025 or 2026; 504 and 618 rows, respectively, enter every model comparison. Tier-2 rows and years outside the fixed split are excluded by the preregistered eligibility rule. Match/map detail availability is handled by the existing component fallbacks; no extra rows were dropped. The 2026 sample has four more matches than the prior three-input research note because this snapshot is later.

Frozen weights, in input order: three-input `[0.819587, -0.085429, 0.128071]`; four-input `[0.122084, -0.039918, 0.010051, 0.870542]`. The four-input fit puts most weight on fast/slow, which is strongly correlated with production Elo.

Paired t is computed from per-match Elo log loss minus model log loss. ECE is count-weighted absolute observed-versus-mean-forecast gap over ten fixed bins.

| Year | Model | n | Log loss | Brier | Accuracy | Paired t vs Elo | ECE |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 2025 | Elo | 504 | 0.64135 | 0.22549 | 0.63690 | +0.00 | 0.04234 |
| 2025 | fast/slow | 504 | 0.63404 | 0.22162 | 0.62302 | +1.27 | 0.05100 |
| 2025 | three-input | 504 | 0.63730 | 0.22369 | 0.63492 | +1.66 | 0.03729 |
| 2025 | four-input | 504 | 0.63387 | 0.22165 | 0.62698 | +1.42 | 0.03120 |
| 2026 | Elo | 618 | 0.66311 | 0.23483 | 0.60841 | +0.00 | 0.06458 |
| 2026 | fast/slow | 618 | 0.65941 | 0.23364 | 0.63107 | +0.73 | 0.06945 |
| 2026 | three-input | 618 | 0.65967 | 0.23369 | 0.61812 | +1.36 | 0.06692 |
| 2026 | four-input | 618 | 0.65868 | 0.23333 | 0.63916 | +0.94 | 0.06889 |

### Ten-bin calibration

Each cell is `n / mean forecast / observed win rate`; `—` means an empty bin. Bins are `[0.0,0.1)`, …, `[0.9,1.0]`.

| Year | Model | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2025 | Elo | 2/0.097/0.000 | 21/0.156/0.190 | 40/0.248/0.300 | 61/0.350/0.475 | 93/0.451/0.398 | 101/0.550/0.564 | 93/0.648/0.645 | 60/0.748/0.683 | 32/0.846/0.844 | 1/0.902/1.000 |
| 2025 | fast/slow | 2/0.079/0.500 | 20/0.154/0.100 | 39/0.254/0.333 | 54/0.360/0.407 | 103/0.451/0.466 | 105/0.542/0.476 | 96/0.642/0.698 | 55/0.748/0.709 | 27/0.839/0.889 | 3/0.914/0.667 |
| 2025 | three-input | 1/0.096/0.000 | 16/0.157/0.188 | 40/0.254/0.250 | 58/0.354/0.500 | 101/0.455/0.396 | 117/0.550/0.547 | 86/0.649/0.640 | 56/0.746/0.732 | 29/0.835/0.897 | — |
| 2025 | four-input | 2/0.085/0.500 | 18/0.156/0.111 | 42/0.257/0.310 | 53/0.364/0.415 | 103/0.453/0.456 | 110/0.544/0.509 | 96/0.645/0.667 | 50/0.749/0.740 | 28/0.836/0.893 | 2/0.913/0.500 |
| 2026 | Elo | 1/0.099/0.000 | 18/0.152/0.222 | 48/0.254/0.354 | 102/0.356/0.265 | 104/0.450/0.442 | 123/0.551/0.545 | 145/0.644/0.538 | 54/0.746/0.648 | 23/0.832/0.739 | — |
| 2026 | fast/slow | 2/0.082/0.000 | 14/0.154/0.143 | 44/0.253/0.341 | 93/0.354/0.323 | 114/0.452/0.325 | 135/0.549/0.563 | 126/0.647/0.548 | 67/0.739/0.672 | 22/0.833/0.727 | 1/0.912/1.000 |
| 2026 | three-input | — | 14/0.159/0.214 | 46/0.257/0.348 | 94/0.356/0.255 | 119/0.451/0.403 | 135/0.554/0.563 | 143/0.642/0.524 | 52/0.743/0.692 | 15/0.830/0.867 | — |
| 2026 | four-input | 2/0.087/0.000 | 12/0.152/0.167 | 45/0.255/0.333 | 90/0.355/0.300 | 117/0.451/0.316 | 145/0.551/0.566 | 124/0.648/0.573 | 62/0.738/0.661 | 20/0.829/0.750 | 1/0.904/1.000 |

**Verdict: NOT PROVEN.** The four-input stack has positive paired t in both test years but neither reaches +2; 2026 ECE (0.06889) also exceeds Elo (0.06458). It improves log loss over the frozen three-input stack on both years (2025: 0.63387 versus 0.63730; 2026: 0.65868 versus 0.65967), but that secondary comparison does not change the frozen verdict. Both years are repeatedly consulted retrospective evidence, and production remains unchanged.

