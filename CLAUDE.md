# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```powershell
.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"   # NOT pip.exe — see "Venv landmine" below
pytest -q                            # full suite (pyproject puts the repo root on sys.path)
pytest tests/test_ratings.py::test_compute_elo_is_point_in_time  # single test
```

CLI (`vct`, defined in `cli.py`):

| Command | Purpose |
| --- | --- |
| `vct init-db` | Apply `sql/schema.sql` → `data/vct.duckdb`. Fails if tables exist; delete the `.duckdb` file to rebuild. |
| `vct download-kaggle` | Download/unzip the historical corpus (~1.3 GB, 131 CSVs). |
| `vct inspect-kaggle` | Print every Kaggle CSV with its columns. Run this before writing any loader. |
| `vct load-kaggle` | Kaggle CSVs → canonical tables. Idempotent (clears first); prints a `LoadReport` of inserts and unresolved rows. |
| `vct update` | Matchday refresh: newest official event match lists → `load-vlrgg` → detail fetch for any unresolved Tier-1 team name → upcoming forecasts (Elo plus shadow models), appended to `data/processed/prediction_log.parquet`. Grade with `python scripts/grade_predictions.py`. |
| (market prices) | Every upcoming refresh also fetches open Polymarket Valorant moneylines (public Gamma API, no key) → `data/raw/polymarket/`, fuzzy-matched onto fixtures by start time ±2h and both team names (`etl/markets.py`). Logged as `p_market_a`, `market_spread`, `market_volume`; the grader scores Elo against it on markets with spread ≤ 0.10. An outage logs Elo only. |
| `vct ingest-vlrgg [--what results\|upcoming]` | Fetch live feed → raw; upcoming also writes Tier-1 and Game Changers fixtures (`tier` column) with Elo probabilities to `data/processed/upcoming_tier1.parquet`. |
| `vct prediction MATCH_ID [--json]` | Print one cached upcoming Tier-1 prediction; refresh the upcoming feed once on a cache miss. |
| `vct predictions [--json]` | Print every cached upcoming Tier-1 forecast; fetch once if the cache is absent. |
| `vct load-vlrgg` | Merge harvested event matches into `match` / `match_team`; safe to re-run. |

### The desk app: three layers, one payload

`src/vct_quant/dashboard.py` is the **model layer** and the only place the numbers
are computed. `python -m vct_quant.dashboard` prints the whole payload as JSON.
Heavy Elo replays are cached by `lru_cache` keyed on the `.duckdb` mtime, so
`vct update` invalidates them and nothing else does.

`server.js` is the **backend**: `node server.js` (or `npm start`) on
`http://127.0.0.1:8000`. Zero npm dependencies -- node's `http`, `fs` and
`child_process`. It shells out to the model layer, caches the payload the same way,
collapses concurrent requests into one Python process, serves `frontend/index.html`
at `/`, and answers `/api/snapshot`, `/api/fixtures`, `/api/backtest`, `/api/live`,
`/api/rankings`, `/api/ledger`, `/api/health`. **GET only** -- DuckDB is
single-writer, so ingestion stays a CLI job. Set `PYTHON` to override the
interpreter, `PORT`/`HOST` to move it. `npm run check` boots it and hits every route.
**The cache keys on data, not code** -- editing `dashboard.py` needs a server
restart, while `vct update` is picked up by the page's refresh button.

`frontend/index.html` is the **frontend**: React 18 + Babel from cdnjs, no build
step. It runs in two modes from one file -- served by `server.js` it fetches
`/api/snapshot` and shows a live chip and a refresh button; baked by
`python scripts/report.py` (which replaces the `__DATA__` token in the
`<script id="baked">` tag) it renders `data/processed/report.html` with no server,
which is what the published artifact needs since an artifact cannot reach
localhost. Republish that file with the Artifact tool to refresh
https://claude.ai/artifact/EQbyox8ZHiUEHtQbUmxQQj.

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
now backfills real dates for 72,507 of 82,040 canonical matches.

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

