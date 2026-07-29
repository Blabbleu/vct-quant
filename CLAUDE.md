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
| `vct ingest-vlrgg [--what results\|upcoming]` | Fetch live feed → raw; upcoming also writes official Tier-1 fixtures and Elo probabilities to `data/processed/upcoming_tier1.parquet`. |
| `vct prediction MATCH_ID [--json]` | Print one cached upcoming Tier-1 prediction; refresh the upcoming feed once on a cache miss. |
| `vct predictions [--json]` | Print every cached upcoming Tier-1 forecast; fetch once if the cache is absent. |
| `vct load-vlrgg` | Merge harvested event matches into `match` / `match_team`; safe to re-run. |

Build and benchmark:

```powershell
python -m vct_quant.features.build
python scripts/backfill_vlrgg.py --pages 12
python scripts/benchmark_elo.py
python scripts/benchmark_baseline.py
```

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
          →  models (baseline: margin-aware Elo)
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

### Chronology

There is **no date or match-time column anywhere in the Kaggle corpus** — only a
`Year` column in `all_ids/all_matches_games_ids.csv`. The vlrggapi event harvest
now backfills real dates for 72,342 of 81,875 canonical matches.

**Continue using ascending vlr.gg `Match ID` as the universal ordering key.**
It covers the undated Kaggle tail and is strongly validated by the backfill:
`corr(match_id, completed_at) = 0.9956`. Use `completed_at` only for genuinely
elapsed-time features such as rest days.

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

### Detail coverage differs by source

The event backfill expands canonical match-level coverage to 81,875 matches but
does not carry map or player rows. The official model scope is much narrower:
11,948 Tier-1 and 14,864 Tier-2 matches. Player-map stats cover 11,829 Tier-1
matches and zero backfilled Tier-2 matches.

`etl/events.py::competition_tier` owns the season-aware scope:

* Tier 1: primary VCT regional circuit, Masters, Champions, historical LCQs.
* Tier 2: post-2022 Challengers/VCL and Ascension.
* Excluded: Game Changers, Premier, third-party/offseason, community, ranked.

The 2021-2022 events named "Stage N: Challengers" are Tier 1: before the 2023
league restructure, they were the primary regional VCT circuit.

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
* **vlrggapi is unofficial and fragile** — the hosted deployment returned HTTP 402
  (host over spending limit) on 2026-07-25. It is now **self-hosted on
  `http://127.0.0.1:3001`** (`github.com/axsddlr/vlrggapi`), which is what
  `vlrgg.base_url` in `config/settings.yaml` points at; start that server before
  any `vct ingest-vlrgg`. Verified working 2026-07-27 for `results`, `upcoming`,
  `match/details`, `rankings`. Every fetch is written verbatim to
  `data/raw/vlrgg/` before parsing so ingestion stays replayable when the API
  changes shape. Note `results` pages ~50 matches at a time.
* **Riot API is a dead end for pro matches** — VCT is played on the esports
  tournament realm, which is not public, and VAL-MATCH-V1 needs an approved
  production key. `ingest/riot.py` is a deliberate placeholder for ranked-queue
  form signals only.

## Implementation status

Working: both ingest/load paths, event provenance and official tier
classification, point-in-time Elo and roster churn, the 26,419-row official
feature matrix, and walk-forward evaluation.

The database is loaded: 81,875 matches (72,342 dated), 27,416 maps, and 272,991
player-map stat rows. The vlrggapi load is additive and idempotent: Kaggle rows
gain dates, while new event matches are inserted with their two teams.

**The current model is raw margin-aware Elo on Tier 1.** It feeds
`maps_a / (maps_a + maps_b)` at K=48 and scores **0.6525 log loss / 0.2302
Brier / 61.8% accuracy** over 1,524 walk-forward Tier-1 matches. Reproduce with
`python scripts/benchmark_elo.py`.

