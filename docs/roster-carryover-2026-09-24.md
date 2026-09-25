# Roster carry-over shadow — fixed decision rule

This rule was selected on 2022 H1 in `scripts/open_era.py` (2021 burn-in). The comparison already consulted 2022 H2 and 2023–26 on 2026-09-24; **neither is a fresh holdout** for subsequent refinements. No live prediction-log outcome is used to select or tune this rule. Production margin-aware Elo (K=48, Tier-2 Elo weight=0) remains the primary forecast.

## Frozen rule

For the first Tier-1 match under a new team key, inherit **100% of the source team's current Elo edge over 1500** if at least **3 players** in its lineup were last recorded together on one previously rated Tier-1 team **and** at least 3 are in that source team's latest recorded Tier-1 lineup. The lineup is the distinct player IDs (fallback: handle) recorded in player-map stats for the match. A continuing team that has already replaced its departing core is not a source. Tier-2 results do not move ratings or establish a Tier-1 source; Tier-2 player-map data may identify a new team's latest known lineup for an upcoming fixture. If a lineup is missing, start at 1500. Other Elo updates, including the map-share signal, are unchanged. The implementation is opt-in in `features/carryover.py`; `predict_upcoming` adds a shadow column only, leaving `p_team_a_win` untouched.

For future fixtures the actual lineup is not yet known: use the team's last recorded lineup if one exists, otherwise use 1500. Thus the retrospective test, which knows who fielded each match, is an **upper bound on availability**, not a direct estimate of live shadow performance. Do not substitute a future lineup into a historical prediction. `p_team_a_win_carryover` is only a candidate shadow; do not promote it based on the historical scores below. Grade on live pre-match logged forecasts with paired losses against primary Elo, and seek approval before any promotion.

## Existing historical evidence (recorded before this doc)

- 2022 H2: 0.6359 Elo vs 0.6200 carry-over; paired t = +5.08.
- 2023–26: 0.6479 Elo vs 0.6500 carry-over; paired t = −1.47 (not proven in the later regime).

## Reproduction on the dev DB snapshot

`python scripts/benchmark_carryover.py` verifies the candidate probabilities against `scripts/open_era.py` to 1e-12 on 12,099 Tier-1 historical matches; 430 team inheritances occurred (the original harness marks 418 matches with at least one inheritance). It also checks that empty-roster replay equals production Elo. On this snapshot:

- 2022 H1 tuning: n=1,760; Elo 0.6322, carry-over 0.6207, paired t=+4.68.
- 2022 H2 test: n=1,759; Elo 0.6359, carry-over 0.6200, paired t=+5.08.
- 2023–26 confirmation: n=1,863; Elo 0.6479, carry-over 0.6500, paired t=−1.47.

On the 18 cached official fixtures, the shadow differs from primary Elo on 8 despite **zero** current fixture sides having a known inheritance source. Those differences are accumulated changes to historical team ratings, not fresh roster evidence; do not present them as eight new roster moves. Future qualifying rosters may be unavailable in player-map stats and then cannot trigger inheritance for a new team.

These reproduce the previously reported results; they are not a fresh test. Since the later regime is negative and every historical year has been consulted, leave production unchanged. The next decision should be based on a prospective live sample with actual pre-match lineup availability and a separately pre-registered promotion criterion; the ensemble/shrink checkpoint in `docs/model-lab-2026-09-24.md` is **not** a criterion for this candidate.
