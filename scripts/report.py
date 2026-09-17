"""Bake the dashboard into one standalone file: data/processed/report.html.

    python scripts/report.py          # after `vct update`

Same payload the API serves (`vct_quant.dashboard.snapshot`), embedded as JSON so
the file opens with no server -- which is what the published artifact needs, since
an artifact cannot reach localhost. For the live version, run `vct serve`.
"""
from __future__ import annotations

import json
from pathlib import Path

from vct_quant.config import PROCESSED_DIR
from vct_quant.dashboard import snapshot

PAGE = Path(__file__).resolve().parents[1] / "frontend" / "index.html"


def main() -> None:
    data = snapshot()
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    path = PROCESSED_DIR / "report.html"
    html = PAGE.read_text(encoding="utf-8").replace(
        "__DATA__", json.dumps(data, separators=(",", ":"))
    )
    path.write_text(html, encoding="utf-8")
    print(f"{len(html):,} bytes -> {path}")
    print(f"  {len(data['fixtures'])} fixtures, {data['live']['graded']} graded, "
          f"backtest log loss {data['backtest']['log_loss']:.4f}")


if __name__ == "__main__":
    main()
