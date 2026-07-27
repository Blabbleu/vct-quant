# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```powershell
.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"   # NOT pip.exe — see "Venv landmine" below
pytest -q                            # full suite
pytest tests/test_ratings.py::test_compute_elo_is_point_in_time  # single test
```

CLI (`vct`, defined in `cli.py`):

| Command | Purpose |
| --- | --- |
| `vct init-db` | Apply `sql/schema.sql` → `data/vct.duckdb`. Fails if tables exist; delete the `.duckdb` file to rebuild. |
| `vct download-kaggle` | Download/unzip the historical corpus (~1.3 GB, 131 CSVs). |
| `vct inspect-kaggle` | Print every Kaggle CSV with its columns. Run this before writing any loader. |
| `vct load-kaggle` | Kaggle CSVs → canonical tables. Idempotent (clears first); prints a `LoadReport` of inserts and unresolved rows. |
| `vct ingest-vlrgg [--what results\|upcoming]` | Fetch live match feed → `data/raw/vlrgg/`. |

### Venv landmine

This venv was copied from a since-deleted sibling project, so its `Scripts/*.exe`
console shims embedded a dead interpreter path. Symptom: **the shim exits 1 with
zero output**, so `pip install` appears to do nothing at all. All shims were
regenerated, but if it recurs, `python -m <tool>` is the escape hatch — it bypasses
the shim entirely. For this reason `ingest/kaggle.py` shells out via
`sys.executable -m kaggle`, never the bare `kaggle` console script.

## Architecture

```
data/raw  →  ETL (normalize + entity resolution)  →  DuckDB canonical tables
          →  features (Elo, rolling form; point-in-time only)  →  data/processed
          →  models (baseline: logistic regression on Elo diff)
          →  eval (walk-forward backtest; log loss, Brier, calibration)
```

### Two sources, one schema — and the bridge between them

`sql/schema.sql` is shaped for the **vlrggapi v2 harvest**: every entity is keyed
on a numeric vlr.gg ID (`match_id`, `team_id`, `player_id`, all `CHECK (... > 0)`),
with `harvest_run` / `api_response` capturing request lineage.

The **Kaggle corpus is name-keyed** — its match CSVs join on text columns
(`Tournament`, `Stage`, `Match Type`, `Match Name`) and carry no IDs at all.

These two worlds are reconciled by `data/raw/kaggle/all_ids/`, which maps names to
the same numeric vlr.gg IDs the schema expects (`all_matches_games_ids.csv` supplies
Tournament ID / Match ID / Game ID; `all_players_ids.csv` and `all_teams_ids.csv`
cover entities). **Join through those files rather than fuzzy-matching names** —
`etl/entity_resolution.py` has `normalize_name` and `vlr_id_from_url` for the
residual cases only.

`match_map.match_map_id` and other surrogate keys come from DuckDB sequences
(DuckDB has no identity columns); `sql/schema.postgres.sql` is the reference
original, not applied anywhere.

### The dataset has no timestamps

There is **no date or match-time column anywhere in the Kaggle corpus** — only a
`Year` column in `all_ids/all_matches_games_ids.csv`. This directly conflicts with
two things the codebase assumes:

* `eval/backtest.py::walk_forward_splits` takes a `dates` Series.
* `features/ratings.py::compute_elo` requires matches in chronological order.

**Use ascending vlr.gg `Match ID` as the chronological proxy.** vlr.gg assigns IDs
sequentially, and this was verified against the data: per-year ID ranges are
strictly increasing with zero overlap across 2021–2026. Anything needing real
elapsed time (rest days, layoff decay) requires backfilling dates from vlrggapi.

### Two traps in the match CSVs

* **Bo1 rows store the round score, not the map score.** In `matches/scores.csv`
  a best-of-one appears as `13-3`, not `1-0` (1,671 rows). Deriving `best_of` as
  `2*max-1` yields nonsense like 25. A series is never won by more than 3 maps,
  so `max > 3` means it is a round score from a single-map match — verified:
  every such row has exactly one map. `normalize.py` normalizes these back to a
  map count.
* **Year folders overlap.** A tournament straddling a year boundary is scraped
  into both (e.g. Valorant Conquerors Championship sits in `vct_2021/` *and*
  `vct_2022/`). Anything reading year-by-year must dedupe across years or it will
  double-insert; the match/map loaders sidestep this by deduping globally on
  Match ID / Game ID.

Also note **Bo2 is a real format** — 75 matches genuinely drew (74 at 1-1, one at
2-2). `is_winner` is NULL for those, not False; exclude them from binary training
or score them as 0.5.

### Coverage is heavily skewed by year

Of 27,450 map rows across 12,677 matches, **2021 alone contributes 14,489 (53%)**,
while 2023 has just 830. The early years include far more low-tier qualifier play.
Training naively across the whole corpus lets 2021 qualifiers dominate; weight,
filter by tournament tier, or subset by year deliberately.

## Ground rules

* **No leakage.** Every feature for a match uses only data available before that
  match started. `compute_elo` is written to attach *pre-match* ratings for this
  reason. In `features/rolling.py`, prefer `groupby` + `shift(1)` before rolling
  over post-hoc filtering.
* **Temporal validation only.** Random splits are banned — team strength is
  autocorrelated, so a random split trains on the future to predict the past.
* **Optimize log loss / Brier, not accuracy.** Favorites win ~60% of the time, so
  60% accuracy is trivial. Always check `metrics.calibration_table`: a bucket
  predicted at 70% should win ~70% of the time. Well-tuned Elo is the benchmark to
  beat.
* **Raw is immutable.** Never edit `data/raw/`. The `.duckdb` file is disposable
  and rebuildable from raw via `vct init-db` + replaying ETL.

## Operational notes

* **DuckDB is single-writer.** One pipeline process at a time; notebooks must use
  `db.connect(read_only=True)`.
* **Kaggle auth**: token at `~/.kaggle/access_token`, or `~/.kaggle/kaggle.json`.
  Do *not* leave blank `KAGGLE_USERNAME=`/`KAGGLE_KEY=` in `.env` — the client
  copies every `KAGGLE_*` env var over whatever it read from the token file and
  treats present-but-empty as valid credentials, turning working auth into a 401.
* **vlrggapi is unofficial and fragile** — it returned HTTP 402 (host over spending
  limit) across the whole deployment on 2026-07-25. Fallback is self-hosting
  `github.com/axsddlr/vlrggapi` and repointing `vlrgg.base_url` in
  `config/settings.yaml`. Every fetch is written verbatim to `data/raw/vlrgg/`
  before parsing so ingestion stays replayable when the API changes shape.
* **Riot API is a dead end for pro matches** — VCT is played on the esports
  tournament realm, which is not public, and VAL-MATCH-V1 needs an approved
  production key. `ingest/riot.py` is a deliberate placeholder for ranked-queue
  form signals only.
* The repo lives inside OneDrive; `data/` is 1.3 GB. Exclude it and `.venv/` from
  sync.

## Implementation status

Working: `config`, `db`, `ingest/{kaggle,vlrgg}`, `features/ratings.py` (Elo),
`eval/{backtest,metrics}`, `etl/entity_resolution.py` helpers, and the full
Kaggle path in `etl/normalize.py`.

The database is loaded: 12,672 matches, 27,416 maps, 272,991 player-map stat
rows, 3,947 teams. Unresolved rates are low — 2.8% of `match_team` rows have a
NULL `team_id` and 3.8% of player rows a NULL `player_id`, in both cases because
the name maps to two distinct vlr.gg IDs and guessing would merge two entities.
The text name is always retained.

Sequential Elo over this data scores **0.6449 log loss / 62.6% accuracy**
(coin flip is 0.6931). That is the number to beat. It is somewhat underconfident
in the 0.6-0.8 bucket, so K-factor tuning is the obvious first improvement.

Stubs with TODOs — the actual remaining work: `features/rolling.py`,
`features/build.py` (the point-in-time feature matrix →
`data/processed/features.parquet`, one row per match with label `1` if team_a
won), and `load_vlrgg_match_results` in `etl/normalize.py`.