The event backfill expands canonical match-level coverage to 82,040 matches but
does not carry map or player rows. The official model scope is much narrower:
12,108 Tier-1 and 14,869 Tier-2 matches. Player-map stats cover 12,085 Tier-1
matches and zero backfilled Tier-2 matches.

`etl/events.py::competition_tier` owns the season-aware scope:

* Tier 1: primary VCT regional circuit, Masters, Champions, pre-2027 LCQs;
  from 2027 also Kickoff and the Cups.
* Tier 2: post-2022 Challengers/VCL and Ascension; from 2027 the open stages
  (Open Qualifiers, Open Playoffs, Wild Card, 2027+ LCQs), which keep amateur
  rosters out of the Tier-1 pool. `vct update` prints a WARNING for any
  VCT-branded title that gets no tier: that is how a renamed 2027 stage shows up.
* Tier 3: Game Changers, as its **own rating pool** (`match_sequence(tiers=(3,))`).
  44 teams appear in both pools; never replay them together.
* Excluded: Premier, third-party/offseason, community, ranked.

The 2021-2022 events named "Stage N: Challengers" are Tier 1: before the 2023
league restructure, they were the primary regional VCT circuit.

VCT 2027 is an open, all-tournament season (see ROADMAP "Phase 7"). The 2027
tier rules were written against guessed titles; vlr.gg had no 2027 events on
2026-09-24. Swap the guesses in `test_vct_2027_open_stages_stay_out_of_tier_1`
for real titles as soon as the November Kickoff qualifiers are listed.

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
classification, point-in-time Elo and roster churn, the 26,584-row official
feature matrix, and walk-forward evaluation.

The database is loaded: 82,040 matches (72,507 dated), 28,556 maps, and 284,371
player-map stat rows. The vlrggapi load is additive and idempotent: Kaggle rows
gain dates, while new event matches are inserted with their two teams.

**The current model is raw margin-aware Elo on Tier 1.** It feeds
`maps_a / (maps_a + maps_b)` at K=48 and scores **0.6567 log loss / 0.2320
Brier / 61.6% accuracy** over 1,676 walk-forward Tier-1 matches (data through
2026-09-24, after the automatic team-ID resolution below). Reproduce with
`python scripts/benchmark_elo.py`.

### Shadow models and the 2026-09-24 model lab

Six more candidates were tuned on 2023-24 and scored on 2025/26
(`docs/model-lab-2026-09-24.md`; `scripts/model_lab.py`, `model_lab2.py`,
`ensemble_robustness.py`). None cleared the t > 2 ship bar.
Best-of-aware map ratings (t = -4.24), calendar inactivity decay (+0.00) and a
player-level Elo blend (+0.31) were rejected. A walk-forward logistic refit of
Elo lost on validation in every setting that finished; its player-form/churn
variants timed out unscored.

Two survivors are **logged as shadows** by `models/shadow.py`. `predict_upcoming`
adds `p_team_a_win_ensemble` and `p_team_a_win_calibrated` to official fixtures,
and `grade_predictions.py` and the desk's live panel grade them against Elo:

* **Fast/slow ensemble**: 0.7 x logit(Elo K=16) + 0.3 x logit(Elo K=256). It
  wins every walk-forward fold (0.6488 vs 0.6567), and 82% of 330 nearby
  settings gain held-out. The pre-registered pick is only t = +1.70 on 2025+26,
  and +0.69 on 2026 alone.
* **Online shrink**: `sigmoid(a * logit(p))` with `a` refit on the trailing 500
  scored Tier-1 forecasts (t = +1.21).

Do not retune shadow settings against the live log. At a ~0.007/match gain,
t = 2 needs ~1,500 graded matches, so the live log is a guard against
regression, not a significance test. **The promotion rule is fixed in advance**
in `docs/model-lab-2026-09-24.md` section 3. Checkpoint 1 is after the
Champions 2026 final (promote if the ensemble is no worse than Elo, n ≥ 25);
checkpoint 2 is at 300 graded matches. Apply it as written.

`scripts/matchday.sh` runs `vct update` plus grading every 2h from blabbleu's
crontab (flock-guarded, skips if vlrggapi is down, stops itself after
2027-12-31). Output goes to `data/interim/matchday.log`.

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
production baseline.

