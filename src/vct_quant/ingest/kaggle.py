"""Download/refresh the Kaggle VCT dataset (scraped from vlr.gg, 2021-2026).

Uses the kaggle CLI via subprocess (importing the kaggle package authenticates
on import, which breaks when credentials are absent). Credentials come from
%USERPROFILE%/.kaggle/access_token or .kaggle/kaggle.json — see
https://www.kaggle.com/settings.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from ..config import RAW_KAGGLE_DIR, SETTINGS

DATASET: str = SETTINGS["kaggle"]["dataset"]


def download(dest: Path = RAW_KAGGLE_DIR) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    # `-m kaggle` rather than the `kaggle` console script: the script resolves
    # via PATH and its Windows shim hardcodes the interpreter it was built
    # against, so a moved or copied venv fails silently with exit 1.
    subprocess.run(
        [sys.executable, "-m", "kaggle",
         "datasets", "download", "-d", DATASET, "-p", str(dest), "--unzip"],
        check=True,
    )


def list_csvs(root: Path = RAW_KAGGLE_DIR) -> list[Path]:
    return sorted(root.rglob("*.csv"))
