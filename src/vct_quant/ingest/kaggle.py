"""Download/refresh the Kaggle VCT dataset (scraped from vlr.gg, 2021-2026).

Uses the kaggle CLI via subprocess (importing the kaggle package authenticates
on import, which breaks when credentials are absent). Credentials live in
%USERPROFILE%/.kaggle/kaggle.json — see https://www.kaggle.com/settings.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from ..config import RAW_KAGGLE_DIR, SETTINGS

DATASET: str = SETTINGS["kaggle"]["dataset"]


def download(dest: Path = RAW_KAGGLE_DIR) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["kaggle", "datasets", "download", "-d", DATASET, "-p", str(dest), "--unzip"],
        check=True,
    )


def list_csvs(root: Path = RAW_KAGGLE_DIR) -> list[Path]:
    return sorted(root.rglob("*.csv"))
