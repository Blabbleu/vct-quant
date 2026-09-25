# Pre-series map-veto feasibility — 2026-09-25

Read-only audit: `python scripts/map_veto_feasibility.py` on the dev DB snapshot.
Scope: completed Tier-1 Bo3/Bo5 series dated 2023–26. This is a **coverage
check, not a model backtest**. Production Elo pooled walk-forward baseline
remains 0.6567 log loss (n=1,676; `scripts/benchmark_elo.py`).

- 1,853 eligible series; 1,623 have a distinct named, scored map row for every
  map counted by the series result. By year, played-map coverage is 331/331
  (2023), 434/434 (2024), 498/498 (2025), 360/590 (2026). In 2026, 230
  series lack complete played-map detail in the current snapshot.
- Only 707/1,853 played all the way to their recorded Bo3/Bo5 limit and have
  complete scored map rows. The other 1,043 finished early by series score;
  none has a complete observed pool. The remaining series include incomplete
  detail / inconsistent score states. A 2–0 Bo3 omits the third map even if
  both played maps are fully loaded. A 3–0 or 3–1 Bo5 omits future maps too.
- No eligible series has a nonempty `picked_by_team_id` or `picked_by_raw` in
  its map rows. Across the entire canonical `match_map` table, both columns
  are empty on all 27,469 rows (direct snapshot query). Neither `match_map`
  nor its score rows provide a pre-match veto timestamp. The CLI's manually
  supplied map list is not evidence that the historical feed supplied one.

**Decision:** do not benchmark a pre-series map-specific *series* model using
these post-match played-map names as if they were known at forecast time. It
would select on the realized series length and omit unplayed deciders; even
707 structurally complete series have no verified pre-start veto observation.
This is a data constraint, not a negative paired-t model result, and primary
forecasts remain unchanged.

**Next prerequisite:** the [source audit](veto-source-audit-2026-09-25.md)
found complete `map_vetos` text on 18 historical final-page detail snapshots,
although no picks were stored in the canonical `match_map` rows. Eight
pre-start detail probes had empty vetoes and `TBD` maps. Determine whether
ordered *full* Bo3/Bo5 vetoes appear before series start, with retrieval
timestamp, match ID and all picks/decider. Store immutable raw evidence only
through an approved live-side ingest path. Separately, a map-level outcome
benchmark can test
per-map predictions from prior map history, but must group updates by match
ID (do not learn map 1 before predicting map 2 in a pre-series forecast),
use prior matches only, and cannot claim to evaluate a pre-veto series
forecast. Freeze validation selection before scoring later years; historical
2025/26 have already been consulted repeatedly, so any apparent gain there
is retrospective, not a clean deployment holdout.
