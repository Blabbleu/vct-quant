"""Read-only paired 2025–26 diagnostic for retained completed/TBD Tier-1 rows.

    python -m scripts.placeholder_scoring

See docs/placeholder-sensitivity.md for the frozen comparison rule. This is
not a production-scope change and does not write the database.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from scripts.placeholder_audit import placeholder_rows
from scripts.placeholder_impact import _replay
from vct_quant import db
from vct_quant.features.build import match_sequence


def scored_replays(history: pd.DataFrame, excluded: set[int]) -> pd.DataFrame:
    """Paired pre-match probabilities on later, resolved Tier-1 2025–26 games."""
    if not excluded or excluded - set(history.match_id):
        raise ValueError(f"IDs not in history: {sorted(excluded - set(history.match_id))}")
    current, _ = _replay(history)
    without, _ = _replay(history.loc[~history.match_id.isin(excluded)])
    paired = current[['match_id', 'p_a_win']].merge(
        without[['match_id', 'p_a_win']], on='match_id',
        validate='one_to_one', suffixes=('_current', '_without'),
    ).merge(history[['match_id', 'tier', 'year', 'score_a',
                     'team_a_name', 'team_b_name']],
            on='match_id', validate='one_to_one')
    paired = paired.loc[
        paired.match_id.gt(max(excluded)) & paired.tier.eq(1)
        & paired.year.isin((2025, 2026)) & paired.score_a.isin((0., 1.))
        & ~paired.team_a_name.str.fullmatch('TBD', case=False, na=False)
        & ~paired.team_b_name.str.fullmatch('TBD', case=False, na=False)
    ].copy()
    return paired.rename(columns={'score_a': 'y', 'p_a_win_current': 'p_current',
                                  'p_a_win_without': 'p_without'})


def summary(rows: pd.DataFrame) -> dict:
    """Positive paired t favors exclusion; a zero-variance delta has no t."""
    y = rows.y.to_numpy(dtype=float)
    cur = np.clip(rows.p_current.to_numpy(dtype=float), 1e-12, 1-1e-12)
    alt = np.clip(rows.p_without.to_numpy(dtype=float), 1e-12, 1-1e-12)
    loss = lambda p: -(y * np.log(p) + (1-y) * np.log(1-p))
    d = loss(cur) - loss(alt)
    sd = d.std(ddof=1) if len(d) > 1 else float('nan')
    return {'n': len(rows), 'current_loss': float(loss(cur).mean()),
            'without_loss': float(loss(alt).mean()),
            'paired_t': float(d.mean() / (sd / np.sqrt(len(d)))) if sd > 0 else None,
            'max_abs_delta': float(np.max(np.abs(cur-alt))) if len(d) else None}


def main() -> None:
    with db.connect(read_only=True) as con:
        history = match_sequence(con)
        placeholders = placeholder_rows(con)
    excluded = set(int(x) for x in placeholders.loc[placeholders.tier.eq(1), 'match_id'])
    if excluded != {10802, 97028}:
        raise ValueError(f"unexpected Tier-1 placeholder set: {sorted(excluded)}")
    rows = scored_replays(history, excluded)
    print(f"Excluded={sorted(excluded)}; 2025-26 scored rows: {summary(rows)}")
    print('Read-only retrospective; not an untouched holdout or production change.')


if __name__ == '__main__':
    main()
