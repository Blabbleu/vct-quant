# vct-quant

Match prediction quant model for the Valorant Champions Tour (VCT).

## Data sources

| Source | Role | Where |
| --- | --- | --- |
| [Kaggle VCT dataset](https://www.kaggle.com/datasets/ryanluong1/valorant-champion-tour-2021-2023-data) | Historical training corpus (2021–2026, scraped from vlr.gg) | `data/raw/kaggle/` |
| [vlrggapi](https://vlrggapi.vercel.app) (unofficial vlr.gg API) | Keeping the DB current going forward | `data/raw/vlrgg/` |
| Riot official API | Optional: pro players' ranked-queue form. **Not** a source of VCT pro matches (tournament realm is not public; VAL-MATCH-V1 needs an approved production key) | `data/raw/riot/` |

## Setup

```powershell
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
vct init-db          # create data/vct.duckdb from sql/schema.sql
vct download-kaggle  # needs %USERPROFILE%\.kaggle\kaggle.json
vct inspect-kaggle   # see the CSV layout before writing ETL loaders
vct load-kaggle      # load the historical corpus
python scripts/backfill_vlrgg.py --pages 12
vct load-vlrgg       # merge the harvested vlr.gg event matches
python scripts/backfill_promoted_details.py  # Tier-2 player form for promoted teams
vct load-vlrgg-details
vct ingest-vlrgg     # fetch the latest shallow results feed
python -m vct_quant.features.build
python scripts/benchmark_baseline.py
python scripts/benchmark_gradient_boosting.py
```

## Pipeline

```
data/raw  →  ETL (normalize + entity resolution)  →  DuckDB canonical tables
          →  features (Elo, rolling form; point-in-time only)  →  data/processed
          →  models (baseline: margin-aware Elo)
          →  eval (walk-forward backtest; log loss, Brier, calibration)
```

Ground rules that keep the model honest:

* **No leakage** — every feature for a match uses only data available before
  that match started. `features/` is built around pre-match snapshots.
* **Temporal validation only** — `eval/backtest.py` trains on the past and
  tests on the future; random splits are banned.
* **Official competition only** — Tier 1 is the prediction target. Tier 2
  (Challengers/VCL and Ascension) is retained as possible evidence for promoted
  teams; Game Changers, Premier, third-party, offseason, and ranked matches are
  excluded from modeling.
* **Raw is immutable** — `data/raw/` is never edited; the DuckDB file is
  disposable and rebuildable (`vct init-db` + replaying ETL).

## Layout

```
config/           settings.yaml (URLs, paths)
sql/              schema.sql (DuckDB, active) · schema.postgres.sql (reference)
src/vct_quant/
  ingest/         source adapters → data/raw (vlrgg, kaggle, riot)
  etl/            raw → canonical tables; entity resolution across sources
  features/       Elo, rolling form, feature-matrix assembly
  models/         baseline + future models
  eval/           walk-forward backtesting, calibration metrics
  cli.py          `vct` entrypoint
data/             raw → interim → processed (gitignored)
notebooks/        EDA only — no pipeline logic
tests/
```

## Notes

* DuckDB: single-writer. One pipeline process at a time; notebooks should
  connect `read_only=True`.
