# As-of map veto profile: coverage and preregistration

## Hypothesis and data

Prior map bans and map results may add signal to production Elo. Use Kaggle `draft_phase.csv` and `maps_scores.csv` from 2021–2026, joined through each year's `ids/tournaments_stages_matches_games_ids.csv` to the vlr.gg Match ID and then to `match_sequence`. Remove exact duplicate source rows; exclude ambiguous bridge keys and report failed joins. A team's prior draft history is its last 20 completed, lower-Match-ID series with a resolved draft. For each pool map, ban rate is the share of those series in which the team banned it. Shrunk map win rate is `(wins + 2.5) / (played + 5)` from played maps in the corresponding prior series. A series contributes to history only after its features are emitted.

The series map pool is the set of maps in any draft row of the same Kaggle Tournament. This represents the announced event pool and does not use the series's own action or outcome to determine a team's tendency. For each map, weight is `(1 - ban_rate_A) * (1 - ban_rate_B)`, normalized across the pool. `veto_edge` is the weighted sum of A minus B shrunk map win rates. If all weights are zero or a pool is unavailable, the edge is missing. Coverage counts decisive Tier-1 rows with both sides having at least three prior draft series and a finite edge.

## PRE-REGISTERED later trial

This task audits coverage and **scores no model**. The later trial will fit scikit-learn `LogisticRegression` with library defaults, once, on eligible decisive Tier-1 rows from 2023 and 2024. Its two inputs, in fixed order, are **production Elo logit** as in `research/asof_economy_stack.py` and **veto_edge**. The fit is frozen for 2025 and 2026. Score each year separately on all decisive Tier-1 rows against production Elo on identical matches, using Elo fallback when either side has fewer than three prior draft series or `veto_edge` is nonfinite. Primary metric: paired per-series log loss, with t statistic from per-series Elo minus trial loss. Secondary metrics: Brier score, accuracy, and ten-bin calibration/ECE. Verdict is `WIN` only if paired log-loss t > 2 in both years and ECE is no worse in both; otherwise `NOT PROVEN` if mean log-loss gain is positive in both; otherwise `REJECTED`. There is no tuning on either test year. Both 2025 and 2026 were consulted in prior research, so even `WIN` requires a later clean holdout before promotion.

## Coverage audit

The audit read the copied DuckDB `match_sequence` and the read-only Kaggle archive. Counts below use all decisive Tier-1 sequence rows as the denominator. Earlier Tier-2 draft series can contribute to prior history. Exact duplicate source rows were removed. A bridge key with multiple Match IDs was excluded.

| Year | Decisive Tier-1 rows | Eligible: both sides ≥3 prior draft series and finite edge | Other rows | Failed series joins | Unmapped team names |
| --- | ---: | ---: | ---: | ---: | ---: |
| 2023 | 333 | 280 | 53 | 0 | 0 |
| 2024 | 436 | 417 | 19 | 0 | 0 |
| 2025 | 504 | 486 | 18 | 0 | 1 |
| 2026 | 618 | 331 | 287 | 0 | 1 |

Join failures below count distinct source series/team/reason records after exact duplicate removal, across all Kaggle source years. `outside_match_sequence` includes matches outside the Tier-1/Tier-2 sequence used by this audit; these do not supply history. The sole unmapped normalized team name is `Mega Minors` in both 2025 and 2026.

| Source year | Reason | Count |
| --- | --- | ---: |
| 2021 | ambiguous_id_bridge | 2 |
| 2021 | outside_match_sequence | 513 |
| 2021 | unresolved_map_result | 1 |
| 2022 | outside_match_sequence | 324 |
| 2022 | unresolved_map_result | 3 |
| 2025 | team_name_mismatch | 25 |
| 2026 | team_name_mismatch | 25 |

The 2026 eligibility drop largely reflects that the available draft archive stops before many sequence results in the copied database. Coverage is an archive snapshot, not a forecast score. **No model was fitted or scored.**

## Frozen trial scoring plan

`research/asof_veto_stack.py` applies the PRE-REGISTERED later trial above unchanged: it fits once on eligible 2023–2024 decisive Tier-1 rows, freezes that fit, and scores 2025 and 2026 separately against production Elo on identical matches with Elo fallback for ineligible rows. Log loss and the paired per-series gain are primary; Brier, accuracy, and ten-bin ECE are secondary. The verdict uses exactly the stated t, ECE, and mean-gain thresholds.

## Results

One scikit-learn `LogisticRegression` fit (library defaults, version 1.9.1) used **697** eligible decisive Tier-1 rows from 2023–2024. Input order was production Elo logit, then `veto_edge`. The fitted intercept was **0.015802**; coefficients were **0.912115** and **−0.078778**, respectively. The fit was frozen for both test years. All decisive Tier-1 rows were scored, with Elo fallback where ineligible. The current copied data snapshot has 622 decisive 2026 rows, four more than the earlier coverage audit's snapshot.

| Year | n total | n eligible | Log loss trial | Log loss Elo | Brier trial | Brier Elo | Accuracy trial | Accuracy Elo | ECE trial | ECE Elo | Mean Elo − trial log loss | Paired t |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 2025 | 504 | 486 | 0.639644 | 0.641353 | 0.224776 | 0.225489 | 0.640873 | 0.636905 | 0.061789 | 0.042336 | +0.001709 | +1.178119 |
| 2026 | 622 | 331 | 0.663012 | 0.663315 | 0.234869 | 0.234920 | 0.610932 | 0.609325 | 0.050027 | 0.062688 | +0.000303 | +0.339052 |

**Verdict: NOT PROVEN.** Mean log-loss gain is positive in both years, but neither paired t exceeds 2, and 2025 ECE is worse than Elo's.

Both 2025 and 2026 were consulted in earlier research, so even a WIN needs a clean later holdout before any promotion.
