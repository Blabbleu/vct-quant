# Kaggle round-count economy profile: coverage and preregistration

## Hypothesis and data

Full-buy round win rate and pistol win rate from completed earlier series may add signal to production Elo. Read the read-only 2021–2026 Kaggle `eco_stats.csv` files, exclude `All Maps` summary rows, remove exact duplicate rows, and join each played map to its vlr.gg match ID using the same year's tournament/stage/match type/match name/map ID file. Resolve each team to one side of `match_sequence` using normalized names (`lower(trim(name))`). Report failed series and team joins. For each matched series side, full-buy rate is the sum of `Won` divided by the sum of `Initiated` for `$$$ (won)` rows, missing when the denominator is zero. Pistol rate is the sum of pistol `Won` divided by twice the number of distinct maps with a `Pistol Won` row.

Replay matches in strictly ascending match ID. At each match, use the last 20 prior completed series with a usable economy rate for that side; record both side counts and feature differences before ingesting the current series. Earlier Tier-2 series may supply history. Coverage is for decisive Tier-1 matches only.

## PRE-REGISTERED later scoring rule

This task computes coverage and no outcome score. The later experiment will fit **scikit-learn `LogisticRegression` with its defaults** on decisive Tier-1 2023–2024 rows where both sides have at least three prior economy series and both rate differences are available. Fixed inputs are production Elo logit, full-buy rate difference, and pistol rate difference. Freeze those coefficients and score 2025 and 2026 separately against production Elo on identical decisive Tier-1 rows; use Elo alone whenever either side lacks three prior economy series or either difference is missing. Primary metric is paired per-series log loss. Secondary metrics are Brier score, accuracy, and 10-bin calibration/ECE. Declare `WIN` only if paired log-loss t exceeds 2 in **both** years and ECE is no worse in **both** years. Otherwise declare `NOT PROVEN` if mean gain is positive in both years; otherwise `REJECTED`. There is no tuning on 2025 or 2026. Both test years were consulted in earlier research, so even a `WIN` needs a later clean holdout before promotion.

## Coverage audit

The audit used the copied DuckDB `match_sequence` and the read-only Kaggle archive. `All Maps` rows are series summaries, so they were excluded before joining played maps. Exact duplicate played-map rows were removed before totals. A bridge with multiple distinct match/game IDs is treated as ambiguous. A failed series is a distinct Kaggle tournament/stage/match type/match name combination with no unique bridge or no row in `match_sequence`. A failed team name is a distinct normalized source name that cannot identify exactly one sequence side. The audit prints every failure with its reason, source series, and match ID when available.

| Year | Decisive Tier-1 rows | Both sides ≥3 prior economy series | Kaggle series failed to map | Team names failed to map |
| --- | ---: | ---: | ---: | ---: |
| 2023 | 333 | 289 | 0 | 0 |
| 2024 | 436 | 362 | 0 | 0 |
| 2025 | 504 | 422 | 0 | 1 |
| 2026 | 618 | 518 | 0 | 1 |

The one unmatched normalized team name in 2025 and 2026 is `Mega Minors`, appearing in 25 series in each year whose sequence sides are other teams (principally NRG). The raw `all_teams_ids.csv` gives `Mega Minors` and NRG different IDs, so the source name cannot safely be assigned to NRG. Those economy rows are excluded. There are also 452 unmatched 2021 series and 322 unmatched 2022 series because their match IDs fall outside the Tier-1/Tier-2 match sequence used for production Elo; the full failure list is emitted by the audit. Kaggle 2026 economy files end after Masters London, so coverage of late-2026 matches is expected to be lower even though their earlier economy history can still meet the three-series threshold.

**Leakage boundary.** Kaggle counts are post-match facts. The replay emits a row's features before adding either side's current series, and adds counts only for completed series with smaller match IDs. Later series cannot change earlier features. No scoring metric was computed here.
