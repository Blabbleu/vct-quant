# Roadmap

Sequenced by dependency and by what actually de-risks the project earliest.
Grounded in the data as it exists on disk today (verified 2026-07-28), not the
dataset description.

## Phase 0 — Foundation ✅ done

Scaffold, schema, Elo, backtest splitter, and metrics are in place. The Kaggle
corpus is downloaded (12,677 matches / 27,450 map rows / 131 CSVs). The venv's
broken console shims and stale editable install are repaired.

## Phase 1 — ETL: Kaggle → canonical tables ✅ done

Implemented in `etl/normalize.py`, run with `vct load-kaggle`. Loaded 12,672
matches, 27,416 maps, 272,991 player-map rows, 3,947 teams, 14,775 players.
Resolution held up far better than feared: only 1 of 12,676 score rows failed to
resolve to a match_id. Residual NULL-ID rates are 2.8% (teams) and 3.8%
(players), all from names carrying two distinct vlr.gg IDs, where guessing would
merge two entities' histories.

Three data defects found and handled — see CLAUDE.md: Bo1 rows store round
scores rather than map scores, year folders overlap so a tournament can be
scraped into two of them, and Bo2 draws are real (75 matches) so `is_winner` is
NULL rather than False.

*Original plan retained below for context.*

Order matters here — build the ID spine before any match data:

1. **Load `all_ids/` first.** `all_teams_ids.csv` → `team`, `all_players_ids.csv`
   → `player`, and `all_tournaments_stages_match_types_ids.csv` → `event`. These
   supply the numeric vlr.gg IDs that every other table's foreign keys require.
2. **Build the name→ID resolver** from `all_matches_games_ids.csv`. It is the
   join table between the name-keyed match CSVs (`Tournament` + `Stage` +
   `Match Type` + `Match Name`) and numeric `Match ID` / `Game ID`. Also fold in
   `all_teams_mapping.csv` (Abbreviated → Full Name), since match CSVs
   inconsistently use both forms.
3. **Load `matches/scores.csv` → `match` + `match_team`.** This carries the label
   (`Match Result`, `Team A Score`, `Team B Score`).
4. **Load `matches/maps_scores.csv` → `match_map` + `match_map_team_score`**, then
   `matches/overview.csv` → `match_map_player_stat`.

Leave `harvest_run` / `api_response` lineage columns NULL for Kaggle rows — they
are nullable and only meaningful for live vlrggapi harvests.

**Expect resolution failures.** Orgs rebrand and players change handles across
2021–2026. Do not silently drop unresolved rows — count them, log them, and make
the unresolved rate a number you watch. A quietly-dropped 15% will distort every
rating that follows.

**Exit criterion:** `match`, `match_team`, `match_map` populated; unresolved-entity
rate measured and consciously accepted.

## Phase 2 — Establish chronology ✅ done

The Kaggle corpus has **no date column anywhere**. Elo and walk-forward
validation both depend on time ordering, so this had to be settled explicitly.

**Ascending vlr.gg `Match ID` is the ordering key** (per-year ID ranges are
strictly increasing with zero overlap across all six years). No separate sequence
column was added — `match.match_id` already *is* that column, persisted and a
primary key. What changed instead:

* `features/build.py::match_sequence` is the single ordered read of the canonical
  tables (`ORDER BY match_id`), returning `match_id, team_a, team_b, score_a`.
  Nothing downstream relies on incidental row order. Unresolved teams fall back to
  a `name:` key so the 2.8% NULL `team_id` rows stay distinct entities instead of
  merging into one.
* `walk_forward_splits` now cuts by **rank**, not by value, so it accepts any
  sortable key. Its old `pd.to_datetime` would have read match_ids as nanoseconds
  and silently produced garbage. Side benefit: every test window holds the same
  number of matches regardless of how clumped the key is.

The vlrggapi event backfill now supplies real dates for 72,342 of 81,875 matches
and validates the proxy (`corr(match_id, completed_at) = 0.9956`). Keep match ID
as the universal ordering key; use `completed_at` for elapsed-time features.

## Phase 3 — Thin end-to-end slice ✅ done

The canonical database retains all 81,875 harvested matches, but the model
sequence is restricted to 11,948 official Tier-1 and 14,864 official Tier-2
matches. The other 55,063 matches never enter ratings or features.

Margin-aware Elo scores **0.6525 walk-forward log loss / 0.2302 Brier / 61.8%
accuracy** over 1,524 scored Tier-1 matches in 5 folds (coin flip = 0.6931).
Reproduce with `python scripts/benchmark_elo.py`.

*Original plan retained below.*

Do this **before** building more features. Elo, the splitter, and the metrics
already exist — the only missing link was ETL. So the moment Phase 1 lands, a
complete honest number is a short step away:

