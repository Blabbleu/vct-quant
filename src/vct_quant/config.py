"""Project paths and settings.

The project root is resolved relative to this file (editable install), or can
be overridden with the VCT_QUANT_ROOT environment variable.
"""
from __future__ import annotations

import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

PROJECT_ROOT = Path(os.getenv("VCT_QUANT_ROOT", Path(__file__).resolve().parents[2]))

load_dotenv(PROJECT_ROOT / ".env")

with open(PROJECT_ROOT / "config" / "settings.yaml", encoding="utf-8") as f:
    SETTINGS: dict = yaml.safe_load(f)

DATA_DIR = PROJECT_ROOT / SETTINGS["paths"]["data_dir"]
DB_PATH = PROJECT_ROOT / SETTINGS["paths"]["db_path"]
SQL_DIR = PROJECT_ROOT / "sql"

RAW_DIR = DATA_DIR / "raw"
RAW_VLRGG_DIR = RAW_DIR / "vlrgg"
RAW_KAGGLE_DIR = RAW_DIR / "kaggle"
RAW_RIOT_DIR = RAW_DIR / "riot"
INTERIM_DIR = DATA_DIR / "interim"
PROCESSED_DIR = DATA_DIR / "processed"

RIOT_API_KEY = os.getenv("RIOT_API_KEY") or None
