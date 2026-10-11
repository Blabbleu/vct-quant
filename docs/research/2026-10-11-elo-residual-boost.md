# Shrunken boosted residual on production Elo logit

## Pre-registration

**Hypothesis.** Strictly pre-match form and schedule context contains a small residual after production Elo. This shadow experiment starts at the production Elo logit and fits only a shrunken Newton tree correction. Zero rounds must reproduce Elo exactly. It is distinct from the earlier raw-feature HistGradientBoosting experiment, which lost to Elo.

**Data and timing.** Replay `match_sequence` in match ID order across the official Tier-1/Tier-2 Elo pool. Use production `compute_elo`, `margin_signal`, and `elo_k` for the fixed offset. Fit only binary Tier-1 series. Every rolling feature is captured before updating either team's history with the current match. Training rows are dated 2023 or earlier; validation is 2024. After selection, refit on all eligible rows through 2024 and freeze for separate 2025 and 2026-to-date tests. The two test years have been consulted by earlier experiments, so evidence is exploratory.

**Features.** Elo probability; log1p of prior match count per side; days since each side's previous match, with -1 and a missing flag when either date is null or no previous match exists; mean of the last five series outcomes minus their pre-match Elo probabilities from each team's perspective (zero with no history); each side's win share over its last ten maps from `round_share_series.load_maps` (-1 with no maps); `churn_a`, `churn_b`, and `player_form_diff` from `build_features`, joined by match ID (missing values use -1 for churn and 0 for player form); best-of as 1, 3, or 5, otherwise 0. Prior counts, form, and map history include both official tiers in replay order. Dates are used only for elapsed days. For a side swap, side features exchange, Elo probability complements, and player form difference changes sign.

**Model and tuning.** Augment training with both side orientations, mirrored features, complementary labels, and negated Elo logits. Each round fits a `DecisionTreeRegressor` to logistic Newton response `(y-p)/(p(1-p))` with Hessian sample weights, then adds learning rate 0.05 times its output to the fixed-offset logit. Grid: depth 1 or 2; minimum leaf size 50 or 150; rounds 0, 25, 50, 100, or 200. Select the lowest mean 2024 log loss, with deterministic grid-order tie breaking. Report the selected cell and whether it lies on an edge of depth, leaf-size, or rounds grid. Predictions average the two orientations as `0.5 * (p_ab + 1 - p_ba)`.

**Metrics and decision.** Primary metric is mean log loss against production Elo on identical matches. Secondary metrics are Brier score, accuracy, ten-bin reliability, and expected calibration error (ECE). Report paired t statistic of per-match Elo loss minus model loss. Verdict is **WIN** only if paired t > +2 and model ECE is no worse than Elo in **both** 2025 and 2026. If that fails but both t statistics are positive, verdict is **NOT PROVEN**. Otherwise verdict is **REJECTED**; selecting zero rounds is always **REJECTED**.

## Results

Run: `python research/elo_residual_boost.py` on the supplied snapshot. Map loader: 28,104 map records, 26,158 valid, 1,946 outside the official replay pool. The 2024 validation set has 436 binary Tier-1 series.

| Depth | Min leaf | 0 rounds | 25 | 50 | 100 | 200 |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 50 | **0.65222715** | 0.65565862 | 0.65772336 | 0.66122838 | 0.66617740 |
| 1 | 150 | 0.65222715 | 0.65565862 | 0.65772336 | 0.66122838 | 0.66641005 |
| 2 | 50 | 0.65222715 | 0.65791534 | 0.65994058 | 0.66357841 | 0.66461337 |
| 2 | 150 | 0.65222715 | 0.65791534 | 0.65994058 | 0.66214805 | 0.66331332 |

**Chosen cell:** depth 1, min leaf 50, 0 rounds. All zero-round cells tie, so grid order selects the first. The chosen cell is at the lower edge for rounds; depth and leaf size are each at an endpoint of their two-value grids. Refit through 2024 leaves zero trees.

