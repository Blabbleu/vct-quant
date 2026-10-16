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

## Results: frozen Elo plus economy stack

The pre-registered model was fit once on 651 eligible decisive Tier-1 series from 2023–2024. It uses scikit-learn `LogisticRegression()` defaults without scaling, tuning, or class weights. The frozen input order is Elo logit, full-buy win-rate difference (A − B), and pistol win-rate difference (A − B). The library version was scikit-learn 1.9.1.

Fitted intercept: `0.012192995765351058`. Fitted coefficients, in input order: `0.9956405839085242, 0.11885041178984271, -0.595607419170709`.

The stack uses this model only when both sides have at least three prior economy series and both differences are present. Every other forecast is production Elo. Scores below are on identical decisive Tier-1 rows for each year. Gain is Elo log loss minus stack log loss; paired t is computed from per-series loss differences.

| Year | n | Economy model n | Stack log loss | Elo log loss | Stack Brier | Elo Brier | Stack accuracy | Elo accuracy | Stack ECE | Elo ECE | Mean gain | Paired t |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 2023 | 333 | 289 | 0.607314 | 0.606869 | 0.209104 | 0.208962 | 0.672673 | 0.657658 | 0.041015 | 0.043993 | -0.000445 | -0.374580 |
| 2024 | 436 | 362 | 0.650665 | 0.652227 | 0.229306 | 0.229934 | 0.616972 | 0.614679 | 0.049958 | 0.057865 | 0.001562 | 1.610286 |
| 2025 | 504 | 422 | 0.640186 | 0.641353 | 0.225030 | 0.225489 | 0.636905 | 0.636905 | 0.043474 | 0.042336 | 0.001167 | 1.220025 |
| 2026 | 618 | 518 | 0.662638 | 0.663108 | 0.234792 | 0.234828 | 0.614887 | 0.608414 | 0.065705 | 0.064583 | 0.000469 | 0.502659 |

### Ten-bin reliability

Each cell gives `n / mean forecast / observed win rate`; empty bins show `0 / — / —`. Bins are `[0,.1)`, `[.1,.2)`, …, `[.9,1]`.

**2023**

| Bin | Stack | Elo |
| --- | --- | --- |
| 0 | 2 / 0.0707 / 0.0000 | 3 / 0.0755 / 0.0000 |
| 1 | 15 / 0.1645 / 0.2667 | 14 / 0.1646 / 0.2857 |
| 2 | 22 / 0.2573 / 0.2273 | 26 / 0.2598 / 0.1923 |
| 3 | 42 / 0.3543 / 0.2143 | 37 / 0.3551 / 0.2703 |
| 4 | 56 / 0.4564 / 0.4643 | 60 / 0.4569 / 0.4833 |
| 5 | 78 / 0.5331 / 0.5385 | 73 / 0.5313 / 0.5068 |
| 6 | 49 / 0.6489 / 0.6735 | 54 / 0.6495 / 0.6481 |
| 7 | 47 / 0.7368 / 0.7872 | 42 / 0.7373 / 0.8095 |
| 8 | 16 / 0.8431 / 0.8750 | 18 / 0.8408 / 0.8889 |
| 9 | 6 / 0.9164 / 0.8333 | 6 / 0.9156 / 0.8333 |

**2024**

| Bin | Stack | Elo |
| --- | --- | --- |
| 0 | 1 / 0.0918 / 0.0000 | 1 / 0.0845 / 0.0000 |
| 1 | 9 / 0.1684 / 0.1111 | 12 / 0.1726 / 0.0833 |
| 2 | 32 / 0.2463 / 0.2812 | 32 / 0.2517 / 0.3125 |
| 3 | 51 / 0.3519 / 0.5098 | 51 / 0.3524 / 0.5294 |
| 4 | 76 / 0.4571 / 0.4079 | 72 / 0.4543 / 0.4028 |
| 5 | 95 / 0.5457 / 0.5368 | 99 / 0.5457 / 0.4949 |
| 6 | 78 / 0.6431 / 0.5641 | 74 / 0.6457 / 0.6081 |
| 7 | 68 / 0.7491 / 0.7500 | 69 / 0.7495 / 0.7536 |
| 8 | 23 / 0.8454 / 0.8261 | 23 / 0.8481 / 0.8261 |
| 9 | 3 / 0.9198 / 0.6667 | 3 / 0.9302 / 0.6667 |

**2025**

| Bin | Stack | Elo |
| --- | --- | --- |
| 0 | 1 / 0.0971 / 0.0000 | 2 / 0.0972 / 0.0000 |
| 1 | 22 / 0.1582 / 0.1818 | 21 / 0.1563 / 0.1905 |
| 2 | 40 / 0.2541 / 0.3000 | 40 / 0.2482 / 0.3000 |
| 3 | 56 / 0.3508 / 0.4643 | 61 / 0.3504 / 0.4754 |
| 4 | 98 / 0.4501 / 0.4082 | 93 / 0.4511 / 0.3978 |
| 5 | 100 / 0.5514 / 0.5800 | 101 / 0.5497 / 0.5644 |
| 6 | 93 / 0.6461 / 0.6022 | 93 / 0.6479 / 0.6452 |
| 7 | 60 / 0.7448 / 0.7167 | 60 / 0.7482 / 0.6833 |
| 8 | 34 / 0.8426 / 0.8529 | 32 / 0.8456 / 0.8438 |
| 9 | 0 / — / — | 1 / 0.9017 / 1.0000 |

**2026**

| Bin | Stack | Elo |
| --- | --- | --- |
| 0 | 1 / 0.0990 / 0.0000 | 1 / 0.0990 / 0.0000 |
| 1 | 16 / 0.1513 / 0.2500 | 18 / 0.1517 / 0.2222 |
| 2 | 48 / 0.2579 / 0.3125 | 48 / 0.2543 / 0.3542 |
| 3 | 96 / 0.3569 / 0.2708 | 102 / 0.3562 / 0.2647 |
| 4 | 110 / 0.4493 / 0.4182 | 104 / 0.4503 / 0.4423 |
| 5 | 126 / 0.5518 / 0.5635 | 123 / 0.5509 / 0.5447 |
| 6 | 144 / 0.6450 / 0.5347 | 145 / 0.6441 / 0.5379 |
| 7 | 55 / 0.7452 / 0.6545 | 54 / 0.7459 / 0.6481 |
| 8 | 22 / 0.8313 / 0.7273 | 23 / 0.8321 / 0.7391 |
| 9 | 0 / — / — | 0 / — / — |

### Verdict

**NOT PROVEN.** Mean paired log-loss gain is positive in both 2025 and 2026, but the paired t-statistics are below 2 in both years and ECE is worse in both. The economy stack fails the pre-registered WIN bar; this is a negative result for promotion. Both test years were consulted in earlier research, so even a WIN would need a later clean holdout.
