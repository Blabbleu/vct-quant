# Prospective evidence gate for the frozen four-input fast-slow stack

## Preregistration (before prospective scoring)

**Hypothesis.** The already frozen four-input stack improves binary log loss over contemporaneous production Elo for future decisive Tier-1 fixtures. The frozen weights are `[0.12208379, -0.03991768, 0.01005058, 0.87054212]`; this gate never computes inputs or fits weights. The retrospective 2025 and 2026 results were consulted and provide no prospective evidence.

**Cohort and source.** The only forecast source is a supplied, immutable external CSV snapshot with `match_id`, `captured_at`, `kickoff_at`, `team_a_id`, `team_b_id`, `p_stack`, and `p_elo`. All timestamps are UTC with explicit timezone. The fixed cutoff is **2026-10-13T04:00:00Z**. Admit a record only when capture is strictly after the cutoff and strictly before its scheduled kickoff. A match ID may occur once in the entire supplied snapshot; duplicates, including revised forecasts, invalidate the snapshot rather than choosing a favorable version. Never fill missing forecasts from settled rows, historical replay, or the prediction log. Score only exact match-ID settlements from a read-only copied DuckDB, with unique match and team rows, matching team-A and team-B IDs in team-number order, a decisive team-A outcome, and event tier 1. Exclude ties and other tiers. Missing settlement, tier, orientation, completion time, or other required join data is incomplete and unscored, not a model loss. Null DB `scheduled_at` means the copied harvest did not preserve kickoff and does not block the join; a populated DB schedule must equal the immutable snapshot kickoff. A settlement with `completed_at` before capture or kickoff is ineligible, so historical results cannot be relabeled as live forecasts.

**Metrics.** Score Elo and stack on the identical admitted fixtures, separately by UTC kickoff calendar year. Primary metric is mean binary log loss and paired advantage `mean(Elo loss - stack loss)`. Secondary metrics are Brier, accuracy at probability 0.5, and count-weighted ten-bin ECE with bins `[0,.1), …, [.9,1]`. Paired t uses sample standard deviation and is null for fewer than two observations or numerically zero variance. An absent event ID creates a singleton cluster keyed by match ID. For each year with at least two event clusters, sample the observed number of whole event clusters uniformly with replacement 10,000 times, using a fresh NumPy generator seeded **20261013** for each year. Report the 2.5th and 97.5th percentiles of fixture-weighted paired advantages. With fewer clusters the interval is null.

**Decision rule.** `SUPPORTING EVIDENCE` requires at least **150** truly prospective scored decisive Tier-1 fixtures in total, at least two event clusters in every scored year, strictly positive paired mean advantage and cluster interval lower bound in every scored year, and stack ECE no worse than Elo ECE in every scored year. If the fixture or cluster threshold is unmet, or required join data is incomplete, verdict is `PENDING`. Once complete and sufficiently sized, failure of any advantage, interval, or ECE bar is `NOT PROVEN`. This is a research evidence label only and never changes the existing fast-slow shadow promotion rule.

## Current result and operational limit

No qualifying immutable post-cutoff stack forecast file is supplied. The gate therefore has the following result; there is no prospective 2025 or 2026 comparison to report.

| Cohort | Scored fixtures | Log loss / Brier / paired t / ECE | Cluster interval | Verdict |
| --- | ---: | --- | --- | --- |
| Post-cutoff snapshot | 0 | Undefined | Undefined | PENDING |

A producer of pre-start four-input stack probabilities does not yet exist. Adding live shadow logging requires separate owner approval; this research scorer does not write forecasts or production data.
