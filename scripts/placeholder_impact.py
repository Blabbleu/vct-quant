"""Read-only replay sensitivity to retained Tier-1 completed/TBD rows.

    python -m scripts.placeholder_impact

Counterfactual only: does not alter match_sequence, the DB or primary forecasts.
The existing additive DB can differ from a clean rebuild; this isolates each
retained Tier-1 placeholder rather than treating zero-weight Tier-2 rows as Elo.
"""
from __future__ import annotations

import pandas as pd

from scripts.placeholder_audit import placeholder_rows
from vct_quant import db
from vct_quant.features.build import elo_k, margin_signal, match_sequence
from vct_quant.features.ratings import DEFAULT_BASE, compute_elo


def _replay(history: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    rows, ratings = compute_elo(
        zip(history.match_id, history.team_a, history.team_b, margin_signal(history)),
        k=elo_k(history.tier),
    )
    return pd.DataFrame(rows), ratings


def compare_replays(history: pd.DataFrame, excluded: set[int]) -> tuple[pd.DataFrame, dict]:
    """Later Tier-1 pre-match probability deltas and final Elo deltas by team."""
    missing = excluded - set(history.match_id)
    if missing:
        raise ValueError(f"IDs not in history: {sorted(missing)}")
    if not excluded:
        raise ValueError('at least one excluded match is required')
    baseline, before = _replay(history)
    alternative, after = _replay(history.loc[~history.match_id.isin(excluded)])
    joined = baseline[['match_id', 'p_a_win']].merge(
        alternative[['match_id', 'p_a_win']], on='match_id', validate='one_to_one',
        suffixes=('_current', '_without'),
    ).merge(history[['match_id', 'tier']], on='match_id', validate='one_to_one')
    joined = joined.loc[joined.tier.eq(1) & joined.match_id.gt(max(excluded))].copy()
    joined['abs_delta'] = (joined.p_a_win_current - joined.p_a_win_without).abs()
    deltas = {key: before.get(key, DEFAULT_BASE) - after.get(key, DEFAULT_BASE)
              for key in before.keys() | after.keys()}
    return joined, deltas


def main() -> None:
    with db.connect(read_only=True) as con:
        history = match_sequence(con)
        placeholders = placeholder_rows(con)
    ids = sorted(int(match_id) for match_id in placeholders.loc[
        placeholders.tier.eq(1), 'match_id'
    ])
    print(f"Tier-1 completed/TBD rows in current sequence: {ids}")
    for excluded in ([match_id] for match_id in ids):
        rows, rating_deltas = compare_replays(history, set(excluded))
        changed = rows.loc[rows.abs_delta.gt(1e-12)]
        recent = rows.tail(20)
        nonzero_ratings = {key: delta for key, delta in rating_deltas.items()
                           if abs(delta) > 1e-12}
        print(f"without {excluded}: later Tier-1 n={len(rows)}, changed={len(changed)}, "
              f"mean_abs={rows.abs_delta.mean():.9f}, max_abs={rows.abs_delta.max():.9f}, "
              f"last20_max={recent.abs_delta.max():.9f}")
        top_ratings = sorted(nonzero_ratings.items(), key=lambda item: -abs(item[1]))[:5]
        print(f"  final ratings changed={len(nonzero_ratings)}, "
              f"max_abs={max(map(abs, nonzero_ratings.values()), default=0):.6f}; "
              f"top ratings={top_ratings}; "
              f"top matches={changed.nlargest(3, 'abs_delta')[['match_id','abs_delta']].to_dict('records')}")
    print('No DB writes; any primary Elo correction requires separate approval.')


if __name__ == '__main__':
    main()