**Glicko-1 was rejected** (`scripts/benchmark_glicko.py`). Tuned on 2024 Tier-1
(best: `c=0, season_c=100, initial_rd=75`), it scored **0.6462** on 2025 versus
Elo's **0.6485** (`t = +0.51`). A narrower grid scored worse on 2024 but better
on 2025 (0.6424, `t = +1.85`): extra tuning overfit the tuning year. The winning
settings contradict the motivation -- new teams did best with a *low* starting
RD; the small gain came from widening RD at season boundaries instead.

Roster-triggered RD widening (`roster_c * churn`, churn = new share of the
lineup) was then tested as the real cause of the season effect. On 2025:
season-only 0.6462 (`t = +0.51`), roster-only 0.6452 (`t = +0.57`), both
**0.6428** (`t = +1.27`). Roster turnover explains the season gain at least as
well as the calendar does, but no variant clears significance, and every best
setting sat at a grid edge. 2025 has now been consulted repeatedly, so it is
no longer a clean holdout. The combined setting was therefore locked
(`season_c=100, roster_c=100, initial_rd=75`) and scored once on untouched 2026
Tier-1: **0.6670 vs Elo 0.6681, `t = +0.26`** (after the team-ID fix below).
Rejected; raw Elo stays.

**2026 looked much harder (Elo 0.6739 vs 0.6485 in 2025) — mostly a data bug.**
The event feed carries team names only, so vlr.gg names that drifted from the
Kaggle ones ("NRG" vs "NRG Esports", "ENVY" vs "Envy") became separate
1500-rated `name:` teams: 118 of 588 2026 matches, at 0.7037 loss.
`load_vlrgg_match_details` now resolves NULL team IDs from detail payloads
(`scripts/diagnose_2026.py` is the analysis). The remaining gap is real:
2026 has more upsets (39.5% vs 36.7%) despite Elo being *less* confident,
concentrated in teams with 50+ prior matches. Every year up to 2026 has now been
used for selection -- the live prediction log is the only clean test left.

The split recurred: by 2026-09-24, 61 Tier-1 names (G2, FPX, NRG, ENVY, JD
Gaming, KIWOOM DRX...) were `name:` keys again across 251 matches since 2023.
**`vct update` now resolves them automatically.** After loading results it
fetches one detail payload per unresolved Tier-1 name
(`normalize.unresolved_team_detail_targets`) and reruns
`load_vlrgg_match_details`. Tier-1 name keys since 2023 are at 0. 2026 Elo
improved 0.6736 -> 0.6674 (t = +1.17), and NRG's first live forecast moved
from 75% to 53% (the market price was 50.5%).

**One-parameter calibration is not yet proven** (`scripts/benchmark_calibration.py`).
`p' = sigmoid(a * logit(p))`, with `a` fit on the previous year only. The
hindsight-best `a` drifts by era: 2021 2.00, 2022 1.44, 2023 1.10, 2024 0.76,
2025 0.76, 2026 0.70. So Elo was underconfident before the 2023 league
restructure and has been overconfident since, which explains the logistic
rejection above. Scores: 2024 fit on 2023 `a=1.10`, **worse** (0.6558 vs
0.6522, `t = -1.99`); 2025 `a=0.76` (0.6444 vs 0.6485, `t = +1.03`); 2026
`a=0.76` (0.6634 vs 0.6681, `t = +1.39`). Two post-restructure years help but
neither clears t ≈ 2. Revisit once the live log is large; do not ship yet.

**Per-region Elo offsets were rejected** (`scripts/benchmark_regions.py`).
Offsets learned online from international results only, added to both teams'
ratings at Masters/Champions. Tuned on 2023-24 international matches (n=135),
k=0 won outright and every k>0 was worse; learned offsets peaked at about
±14 Elo points. International matches are only slightly harder than regional
ones across 2023-26 (0.667 vs 0.645) with the same upset rate. The 2025
international loss of 0.692 was 76 matches of noise. Check a group across
all years before building a fix for it. For the product slice, ingest upcoming official Tier-1
matches, resolve their teams, replay ratings, and emit raw Elo probabilities.
