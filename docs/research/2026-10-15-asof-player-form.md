# As-of observed lineup player-form coverage

## Preregistered later trial (no scoring in this task)

Hypothesis: player ratings attached to each team's last fully observed lineup, known from strictly earlier matches, add predictive signal to production Elo. Use the offline snapshot's `match_sequence` with default Tier 1 and 2 history. The fit set is decisive Tier-1 rows in 2023 and 2024. The identical decisive Tier-1 rows in 2025 and 2026-to-date are separate retrospective tests; **both years have been consulted previously**, so this is a frozen retrospective trial, not a clean holdout. No test-year tuning or refitting.

Fit one no-intercept logistic stack on columns: logit of production Elo; as-of form difference, zero when missing; rating coverage difference; lineup completeness difference; and missing flag difference. Scale each non-Elo column by its 2023–24 standard deviation without centering. Freeze all fitted parameters and apply them to both test years. Compare against production Elo on identical matches. Primary metric: paired per-match log-loss difference and paired t statistic (Elo loss minus candidate loss). Secondary metrics: Brier score, accuracy, and ten-bin expected calibration error (ECE). **WIN only if paired t exceeds 2 and ECE is no worse than Elo in each of 2025 and 2026.** Otherwise report TIE or LOSS according to observed scores. This task only audits feature coverage; it fits nothing and computes no model scores.

## Replay policy

A `match_map_team_score.team_id` of null gives no contradiction to `match_team.team_id`; other ambiguous, duplicate, or contradictory map identities quarantine the entire map. A side-map requires exactly five unique player keys in five unique slots. The last lineup updates only when all its side-maps validate and agree on one lineup. **Deliberate policy:** ratings from every individually validated side-map enter player history even when the team's last lineup cannot update because another map was quarantined or because the lineup changed across maps. These are genuine earlier observations of those players. Current-match observations enter only after both sides' features are emitted.

## Observed coverage

Pending offline audit.

The copied offline snapshot was read on 2026-10-15. Counts below include every Tier-1 `match_sequence` row in the year, including non-decisive rows. “Complete prior sides” counts sides with an earlier validated five-player lineup; “missing prior sides” counts the remaining side opportunities. “Missing ratings” sums players without a non-null rating history inside those complete prior lineups. As-of form requires at least one rated player on each side. The current-roster form comparator reproduces `build.py`'s current-match roster selection and is descriptive only; its form is available if both sides have a non-null prior player rating. “Complete current rosters” counts exactly five distinct player keys per side across current-match stats, irrespective of map validation. Neither comparator is a deployable pre-match feature.

| Year | Rows | Complete prior sides | Both prior lineups | Missing prior sides | Missing ratings in complete prior lineups | Both as-of form | Both current-roster form | Both complete current rosters |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 2023 (fit) | 333 | 642 | 319 | 24 | 24 | 319 | 330 | 300 |
| 2024 (fit) | 436 | 863 | 429 | 9 | 128 | 429 | 435 | 432 |
| 2025 (previously consulted) | 504 | 995 | 494 | 13 | 95 | 494 | 503 | 502 |
| 2026-to-date (previously consulted) | 618 | 1224 | 606 | 12 | 15 | 606 | 618 | 613 |

Both-prior-lineup counts match the previous run on this snapshot exactly: 319/333, 429/436, 494/504, and 606/618. **Verdict: coverage audit only; no model fit or score, so no WIN/TIE/LOSS forecast verdict.** The earlier stacked logistic and Elo residual boost results do not establish a win for this as-of feature.
