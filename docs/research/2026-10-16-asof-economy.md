# As-of team economy profile: coverage audit and preregistration

## Hypothesis and fixed feature

Full-buy round win percentage may measure gunfight strength beyond margin Elo, while pistol round win percentage may add a distinct skill signal. Replay `match_sequence` in ascending match ID. For each team, use the last 20 distinct, completed series with a matched economy row, observed strictly before the current series. Compute separate unweighted means of non-null `full_buy_win_pct` and `pistol_win_pct`; a row with one null contributes to the other mean. Record the number of prior rows with at least one usable percentage and separate non-null counts for each mean. No window or weighting selection will use outcome scores. Team IDs take precedence; when an economy row has no team ID, match it to a side by normalized team name (`lower(trim(name))`). Duplicate rows resolving to the same series side count once; conflicting values are excluded. A row that cannot uniquely identify a side is excluded and counted by reason.

The copied database's `raw_stats` will be inspected for buy-type round denominators before the coverage audit. If no such counts are available, the specified unweighted match mean applies. A completed series must have both series scores and a decisive Tier-1 coverage row must have binary `score_a`; no current-series economy value enters its own feature. Earlier Tier-2 rows may supply team history, consistent with the default `match_sequence` universe; coverage is evaluated only for Tier-1 rows.

## Preregistered later scoring rule

This task computes coverage only and fits or scores no model. In a later task, fit one logistic stack on decisive Tier-1 series from 2023–2024 with inputs: production Elo logit, side-A minus side-B full-buy mean, and side-A minus side-B pistol mean. Fit coefficients only on the 2023–2024 rows for which both sides have both means. Freeze coefficients and score 2025 and 2026 separately on exactly the same decisive Tier-1 matches as production Elo. A row lacking either side's history uses its production Elo probability unchanged. Primary metric: paired per-series log loss versus production Elo. Secondary metrics: Brier score, accuracy, and 10-bin calibration/ECE. `WIN` requires paired log-loss t > 2 in both 2025 and 2026 and ECE no worse than production Elo in both years. If mean improvement is positive in both years but that bar fails, label `NOT PROVEN`; otherwise label `REJECTED`. No tuning on 2025 or 2026. Both years have been consulted by earlier research, so even a `WIN` would require confirmation on a post-cutoff holdout before promotion.

## Coverage audit

The copied DuckDB snapshot contains **zero** `match_team_economy` rows (and zero distinct economy match IDs). Consequently there are no `raw_stats` objects to inspect for round counts per buy type. The fixed implementation uses unweighted match means; any later scoring task must inspect populated `raw_stats` before claiming round weighting is possible. The join audit found zero rows failing to join because there are zero source rows. It also found zero duplicate or conflicting rows. No outcome metric was computed.

| Year | Decisive Tier-1 rows | Both sides ≥3 prior economy rows | Economy rows failing side join |
| --- | ---: | ---: | ---: |
| 2023 | 333 | 0 | 0 |
| 2024 | 436 | 0 | 0 |
| 2025 | 504 | 0 | 0 |
| 2026 | 618 | 0 | 0 |

The 2023–2024 fitting subset has no economy history in this snapshot, so the registered scoring experiment is currently infeasible. This is a coverage result, not evidence about predictive value. The audit uses the supplied copied database snapshot; its counts can change when economy rows are ingested.

**Leakage boundary.** `match_sequence` supplies ascending unique match IDs. The replay emits both side features before reading either side’s current economy row, and it adds a row only after checking the series has two recorded scores. Each deque contains at most 20 earlier matched completed series. Later match IDs cannot change earlier output. Null percentages do not enter their metric mean. Synthetic tests exercise same-series and future isolation, fallback joins, nulls, duplicate handling, and exact counts.