The earlier logistic win was caused by scoring the unrelated broad harvest. On
the corrected 2024 Tier-1 holdout, logistic calibration scores **0.6790 log loss
/ 0.2394 Brier**, worse than raw Elo's **0.6522 / 0.2299** on the same 436
matches (`t = -2.81`). `scripts/benchmark_baseline.py` preserves this rejected
experiment.

Tier-2 shared-Elo weights were tested on Tier-1 validation:

| Tier-2 weight | 2024 log loss | 2025 log loss |
| --- | ---: | ---: |
| **0** | **0.6522** | **0.6485** |
| 0.25 | 0.6554 | 0.6523 |
| 0.50 | 0.6590 | 0.6564 |
| 0.75 | 0.6627 | 0.6606 |
| 1.00 | 0.6666 | 0.6650 |

The result is stronger on the intended subgroup: among 100 Tier-1 matches in
2025 involving a team with prior Ascension history, weight 0 scores 0.5551
versus 0.6098 at weight 0.5. Tier-2 and Tier-1 rating pools are not directly
comparable. Keep Tier-2 history for future roster/player-form features, but its
team results currently have a validated Elo weight of zero.

In the earlier Kaggle-only signal experiment, a 93%-favourite that wins 2-1
scores 0.667 against its own 0.93 expectation, so it *loses* rating. Plain Elo
cannot express "won, but that was bad news"; a margin-weighted K cannot either,
since the winner always gains.

Four training signals were compared on the earlier Kaggle-only 2023-24
validation holdout, each at its own best K, paired per-match t-test
(`scripts/margin_elo.py`):

| signal | best K | log loss | vs binary |
| --- | --- | --- | --- |
| binary win/loss | 32 | 0.6475 | — |
| **map share** | **48** | **0.6342** | **t = +3.20** |
| margin-weighted K | 24 | 0.6425 | loses to map share, t = −2.19 |
| round share | 248 | 0.6441 | t = +0.30, i.e. nothing |

**Round-level detail is worse than map-level**, not better: individual rounds are
mostly noise, and averaging 40 of them washes out more signal than it adds.

**Retune K whenever the training signal changes.** A signal's spread *is* the
learning rate — mean |signal − 0.5| is 0.497 for binary but 0.146 for round share,
so running round share at K=32 is secretly running Elo at K≈9. Comparing variants
at a shared K measures the confound, not the variant.

**Do not retune K or the 400-point scale for the binary signal — that is done.**
K bottoms at 28 (0.6474 vs 0.6475 at K=32) and the scale at 500 (0.6447), neither
surviving a paired test (t = 1.03 for the scale; K differs by 0.0001).

**Season regression does not help.** Regressing ratings toward 1500 at each year
boundary was swept from carry=1.0 (keep everything) to 0.0 (full reset): carry=0.9
gains nothing (t = 0.71) and a full reset is significantly *worse* (t = −2.25).
Rosters do turn over, but Elo at K=48 re-learns faster than a reset can help, and
org-level strength persists across roster changes. Actual roster turnover is
implemented for Tier 1; Tier-2 roster coverage is the remaining gap.

When comparing two models on the same matches, use the **paired** per-match loss
difference, not the standard error of either aggregate score. The baseline
benchmark reports this paired t-statistic.

`features/build.py::match_sequence` is the one ordered read of the canonical
tables — `ORDER BY match_id`, the chronological key. Use it rather than querying
`match` directly, and never rely on incidental row order.

Tier-2 player/roster history is now backfilled around the final 20 matches of
nine teams that played Ascension and later appeared in Tier 1. The corrected
cohort selects 159 unique details; 203 playable Tier-2 matches / 506 maps are
available including valid history from the initial cohort pass. Leakage-safe
prior-player form is in the feature matrix. Default histogram gradient boosting
lost to raw Elo both overall and on the promoted cohort, so raw Elo remains the
production baseline. For the product slice, ingest upcoming official Tier-1
matches, resolve their teams, replay ratings, and emit raw Elo probabilities.