| Year | n | Model log loss | Elo log loss | Model Brier | Elo Brier | Model accuracy | Elo accuracy | Paired t | Model ECE | Elo ECE |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 2025 | 504 | 0.64135311 | 0.64135311 | 0.22548949 | 0.22548949 | 0.63690476 | 0.63690476 | 0.00000000 | 0.04233625 | 0.04233625 |
| 2026 | 616 | 0.66310510 | 0.66310510 | 0.23482553 | 0.23482553 | 0.60876623 | 0.60876623 | 0.00000000 | 0.06467939 | 0.06467939 |

The model and Elo have identical reliability because zero rounds was selected. Each cell below is `count / mean forecast / observed win rate`; empty bins are shown as `0 / — / —`.

| Year | Bin | Model | Elo |
| ---: | ---: | ---: | ---: |
| 2025 | 0 | 2 / 0.09718404 / 0.00000000 | 2 / 0.09718404 / 0.00000000 |
| 2025 | 1 | 21 / 0.15633116 / 0.19047619 | 21 / 0.15633116 / 0.19047619 |
| 2025 | 2 | 40 / 0.24824387 / 0.30000000 | 40 / 0.24824387 / 0.30000000 |
| 2025 | 3 | 61 / 0.35044927 / 0.47540984 | 61 / 0.35044927 / 0.47540984 |
| 2025 | 4 | 93 / 0.45105352 / 0.39784946 | 93 / 0.45105352 / 0.39784946 |
| 2025 | 5 | 101 / 0.54965129 / 0.56435644 | 101 / 0.54965129 / 0.56435644 |
| 2025 | 6 | 93 / 0.64787820 / 0.64516129 | 93 / 0.64787820 / 0.64516129 |
| 2025 | 7 | 60 / 0.74815208 / 0.68333333 | 60 / 0.74815208 / 0.68333333 |
| 2025 | 8 | 32 / 0.84562387 / 0.84375000 | 32 / 0.84562387 / 0.84375000 |
| 2025 | 9 | 1 / 0.90174062 / 1.00000000 | 1 / 0.90174062 / 1.00000000 |
| 2026 | 0 | 1 / 0.09895409 / 0.00000000 | 1 / 0.09895409 / 0.00000000 |
| 2026 | 1 | 18 / 0.15167489 / 0.22222222 | 18 / 0.15167489 / 0.22222222 |
| 2026 | 2 | 48 / 0.25428904 / 0.35416667 | 48 / 0.25428904 / 0.35416667 |
| 2026 | 3 | 102 / 0.35622440 / 0.26470588 | 102 / 0.35622440 / 0.26470588 |
| 2026 | 4 | 104 / 0.45032679 / 0.44230769 | 104 / 0.45032679 / 0.44230769 |
| 2026 | 5 | 121 / 0.55118854 / 0.54545455 | 121 / 0.55118854 / 0.54545455 |
| 2026 | 6 | 145 / 0.64413039 / 0.53793103 | 145 / 0.64413039 / 0.53793103 |
| 2026 | 7 | 54 / 0.74593797 / 0.64814815 | 54 / 0.74593797 / 0.64814815 |
| 2026 | 8 | 23 / 0.83205767 / 0.73913043 | 23 / 0.83205767 / 0.73913043 |
| 2026 | 9 | 0 / — / — | 0 / — / — |

**Summed feature importances:** `elo_p`, `log_prior_a`, `log_prior_b`, `days_a`, `days_b`, `days_missing_a`, `days_missing_b`, `form_a`, `form_b`, `map_share_a`, `map_share_b`, `churn_a`, `churn_b`, `player_form_diff`, and `best_of` are each **0.00000000**, since no tree was retained.

**Verdict: REJECTED.** Validation chose zero rounds, and the paired t statistic is 0.00 in both test years. The fixed offset is identical to production Elo on these matches. The 2025/2026 results are exploratory because those years were consulted by earlier experiments.
