# Event-cluster uncertainty audit of the frozen fast-slow stack

## Preregistration (written before scoring)

**Hypothesis and data.** The frozen four-input fast-slow stack may improve mean binary log loss over production Elo, but fixtures at the same event are dependent. Reuse `stack_fastslow.load()` and `fit_frozen()` unchanged. Fit its four weights only on decisive Tier-1 matches completed in 2023–24. Evaluate decisive Tier-1 matches in 2025 and 2026-to-date separately, with Elo and stack scored on exactly the same match IDs. Read `match_id,event_id` from the supplied database in read-only mode and require one-to-one ID alignment with the complete loaded component frame before filtering. No test-year labels enter fitting or parameter selection.

**Null event policy.** A null `event_id` defines a singleton cluster identified by its `match_id`; distinct nulls are never grouped together. Report their number each year. For a known event that crosses a year boundary, only that year's eligible fixtures enter that year's cluster. Keep all eligible fixtures of a sampled cluster together.

**Metric and uncertainty.** Primary metric is the fixture-weighted paired mean log-loss advantage, `mean(Elo loss - stack loss)`. Ordinary paired t uses the fixture-level sample standard deviation and is descriptive. For each year independently, draw the same number of event clusters as observed, uniformly with replacement, **10,000** times with NumPy seed **20261013** (a fresh generator for each year). Each drawn cluster contributes all its eligible fixtures; divide the summed paired differences by the total number of sampled fixtures. The 95% percentile interval is the empirical 2.5th and 97.5th percentiles of those 10,000 means, using NumPy's default linear quantile interpolation. No studentization or multiple-testing adjustment. Report event and fixture counts, largest event share, and the smallest paired advantage after deleting one complete event, with the removed event ID. Secondary metrics: Brier, accuracy (`p >= .5` predicts team A), ten-bin reliability (`[0,.1), …, [.9,1]`) and fixture-weighted ECE, for both Elo and stack on the same rows.

**Decision rule.** Supporting evidence requires both yearly event-cluster intervals to have strictly positive lower bounds **and** stack ECE no worse than Elo ECE in both years. Otherwise verdict is TIE if both yearly point advantages are positive, or LOSS if either is nonpositive; in either case no promotion. This is an uncertainty audit of an already consulted 2025/2026 test split, not a fresh holdout or a new tuning pass. Even a passing audit would be supporting evidence only, not independent confirmation for promotion.

## Results

The copied 2026-10-13 database was read without modification. `stack_fastslow.load()` checked component match IDs, outcome orientation and Elo parity; the event join then matched every loaded component row one-to-one by `match_id`. The frozen four-input weights from decisive Tier-1 2023–24 are `[0.12208379, -0.03991768, 0.01005058, 0.87054212]` in Elo, round-share, lineup, fast/slow order. The training split has 333 eligible matches in 2023 and 436 in 2024 (769 total). The test split has no eligible row excluded after alignment. No test labels affected fitting. All reported test fixtures are decisive Tier-1 matches on the same IDs for both forecasts; non-decisive matches, other tiers and other years are ineligible.

| Year | Fixtures | Events | Null IDs | Largest event | Elo log loss | Stack log loss | Elo Brier | Stack Brier | Elo accuracy | Stack accuracy |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 2025 | 504 | 15 | 0 | 43 (8.53%) | 0.641353 | 0.633865 | 0.225489 | 0.221655 | 63.69% | 62.70% |
| 2026 | 618 | 15 | 0 | 66 (10.68%) | 0.663108 | 0.658675 | 0.234828 | 0.233328 | 60.84% | 63.92% |

| Year | Mean paired advantage | Ordinary paired t | 95% event-cluster interval | Elo ECE | Stack ECE | Minimum advantage after one event removed |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 2025 | +0.007488 | +1.424 | [-0.001629, +0.017253] | 0.042336 | 0.031196 | +0.005277, remove event 2282 |
| 2026 | +0.004432 | +0.944 | [-0.002096, +0.011324] | 0.064583 | 0.068887 | +0.002769, remove event 2682 |

The leave-one-event-out figures are the **minimum remaining fixture-weighted mean advantage** among all event deletions, rather than the removed event's own mean. The largest reduction is 0.002211 in 2025 and 0.001664 in 2026. Every single-event deletion still leaves a positive point estimate, but the cluster intervals include zero.

### Ten-bin reliability

Each cell is `fixture count / mean forecast / observed team-A win rate`. Bins are left-closed and right-open except the last, which includes 1. Empty bins have undefined means.

| Bin | 2025 Elo | 2025 stack | 2026 Elo | 2026 stack |
| --- | --- | --- | --- | --- |
| 0.0–0.1 | 2 / .097 / .000 | 2 / .085 / .500 | 1 / .099 / .000 | 2 / .087 / .000 |
| 0.1–0.2 | 21 / .156 / .190 | 18 / .156 / .111 | 18 / .152 / .222 | 12 / .152 / .167 |
| 0.2–0.3 | 40 / .248 / .300 | 42 / .257 / .310 | 48 / .254 / .354 | 45 / .255 / .333 |
| 0.3–0.4 | 61 / .350 / .475 | 53 / .363 / .415 | 102 / .356 / .265 | 90 / .355 / .300 |
| 0.4–0.5 | 93 / .451 / .398 | 103 / .453 / .456 | 104 / .450 / .442 | 117 / .451 / .316 |
| 0.5–0.6 | 101 / .550 / .564 | 110 / .544 / .509 | 123 / .551 / .545 | 145 / .551 / .566 |
| 0.6–0.7 | 93 / .648 / .645 | 96 / .645 / .667 | 145 / .644 / .538 | 124 / .648 / .573 |
| 0.7–0.8 | 60 / .748 / .683 | 50 / .749 / .740 | 54 / .746 / .648 | 62 / .738 / .661 |
| 0.8–0.9 | 32 / .846 / .844 | 28 / .836 / .893 | 23 / .832 / .739 | 20 / .829 / .750 |
| 0.9–1.0 | 1 / .902 / 1.000 | 2 / .913 / .500 | 0 / — / — | 1 / .904 / 1.000 |

**Verdict: TIE; no promotion.** Both point advantages are positive, but neither event-cluster interval has a positive lower bound. The 2026 stack ECE is worse than Elo's. The earlier fast-slow and stack work already consulted both 2025 and 2026, so these years cannot provide independent confirmation. The result is descriptive support for a small possible gain, with uncertainty too wide to clear the preregistered bar.
