# State-space Bradley–Terry map model (2026-10-11)

## Pre-registration

**Hypothesis.** A time-varying Gaussian team strength, updated after each observed map and widened during inactivity and at calendar-year boundaries, will improve Tier-1 series forecasts over production margin-aware Elo. The map-level observations and uncertainty-aware forecast distinguish this from the earlier series-level Glicko-1 experiment.

**Data and walk-forward protocol.** Replay every Tier-1 and Tier-2 match in `match_sequence` order. Use valid aligned round scores from `round_share_series.load_maps`; a map outcome is determined by which side won more rounds. Fall back to one binary series result if a match has no valid decisive maps. Forecast each series before updating from any of its maps. Score completed binary Tier-1 series only, against production Elo on identical matches. Missing or unparseable dates add no elapsed-day noise; known calendar-year transitions still add the season bump.

**Model and tuning.** Each team begins with mean 0 and variance `s0²`. At a later appearance, add `q × elapsed_days` to variance and `v_season` once per crossed calendar-year boundary. Use `scale=1.0` and the specified variance-corrected logistic map probability, with a scalar assumed-density/EKF Bernoulli update after each map. Sweep all 24 cells: `q ∈ {0.0005, 0.001, 0.002, 0.004}` per day; `s0 ∈ {0.5, 1.0}`; `v_season ∈ {0, 0.1, 0.3}`. Select the cell with lowest mean one-step-ahead **map log loss** over 2023–24 maps, including both tiers because both tiers update the shared state. Ties break in grid order. Report whether the selected value of each dimension is at a grid edge. No 2025 or 2026 outcome enters selection.

**Primary evaluation and decision.** Freeze the selected cell and report 2025 and 2026-to-date separately. Primary metric is series log loss. Also report Brier score, accuracy, paired t statistic on per-match `(Elo loss − model loss)`, and 10-bin reliability plus ECE for both models. **WIN** iff the state-space model has paired `t > +2` and `ECE ≤ Elo ECE` in **both** years. **NOT PROVEN** if both paired t values are positive and WIN fails. Otherwise **REJECTED**. Report a 50/50 logit blend with Elo and a no-intercept two-input stack fit on 2023–24 Tier-1 binary series via `stack_ensemble.fit`, then frozen, as secondary diagnostics only.

**Holdout caveat.** Earlier experiments consulted 2025 and 2026 outcomes, so these years are not pristine holdouts. This rule is fixed before this experiment's results are run; the secondary models cannot change the primary verdict.

## Results

The 24-cell replay completed in about 10 seconds on this data snapshot. The aligned map loader found 26,158 valid maps in the match-sequence universe; 1,938 decisive maps from 2023–24 contributed to tuning. All per-year scores below use the same completed binary Tier-1 matches as Elo.

### Tuning: one-step-ahead map log loss

| q per day | s0 | v_season | Maps | Map log loss |
| ---: | ---: | ---: | ---: | ---: |
| 0.0005 | 0.5 | 0.0 | 1938 | 0.669584 |
| 0.0005 | 0.5 | 0.1 | 1938 | 0.670079 |
| 0.0005 | 0.5 | 0.3 | 1938 | 0.672367 |
| 0.0005 | 1.0 | 0.0 | 1938 | 0.674509 |
| 0.0005 | 1.0 | 0.1 | 1938 | 0.674701 |
| 0.0005 | 1.0 | 0.3 | 1938 | 0.676698 |
| 0.0010 | 0.5 | 0.0 | 1938 | 0.670499 |
| 0.0010 | 0.5 | 0.1 | 1938 | 0.671359 |
| 0.0010 | 0.5 | 0.3 | 1938 | 0.673633 |
| 0.0010 | 1.0 | 0.0 | 1938 | 0.674300 |
| 0.0010 | 1.0 | 0.1 | 1938 | 0.675265 |
| 0.0010 | 1.0 | 0.3 | 1938 | 0.677584 |
| 0.0020 | 0.5 | 0.0 | 1938 | 0.673194 |
| 0.0020 | 0.5 | 0.1 | 1938 | 0.674082 |
| 0.0020 | 0.5 | 0.3 | 1938 | 0.676107 |
| 0.0020 | 1.0 | 0.0 | 1938 | 0.676219 |
| 0.0020 | 1.0 | 0.1 | 1938 | 0.677342 |
| 0.0020 | 1.0 | 0.3 | 1938 | 0.679591 |
| 0.0040 | 0.5 | 0.0 | 1938 | 0.678020 |
| 0.0040 | 0.5 | 0.1 | 1938 | 0.678780 |
| 0.0040 | 0.5 | 0.3 | 1938 | 0.680401 |
| 0.0040 | 1.0 | 0.0 | 1938 | 0.680474 |
| 0.0040 | 1.0 | 0.1 | 1938 | 0.681458 |
| 0.0040 | 1.0 | 0.3 | 1938 | 0.683341 |

