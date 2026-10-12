# As-of availability audit for frozen roster carry-over

## Protocol registered before scoring (2026-10-12)

**Hypothesis.** The frozen 3-of-5, full-edge, en-bloc rule can improve Tier-1
forecasts when a debuting team's lineup is replaced by its last lineup actually
observed before kickoff. This audits feasibility and does not alter the shadow
or its promotion rule.

**Data and order.** Use the read-only `scripts/model_lab.py::load` snapshot, whose
`match_sequence` is ordered by ascending match ID. This is the project's
chronology proxy; it is not a verified kickoff or completion timestamp for every
match. Only completed matches in that sequence contribute history. Replay every
Tier-1 row, including draws, to update margin Elo at K=48. Tier-2 results have
zero Elo weight but their completed player-map lineups may update roster history.
Skip a missing lineup without erasing the previous observed lineup. Evaluate
only decisive Tier-1 matches, on identical rows for all three forecasts.

**Fixed replay.** Elo starts new team keys at 1500. The existing oracle uses
each debut Tier-1 match's own eventual lineup in the frozen `open_era.py` replay.
The as-of replay uses only each team's last lineup from a strictly lower match
ID, including Tier-2 if present, to decide inheritance before forecasting the
current match. Player provenance is updated after a match only for teams that
already have a Tier-1 rating; an unrated team's Tier-2 lineup supplies target
availability without erasing its players' last rated source. Source-team latest
lineups are updated after any completed Tier-1 or Tier-2 match. A source must already have a Tier-1
rating, at least three players must last have appeared for that source, and at
least three must still be in its latest observed lineup. Transfer the source's
entire rating edge over 1500. If no eligible source or prior target lineup
exists, start the team at 1500. Predict before reading the current score, maps,
lineup, or player stats; then update Tier-1 margin Elo and remember the completed
match's available lineups. No thresholds, shrinkage, K, or other parameters are
searched. Assert the baseline against production `compute_elo` on the same rows.

**Splits and prior consultation.** Burn in on 2021. Split decisive 2022 Tier-1
rows at the median 2022 match ID: IDs at or below it are 2022 H1, above it are
2022 H2, exactly as in `open_era.py`. The fixed design comes only from 2022 H1.
Report H2, 2023, 2024, 2025 and 2026 separately; 2023-24 continue the walk-forward state
without selection. **2022 H2 was already consulted for the oracle rule, and
2025/2026 have already been consulted by other desk research. None is an
independent holdout.** This is retrospective evidence, not a shipping test.

**Metrics.** Primary: mean binary log loss. Secondary: Brier, accuracy at 0.5,
ten-bin calibration, and ECE. For each year and model, report n, log loss,
Brier, paired t of per-match (Elo loss minus model loss), and ECE. For Elo the
paired t is zero by definition. Calibration uses fixed probability bins
`[0,.1),[.1,.2),...,[.8,.9),[.9,1]`; each bin reports n, mean forecast, observed
win rate. ECE is sum of bin n/N times absolute forecast-versus-observed gap.
Empty bins have no gap contribution. Count debut **sides** (a team key's first
Tier-1 appearance) separately from debut matches. Coverage bins for debut sides
are: no strictly prior lineup; prior lineup of 1-2 players; 3-4 players; 5+
players. Also count sides with a rated en-bloc source (actual inheritance),
and show inherited-side counts by period. These are history availability counts,
not current-match oracle coverage.

**Decision, frozen before scoring.** `PROSPECTIVE CANDIDATE` requires as-of
paired t versus Elo strictly above +2 in **each** of 2025 and 2026, ECE no
worse than Elo in **each**, and at least one genuinely pre-match inherited side
in those years combined. Otherwise `NOT VIABLE` if inherited-side coverage is
zero in both years or as-of log loss is no better than Elo in both. All other
failures are `NOT PROVEN`. Even a prospective-candidate label would only justify
future pre-match evaluation; it would not approve shipping from retrospective
years. Report descriptive `WIN` only if both years clear the t bar; otherwise
`TIE/LOSS` against production as appropriate. Do not use the live prediction
log or request new data.

## Results

