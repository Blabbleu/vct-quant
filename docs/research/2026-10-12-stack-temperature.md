# Temporal temperature for the frozen three-input stack

## Pre-registration (written before scoring)

**Hypothesis.** A single scalar temperature selected in 2024 can improve the frozen no-intercept stack's calibration while preserving its discrimination and team-side symmetry. This is a calibration follow-up to `research/stack_ensemble.py`, with no changes to its three component models, input eligibility, or regularized weight fitting.

**Data and chronological split.** Load aligned pre-match production Elo, round-share, and lineup probabilities once with `stack_ensemble.load_components`. Keep decisive Tier-1 matches with year 2023–2026 and common match IDs and outcomes. Fit the original no-intercept, Elo-anchored stack on **2023 only**. Evaluate each fixed scalar in `0.70, 0.80, 0.90, 1.00, 1.10, 1.20` on **2024 only** by mean binary log loss of `sigmoid(temperature × 2023-stack-logit)`. Select the lowest-loss scalar; exact ties select 1.00 if tied, otherwise the scalar closest to 1.00. Freeze that scalar. Refit the original stack with its existing regularization on **2023 plus 2024**, freeze its weights, and apply the selected scalar to its logits for separate **2025** and **2026-to-date** scoring. Do not fit or select anything using either scoring year.

**Measures and decision.** Compare the calibrated stack, the same refit without temperature, and production Elo on identical eligible rows within each scoring year. Primary measure is paired per-match log loss, summarized by the t statistic of Elo loss minus model loss. Report n, mean log loss, Brier score, accuracy, ECE, and all ten calibration bins for each model and year. ECE is count-weighted absolute difference between average forecast and outcome rate in fixed probability bins `[0,.1), …, [.9,1]`; empty bins have no contribution. **WIN** iff calibrated paired t is greater than +2 and calibrated ECE is no worse than Elo in **both** scoring years. Otherwise **NOT PROVEN** iff both calibrated paired t values are positive; otherwise **REJECTED**. Also state whether temperature improves or worsens the uncalibrated stack in each year by log loss and ECE.

This is retrospective: both 2025 and 2026 have been repeatedly consulted. Even WIN would not be an independent holdout or permission to ship.

## Results

Snapshot evaluated 2026-10-12. The current copied database has 618 eligible 2026 matches, versus 614 in the earlier stack document; comparisons below use identical rows **within this run**. The 2023 fit gave weights `[0.974323, -0.206731, 0.287571]`. Its 2024 selection log losses were:

| Temperature | 0.70 | 0.80 | 0.90 | 1.00 | 1.10 | 1.20 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 2024 log loss | **0.650409** | 0.652957 | 0.657240 | 0.663115 | 0.670448 | 0.679112 |

Selected temperature: **0.70**. The frozen 2023–24 refit weights are `[0.819587, -0.085429, 0.128071]`. Paired t is computed from per-match Elo log loss minus model log loss. Elo's t against itself is zero. Accuracy is reported as a secondary metric.

| Year | Model | n | Log loss | Brier | Accuracy | Paired t vs Elo | ECE |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 2025 | Calibrated | 504 | 0.640029 | 0.224632 | 0.634921 | +0.221261 | 0.052157 |
| 2025 | Uncalibrated | 504 | 0.637298 | 0.223694 | 0.634921 | +1.655591 | 0.037292 |
| 2025 | Production Elo | 504 | 0.641353 | 0.225489 | 0.636905 | 0 | 0.042336 |
| 2026 | Calibrated | 618 | 0.658604 | 0.233259 | 0.618123 | +0.846690 | 0.051521 |
| 2026 | Uncalibrated | 618 | 0.659668 | 0.233692 | 0.618123 | +1.363575 | 0.066919 |
| 2026 | Production Elo | 618 | 0.663108 | 0.234828 | 0.608414 | 0 | 0.064583 |

Each cell below is `n / mean forecast / observed win rate`. `—` marks an empty bin; the script prints the unrounded values.

| Year | Probability bin | Calibrated | Uncalibrated | Production Elo |
| --- | --- | --- | --- | --- |
| 2025 | 0.0–0.1 | — | 1 / .096 / .000 | 2 / .097 / .000 |
| 2025 | 0.1–0.2 | 5 / .188 / .200 | 16 / .157 / .188 | 21 / .156 / .190 |
| 2025 | 0.2–0.3 | 22 / .268 / .182 | 40 / .254 / .250 | 40 / .248 / .300 |
| 2025 | 0.3–0.4 | 61 / .355 / .393 | 58 / .354 / .500 | 61 / .350 / .475 |
| 2025 | 0.4–0.5 | 128 / .457 / .414 | 101 / .455 / .396 | 93 / .451 / .398 |
| 2025 | 0.5–0.6 | 151 / .547 / .596 | 117 / .550 / .547 | 101 / .550 / .564 |
| 2025 | 0.6–0.7 | 95 / .642 / .621 | 86 / .649 / .640 | 93 / .648 / .645 |
| 2025 | 0.7–0.8 | 40 / .740 / .900 | 56 / .746 / .732 | 60 / .748 / .683 |
| 2025 | 0.8–0.9 | 2 / .815 / .500 | 29 / .835 / .897 | 32 / .846 / .844 |
| 2025 | 0.9–1.0 | — | — | 1 / .902 / 1.000 |
| 2026 | 0.0–0.1 | — | — | 1 / .099 / .000 |
| 2026 | 0.1–0.2 | 3 / .198 / .333 | 14 / .159 / .214 | 18 / .152 / .222 |
| 2026 | 0.2–0.3 | 21 / .267 / .095 | 46 / .257 / .348 | 48 / .254 / .354 |
| 2026 | 0.3–0.4 | 83 / .359 / .337 | 94 / .356 / .255 | 102 / .356 / .265 |
| 2026 | 0.4–0.5 | 166 / .451 / .361 | 119 / .451 / .403 | 104 / .450 / .442 |
| 2026 | 0.5–0.6 | 204 / .554 / .520 | 135 / .554 / .563 | 123 / .551 / .545 |
| 2026 | 0.6–0.7 | 115 / .635 / .661 | 143 / .642 / .524 | 145 / .644 / .538 |
| 2026 | 0.7–0.8 | 26 / .737 / .692 | 52 / .743 / .692 | 54 / .746 / .648 |
| 2026 | 0.8–0.9 | — | 15 / .830 / .867 | 23 / .832 / .739 |
| 2026 | 0.9–1.0 | — | — | — |

**Frozen verdict: NOT PROVEN.** Both calibrated t values are positive but below +2. Relative to the uncalibrated stack, temperature **worsens** 2025 log loss by 0.002731 and ECE by 0.014864; it **improves** 2026 log loss by 0.001063 and ECE by 0.015398. The conflicting year results and prior consultation of both years preclude a production change.