**Chosen cell:** `q=0.0005`, `s0=0.5`, `v_season=0.0` (map log loss 0.669584). All three values are at a grid edge: q and s0 at their lower edges, v_season at its lower edge. The season bump preferred zero in this grid.

**Frozen stack weights:** Elo 1.137945; state-space −0.212835 (no intercept, fit on 2023–24 Tier-1 binary series).

### Tier-1 series tests

| Year | Model | n | Log loss | Brier | Accuracy | Paired t vs Elo | ECE |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 2025 | Elo | 504 | 0.641353 | 0.225489 | 0.636905 | 0.000000 | 0.042336 |
| 2025 | state-space | 504 | 0.664346 | 0.234346 | 0.623016 | -2.388935 | 0.065763 |
| 2025 | blend | 504 | 0.647866 | 0.228166 | 0.625000 | -1.467559 | 0.046382 |
| 2025 | stack | 504 | 0.640531 | 0.225237 | 0.640873 | 0.356295 | 0.058373 |
| 2026 | Elo | 616 | 0.663105 | 0.234826 | 0.608766 | 0.000000 | 0.064679 |
| 2026 | state-space | 616 | 0.681711 | 0.240798 | 0.608766 | -1.964369 | 0.068708 |
| 2026 | blend | 616 | 0.665816 | 0.235097 | 0.620130 | -0.559776 | 0.063902 |
| 2026 | stack | 616 | 0.664161 | 0.235490 | 0.605519 | -0.411675 | 0.055976 |

The Elo rows provide the paired baseline: 2025 Elo log loss/Brier/accuracy/ECE = 0.641353 / 0.225489 / 0.636905 / 0.042336; 2026 = 0.663105 / 0.234826 / 0.608766 / 0.064679. The blend and stack are report-only.

### Ten-bin reliability

Each cell is `n / mean forecast / observed win rate`; `—` means an empty bin.

| Year | Bin | State-space | Elo |
| ---: | --- | --- | --- |
| 2025 | 0.0–0.1 | 10 / 0.074 / 0.100 | 2 / 0.097 / 0.000 |
| 2025 | 0.1–0.2 | 23 / 0.158 / 0.217 | 21 / 0.156 / 0.190 |
| 2025 | 0.2–0.3 | 48 / 0.255 / 0.438 | 40 / 0.248 / 0.300 |
| 2025 | 0.3–0.4 | 53 / 0.347 / 0.453 | 61 / 0.350 / 0.475 |
| 2025 | 0.4–0.5 | 82 / 0.452 / 0.415 | 93 / 0.451 / 0.398 |
| 2025 | 0.5–0.6 | 82 / 0.549 / 0.524 | 101 / 0.550 / 0.564 |
| 2025 | 0.6–0.7 | 83 / 0.649 / 0.651 | 93 / 0.648 / 0.645 |
| 2025 | 0.7–0.8 | 66 / 0.747 / 0.636 | 60 / 0.748 / 0.683 |
| 2025 | 0.8–0.9 | 45 / 0.837 / 0.778 | 32 / 0.846 / 0.844 |
| 2025 | 0.9–1.0 | 12 / 0.915 / 0.750 | 1 / 0.902 / 1.000 |
| 2026 | 0.0–0.1 | 6 / 0.071 / 0.333 | 1 / 0.099 / 0.000 |
| 2026 | 0.1–0.2 | 40 / 0.164 / 0.275 | 18 / 0.152 / 0.222 |
| 2026 | 0.2–0.3 | 64 / 0.256 / 0.219 | 48 / 0.254 / 0.354 |
| 2026 | 0.3–0.4 | 80 / 0.350 / 0.362 | 102 / 0.356 / 0.265 |
| 2026 | 0.4–0.5 | 87 / 0.446 / 0.460 | 104 / 0.450 / 0.442 |
| 2026 | 0.5–0.6 | 110 / 0.549 / 0.555 | 121 / 0.551 / 0.545 |
| 2026 | 0.6–0.7 | 113 / 0.649 / 0.540 | 145 / 0.644 / 0.538 |
| 2026 | 0.7–0.8 | 74 / 0.741 / 0.608 | 54 / 0.746 / 0.648 |
| 2026 | 0.8–0.9 | 35 / 0.842 / 0.629 | 23 / 0.832 / 0.739 |
| 2026 | 0.9–1.0 | 7 / 0.924 / 0.714 | 0 / — / — |

**Verdict: REJECTED.** The primary paired t values are −2.388935 in 2025 and −1.964369 in 2026, so the pre-registered rule rejects the model. Its ECE also exceeds Elo in both years. The grid-edge selection suggests that more process noise or a larger starting variance would not help within this grid; no further tuning on the consulted test years is justified.