`match` table → order by Match ID → `compute_elo` → `walk_forward_splits` →
`log_loss` / `brier_score` / `calibration_table`.

**Exit criterion:** a real walk-forward log loss for pure Elo, plus a calibration
table. This is the benchmark every later model must beat, and in esports
prediction well-tuned Elo is genuinely hard to beat. Getting this number early
tells you whether anything downstream is actually adding value.

Sanity floor: also score an always-predict-0.5 baseline (log loss ≈ 0.693). If
Elo can't clear that comfortably, something in ETL or ordering is wrong.

## Phase 4 — Feature engineering ✅ thin matrix done

`features/build.py` now emits 26,419 point-in-time Tier-1/Tier-2 rows with Elo,
prior-match counts, and roster churn to `data/processed/features.parquet`.

**Elo variants are done — see CLAUDE.md for the Kaggle-only experiment.** Margin
of victory as a fractional score won (0.6487 → 0.6368 walk-forward, K=48). K
tuning, the rating scale, round-level margin, margin-weighted K, and per-season
regression were all tried and rejected on a paired significance test.

Player-map statistics cover 11,829 of 11,948 Tier-1 matches. A targeted,
resumable detail harvest selects 159 unique matches: the final 20 Tier-2
matches available for nine teams that played Ascension and subsequently
appeared in Tier 1. Including valid history captured during the initial cohort
pass, Tier-2 player stats cover 203 playable matches / 506 maps. The feature
matrix includes prior-player form, coverage, and the share of that history
coming from Tier 2.

Remaining candidates, roughly by expected value:

* Map-level Elo (a separate rating per map — `match_map` is loaded and unused).
* Glicko instead of Elo: carrying a rating *uncertainty* per team would handle the
  71 unseen teams in the 2025 holdout and the weaker evidence of a Bo1.
* Team map win rates and pick/ban tendencies (`agents/`, `matches/draft_phase.csv`).
* Rolling player form from `match_map_player_stat` (rating, ACS, KAST over last N maps).
* Head-to-head record.
* Economy conversion from `matches/eco_stats.csv` — pistol and full-buy win rates.

Every one of these must be computed with `shift(1)` before rolling. **The single
most likely way this project produces impressive-and-wrong results is leakage in
this phase**, because rolling aggregates over a match's own outcome are easy to
write by accident and produce beautiful backtests.

## Phase 5 — Logistic calibration ❌ rejected

The old broad-corpus win was contamination from unrelated events. On the
correct 2024 Tier-1 holdout, logistic calibration scores **0.6790 log loss /
0.2394 Brier**, significantly worse than raw Elo's **0.6522 / 0.2299**
(`t = -2.81`). Reproduce with `python scripts/benchmark_baseline.py`.

Tier-2 shared-Elo weights `0/.25/.5/.75/1` were also evaluated on Tier-1 matches
from both 2024 and 2025. Every positive weight lost, including for teams with
Ascension history, because the mostly isolated rating pools are not directly
comparable. Tier-2 rows remain available for future roster/player features, but
their team results do not move shared Elo.

Untuned histogram gradient boosting with Elo, roster, experience, and
leakage-safe player-form features was also rejected. Trained through 2024 and
tested on 2025, it scored **0.6957 log loss / 0.2447 Brier** versus raw Elo's
**0.6485 / 0.2286**. On the 105 matches involving an Ascension-promoted team,
boosting scored **0.5990 / 0.2029** versus Elo's **0.5568 / 0.1881**.

## Phase 6 — Forward prediction — next

The hosted vlrggapi's HTTP 402 was worked around by self-hosting on
`http://127.0.0.1:3001` (already set as `vlrgg.base_url`). Verified live
2026-07-27: `results` (50), `upcoming` (33), `match/details`, and `rankings` all
return, and all 83 feed rows parse to a match_id.

The historical event harvest and `vct load-vlrgg` are done: 81,875 canonical
matches, 72,342 with real dates. `vct ingest-vlrgg --what upcoming` now preserves
the raw feed and writes only official Tier-1 fixtures to
`data/processed/upcoming_tier1.parquet`, including canonical team/event IDs and
stable fallback team keys. It replays the validated margin-aware Elo through
the latest completed official matches and attaches both teams' win
probabilities. Next: decide whether the product surface should be a CLI report,
small API, or dashboard.

## Cross-cutting

* **Tests worth having**: a leakage regression test (assert no feature for match
  *i* changes when match *i*'s outcome is flipped) is worth more than broad
  coverage elsewhere.
* **DuckDB is single-writer** — keep notebooks on `read_only=True` while the
  pipeline runs.