Scored with `python research/asof_carryover.py` against the local read-only DB
snapshot. The median 2022 decisive Tier-1 match-ID cut is **70070.5**. The
script prints every ten-bin calibration cell (n, mean forecast, observed rate)
for all three models in each period. Empty cells are printed as `nan` for their
means and contribute zero to ECE. Its production Elo probabilities were checked
against `compute_elo` to absolute tolerance `1e-12` on all Tier-1 rows.

| Period | Model | n | Log loss | Brier | Accuracy | Paired t vs Elo | ECE |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 2022 H1 | Elo | 1759 | 0.63221 | 0.22110 | 0.65605 | +0.00 | 0.10794 |
| 2022 H1 | oracle | 1759 | 0.62074 | 0.21598 | 0.66174 | +4.68 | 0.10296 |
| 2022 H1 | as-of | 1759 | 0.63221 | 0.22110 | 0.65605 | +0.00 | 0.10794 |
| 2022 H2 | Elo | 1759 | 0.63575 | 0.22289 | 0.63559 | +0.00 | 0.05609 |
| 2022 H2 | oracle | 1759 | 0.61976 | 0.21577 | 0.65605 | +5.10 | 0.05562 |
| 2022 H2 | as-of | 1759 | 0.63575 | 0.22289 | 0.63559 | +0.00 | 0.05609 |
| 2023 | Elo | 333 | 0.60687 | 0.20896 | 0.65766 | +0.00 | 0.04399 |
| 2023 | oracle | 333 | 0.60586 | 0.20832 | 0.65766 | +0.32 | 0.06698 |
| 2023 | as-of | 333 | 0.60687 | 0.20896 | 0.65766 | +0.00 | 0.04399 |
| 2024 | Elo | 436 | 0.65223 | 0.22993 | 0.61468 | +0.00 | 0.05787 |
| 2024 | oracle | 436 | 0.65884 | 0.23271 | 0.60550 | -1.43 | 0.05374 |
| 2024 | as-of | 436 | 0.65223 | 0.22993 | 0.61468 | +0.00 | 0.05787 |
| 2025 | Elo | 504 | 0.64135 | 0.22549 | 0.63690 | +0.00 | 0.04234 |
| 2025 | oracle | 504 | 0.64103 | 0.22525 | 0.62897 | +0.15 | 0.04222 |
| 2025 | as-of | 504 | 0.64135 | 0.22549 | 0.63690 | +0.00 | 0.04234 |
| 2026 | Elo | 618 | 0.66311 | 0.23483 | 0.60841 | +0.00 | 0.06458 |
| 2026 | oracle | 618 | 0.66407 | 0.23528 | 0.60518 | -0.74 | 0.06183 |
| 2026 | as-of | 618 | 0.66311 | 0.23483 | 0.60841 | +0.00 | 0.06458 |

| Period | Debut sides | No prior lineup | 1-2 players | 3-4 players | 5+ players | Inherited sides |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 2022 H1 | 789 | 789 | 0 | 0 | 0 | 0 |
| 2022 H2 | 312 | 312 | 0 | 0 | 0 | 0 |
| 2023 | 24 | 24 | 0 | 0 | 0 | 0 |
| 2024 | 9 | 9 | 0 | 0 | 0 | 0 |
| 2025 | 13 | 13 | 0 | 0 | 0 | 0 |
| 2026 | 12 | 12 | 0 | 0 | 0 | 0 |

**Frozen verdict: NOT VIABLE (descriptive TIE/LOSS vs Elo).** The 2025 and 2026
as-of paired t values are both zero and inherited-side coverage is zero. ECE
ties Elo because every as-of probability is identical. The oracle's 2022 H2
gain (paired t +5.10 here) cannot be realized by this prior-lineup feed: none
of the 312 H2 debut sides has an earlier observed lineup in the loaded history.
The previously reported H2 n and scores differ slightly from this snapshot;
the matched comparisons above use only this run's common rows.

After the first scoring run, the protocol text was clarified to state that
unrated Tier-2 teams do not overwrite rated-source player provenance and to
list 2023 and 2024 as separate display periods. Both behaviors were already
implemented before scoring; the thresholds, comparisons, and verdict rule were
unchanged.

This is a failure of **observed roster availability in this historical
snapshot**, not evidence that actual pre-match rosters never existed. Match ID
is only a chronology proxy and may not reflect completion order for overlapping
matches. The 2025 and 2026 rows are retrospective and previously consulted; no
independent holdout or live forecast was scored. The result does not change
the frozen shadow or justify promotion.
