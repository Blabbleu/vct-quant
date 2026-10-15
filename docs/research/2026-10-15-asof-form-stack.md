# Frozen Elo plus as-of lineup form stack

## Pre-registered trial

The [as-of player-form coverage pre-registration](2026-10-15-asof-player-form.md) fixed this trial before scoring:

> The fit set is decisive Tier-1 rows in 2023 and 2024. The identical decisive Tier-1 rows in 2025 and 2026-to-date are separate retrospective tests; **both years have been consulted previously**, so this is a frozen retrospective trial, not a clean holdout. No test-year tuning or refitting.
>
> Fit one no-intercept logistic stack on columns: logit of production Elo; as-of form difference, zero when missing; rating coverage difference; lineup completeness difference; and missing flag difference. Scale each non-Elo column by its 2023–24 standard deviation without centering. Freeze all fitted parameters and apply them to both test years. Compare against production Elo on identical matches. Primary metric: paired per-match log-loss difference and paired t statistic (Elo loss minus candidate loss). Secondary metrics: Brier score, accuracy, and ten-bin expected calibration error (ECE). **WIN only if paired t exceeds 2 and ECE is no worse than Elo in each of 2025 and 2026.**

For this run, the remaining verdict labels are **NOT PROVEN** if both test-year paired t statistics are positive, and **REJECTED** otherwise. The fit uses the existing stack ridge penalty toward Elo with anchor `[1, 0, 0, 0, 0]`. A two-column Elo plus form-difference fit is diagnostic only and does not affect the verdict.

## Results

The offline snapshot copied on 2026-10-15 supplied the full `match_sequence` and as-of replay. Production Elo used `compute_elo` with `margin_signal` and `elo_k`, with probabilities in team-A orientation. All match IDs joined one to one before filtering; no eligible decisive Tier-1 rows were excluded. The 2023–24 fit contained 769 rows. The 2025 and 2026-to-date rows below were **previously consulted** by earlier research. The same frozen weights and scales were applied to each year. Paired t is based on Elo per-match log loss minus stack per-match log loss; Elo's self-comparison is zero. Accuracy uses a 0.5 cutoff. ECE uses ten bins.

| Year | Model | n | Log loss | Brier | Accuracy | Paired t vs Elo | ECE |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 2023 (fit) | Five-column stack | 333 | 0.60284 | 0.20751 | 0.69069 | +0.99 | 0.05245 |
| 2023 (fit) | Production Elo | 333 | 0.60687 | 0.20896 | 0.65766 | 0.00 | 0.04399 |
| 2024 (fit) | Five-column stack | 436 | 0.65144 | 0.22988 | 0.61927 | +0.23 | 0.04813 |
| 2024 (fit) | Production Elo | 436 | 0.65223 | 0.22993 | 0.61468 | 0.00 | 0.05787 |
| 2025 (previously consulted) | Five-column stack | 504 | 0.63482 | 0.22264 | 0.63690 | +2.31 | 0.03485 |
| 2025 (previously consulted) | Production Elo | 504 | 0.64135 | 0.22549 | 0.63690 | 0.00 | 0.04234 |
| 2026-to-date (previously consulted) | Five-column stack | 618 | 0.66502 | 0.23601 | 0.61650 | −0.64 | 0.05928 |
| 2026-to-date (previously consulted) | Production Elo | 618 | 0.66311 | 0.23483 | 0.60841 | 0.00 | 0.06458 |

Frozen weights in registered column order (Elo logit, form difference, rating coverage difference, prior lineup completeness difference, missing-form flag difference): `[0.87779182, 0.07918889, 0.03142464, -0.05943497, 0.05943497]`. Population standard deviations used to divide the four non-Elo columns, in that order: `[0.09254274, 0.13025677, 0.10798720, 0.10798720]`. The columns were **not centered**. None had zero fit-row standard deviation, so none was left unscaled. The opposite lineup and missing-flag weights reflect their overlapping information in this snapshot.

Ten-bin reliability for the two test years follows. Each populated cell is `n/mean forecast/observed win rate`; `—` is an empty bin. Bins are `[0,.1), …, [.9,1]`.

| Year | Model | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2025 | Stack | — | 18/0.156/0.167 | 42/0.251/0.238 | 58/0.352/0.500 | 101/0.453/0.406 | 107/0.550/0.551 | 92/0.648/0.630 | 59/0.742/0.746 | 27/0.833/0.889 | — |
| 2025 | Elo | 2/0.097/0.000 | 21/0.156/0.190 | 40/0.248/0.300 | 61/0.350/0.475 | 93/0.451/0.398 | 101/0.550/0.564 | 93/0.648/0.645 | 60/0.748/0.683 | 32/0.846/0.844 | 1/0.902/1.000 |
| 2026 | Stack | — | 15/0.155/0.200 | 45/0.257/0.356 | 104/0.359/0.327 | 110/0.453/0.355 | 140/0.551/0.543 | 140/0.641/0.579 | 50/0.742/0.600 | 14/0.828/0.857 | — |
| 2026 | Elo | 1/0.099/0.000 | 18/0.152/0.222 | 48/0.254/0.354 | 102/0.356/0.265 | 104/0.450/0.442 | 123/0.551/0.545 | 145/0.644/0.538 | 54/0.746/0.648 | 23/0.832/0.739 | — |

**Diagnostic only, excluded from the verdict:** a two-column Elo plus form-difference stack fitted on the same 769 rows had frozen weights `[0.87296870, 0.07737623]`, with the same form scale `0.09254274`. It scored 2025 log loss 0.63716, Brier 0.22372, accuracy 0.63492, paired t +2.10, ECE 0.03282 (n=504); in 2026 it scored 0.65866, 0.23310, 0.62136, +2.62, and 0.05812 (n=618). Those descriptive scores do not alter the registered five-column decision.

## Verdict

**REJECTED.** The five-column stack clears the paired t and ECE bars in 2025, but its 2026 log loss is worse than production Elo and its paired t is negative. The earlier three-input stack had paired t +1.66 and +1.29 in 2025 and 2026; the fast-slow fourth-input stack had +1.42 and +0.94. This trial's 2025 gain is larger, but its 2026 reversal makes the registered full stack less consistent than either earlier stack. The two-column diagnostic looks promising on this snapshot, yet it was explicitly outside the verdict; both test years were previously consulted, so even a diagnostic pass is retrospective evidence only. Production remains unchanged.
