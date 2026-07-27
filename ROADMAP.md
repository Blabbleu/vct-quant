# Roadmap

Sequenced by dependency and by what actually de-risks the project earliest.
Grounded in the data as it exists on disk today (verified 2026-07-25), not the
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

The corpus has **no date column anywhere**. Elo and walk-forward validation both
depend on time ordering, so this had to be settled explicitly rather than assumed.

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

Still out of scope until dates are backfilled from vlrggapi: genuinely time-based
features (rest days, layoff decay, roster-change recency).

## Phase 3 — Thin end-to-end slice ✅ done

**Benchmark: 0.6487 walk-forward log loss, 0.2285 Brier, 61.9% accuracy** over
6,316 scored matches in 5 folds (coin flip = 0.6931). Reproduce with
`python scripts/benchmark_elo.py`. This is the number every later model must beat.

Per fold: 0.6480 / 0.6401 / 0.6633 / 0.6322 / 0.6601 — no fold degrades badly, so
the ordering is not hiding a regime break.

The apparent underconfidence in this table (every bucket from 0.1 to 0.8 winning
more than predicted) is an artifact of the folds being 92% 2021-22 qualifier
play. On a 2023-24 holdout Elo is well calibrated — mean predicted 0.537 vs
actual 0.533 — and both K and the 400-point scale were swept and found already
optimal. See CLAUDE.md; don't re-tune them.

The earlier prequential smoke test scored 0.6449 over the whole history; the
honest walk-forward number being only 0.004 worse is expected, not suspicious.
Top teams by final rating (Paper Rex, Gambit, OpTic, LEVIATÁN, DRX, G2, FNATIC)
are genuinely elite — good evidence entity resolution and ordering are sound.

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

## Phase 4 — Feature engineering

Only now, with a benchmark to measure against. Fill in `features/rolling.py`, then
assemble in `features/build.py` → `data/processed/features.parquet`.

Candidates, roughly by expected value:

* Elo variants: K-factor tuning, map-level Elo, margin-of-victory scaling, a
  per-season regression-toward-the-mean carry.
* Team map win rates and pick/ban tendencies (`agents/`, `matches/draft_phase.csv`).
* Rolling player form from `match_map_player_stat` (rating, ACS, KAST over last N maps).
* Head-to-head record.
* Economy conversion from `matches/eco_stats.csv` — pistol and full-buy win rates.

Every one of these must be computed with `shift(1)` before rolling. **The single
most likely way this project produces impressive-and-wrong results is leakage in
this phase**, because rolling aggregates over a match's own outcome are easy to
write by accident and produce beautiful backtests.

## Phase 5 — Models beyond baseline

Logistic regression on Elo diff first (`models/baseline.py` already trains it).
Then gradient boosting on the wider feature matrix. Judge on walk-forward log loss
*and* calibration, not accuracy — and apply calibration (Platt / isotonic) fit
only on training folds.

Guard against the year-skew documented in CLAUDE.md: 2021 contributes 53% of all
map rows and is dominated by lower-tier qualifier play. Weight by recency or
tournament tier, or subset deliberately.

## Phase 6 — Forward prediction — unblocked

The hosted vlrggapi's HTTP 402 was worked around by self-hosting on
`http://127.0.0.1:3001` (already set as `vlrgg.base_url`). Verified live
2026-07-27: `results` (50), `upcoming` (33), `match/details`, and `rankings` all
return, and all 83 feed rows parse to a match_id.

`match/details` carries a real `date` field ("Monday, July 27 11:00 AM EDT Patch
13.01") plus numeric team IDs — so this is also the path that backfills real
timestamps and lifts the Phase 2 ordering restrictions.

Note the feed is shallow: `results` returns only the most recent ~50 matches per
page, so backfilling history means paging, not one call.

Then: ingest upcoming matches, resolve them onto existing team IDs, apply current
ratings, emit probabilities. This is also what backfills real match timestamps and
lifts the Phase 2 restrictions.

## Cross-cutting

* **Tests worth having**: a leakage regression test (assert no feature for match
  *i* changes when match *i*'s outcome is flipped) is worth more than broad
  coverage elsewhere.
* **Move `data/` out of OneDrive** before it tries to sync 1.3 GB.
* **DuckDB is single-writer** — keep notebooks on `read_only=True` while the
  pipeline runs.
