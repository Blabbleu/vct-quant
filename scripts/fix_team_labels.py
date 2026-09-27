"""Apply `normalize.KAGGLE_TEAM_LABEL_FIXES` to an already-loaded database.

    python scripts/fix_team_labels.py            # dry run: print affected rows
    python scripts/fix_team_labels.py --apply    # rewrite them (single writer)

The loader now fixes the labels on read, so a clean `vct load-kaggle` rebuild is
already correct. This script repairs an existing additive DB without a rebuild:
for each (year dir, wrong label -> right label), it moves Kaggle-loaded
`match_team` rows (date_raw = that year) and their `match_map_team_score` rows
from the wrong team ID to the right one, and renames the stored label. Rows from
other years (vct_2021's real Mega Minors) and vlr.gg-loaded rows are untouched.
Idempotent: a second run finds nothing to move. Raw data is never touched.
"""
from __future__ import annotations

import argparse
import sys

import pandas as pd

from vct_quant import db
from vct_quant.config import RAW_KAGGLE_DIR
from vct_quant.etl.normalize import KAGGLE_TEAM_LABEL_FIXES, _unambiguous


def team_ids() -> dict[str, int]:
    raw = pd.read_csv(RAW_KAGGLE_DIR / "all_ids" / "all_teams_ids.csv")
    return _unambiguous(raw, "Team", "Team ID")


def plan(con, ids: dict[str, int]) -> list[dict]:
    out = []
    for year_dir, fixes in KAGGLE_TEAM_LABEL_FIXES.items():
        year = year_dir.removeprefix("vct_")
        for wrong, right in fixes.items():
            wrong_id, right_id = ids[wrong], ids[right]
            rows = con.execute(
                """
                SELECT mt.match_id, mt.team_number, mt.team_name,
                       EXISTS (SELECT 1 FROM match_team o
                               WHERE o.match_id = mt.match_id AND o.team_id = ?) AS clash
                FROM match_team mt JOIN match m USING (match_id)
                WHERE mt.team_id = ? AND m.date_raw = ?
                ORDER BY mt.match_id
                """,
                [right_id, wrong_id, year],
            ).fetchall()
            for match_id, team_number, name, clash in rows:
                out.append(dict(year=year, match_id=match_id, team_number=team_number,
                                name=name, wrong_id=wrong_id, right_id=right_id,
                                right=right, clash=clash))
    return out


def apply(con, rows: list[dict]) -> tuple[int, int]:
    moved = scores = 0
    con.execute("BEGIN")
    try:
        for r in rows:
            con.execute(
                "UPDATE match_team SET team_id = ?, team_name = ? "
                "WHERE match_id = ? AND team_number = ? AND team_id = ?",
                [r["right_id"], r["right"], r["match_id"], r["team_number"], r["wrong_id"]],
            )
            moved += 1
            scores += con.execute(
                "UPDATE match_map_team_score SET team_id = ? WHERE team_id = ? AND "
                "match_map_id IN (SELECT match_map_id FROM match_map WHERE match_id = ?)",
                [r["right_id"], r["wrong_id"], r["match_id"]],
            ).fetchone()[0]
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise
    return moved, scores


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--apply", action="store_true", help="write the fix (default: dry run)")
    args = ap.parse_args(argv)

    ids = team_ids()
    con = db.connect(read_only=not args.apply)
    try:
        rows = plan(con, ids)
        clashes = [r for r in rows if r["clash"]]
        by_year = pd.Series([r["year"] for r in rows], dtype=object).value_counts().to_dict()
        print(f"{len(rows)} match_team rows to move {by_year}; clashes: {len(clashes)}")
        if clashes:
            print("refusing: target team already on the other side of", [r["match_id"] for r in clashes])
            return 1
        if not rows or not args.apply:
            return 0
        moved, scores = apply(con, rows)
        print(f"moved {moved} match_team rows and {scores} match_map_team_score rows")
        left = plan(con, ids)
        print(f"remaining after apply: {len(left)}")
        return 0 if not left else 1
    finally:
        con.close()


if __name__ == "__main__":
    sys.exit(main())
