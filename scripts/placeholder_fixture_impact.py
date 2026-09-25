"""Read-only Elo sensitivity for *future fixtures in the existing local cache*.

    python -m scripts.placeholder_fixture_impact

This recomputes raw primary Elo from the current additive DB snapshot and each
independent Tier-1 placeholder exclusion. It never changes the DB, cache,
model, or production predictions. The fixture cache may be stale when the
source is down; output is a counterfactual, not a live forecast observation.
"""
from __future__ import annotations

import pandas as pd

from scripts.placeholder_audit import placeholder_rows
from scripts.placeholder_impact import _replay
from vct_quant import db
from vct_quant.config import PROCESSED_DIR
from vct_quant.features.build import match_sequence
from vct_quant.features.ratings import DEFAULT_BASE, expected_score

_COLUMNS = ['match_id', 'scheduled_at', 'team_a_name', 'team_b_name',
            'excluded_id', 'p_current', 'p_without', 'abs_delta',
            'team_a_rating_delta', 'team_b_rating_delta']


def fixture_counterfactuals(history: pd.DataFrame, fixtures: pd.DataFrame,
                            excluded_ids: list[int], *, now: pd.Timestamp) -> pd.DataFrame:
    """Pair independently excluded historical IDs on future known Tier-1 teams."""
    missing = set(excluded_ids) - set(history.match_id)
    if missing:
        raise ValueError(f"IDs not in history: {sorted(missing)}")
    starts = pd.to_datetime(fixtures.scheduled_at, utc=True, errors='coerce')
    eligible = fixtures.loc[
        starts.gt(now) & fixtures.tier.eq(1)
        & fixtures.team_a_name.str.casefold().ne('tbd')
        & fixtures.team_b_name.str.casefold().ne('tbd')
    ].copy()
    if eligible.empty or not excluded_ids:
        return pd.DataFrame(columns=_COLUMNS)
    _, current = _replay(history)
    rows = []
    for excluded_id in excluded_ids:
        _, without = _replay(history.loc[history.match_id.ne(excluded_id)])
        for fixture in eligible.itertuples(index=False):
            a, b = fixture.team_a_key, fixture.team_b_key
            p_current = expected_score(current.get(a, DEFAULT_BASE),
                                       current.get(b, DEFAULT_BASE))
            p_without = expected_score(without.get(a, DEFAULT_BASE),
                                       without.get(b, DEFAULT_BASE))
            rows.append({
                'match_id': fixture.match_id,
                'scheduled_at': fixture.scheduled_at,
                'team_a_name': fixture.team_a_name,
                'team_b_name': fixture.team_b_name,
                'excluded_id': excluded_id,
                'p_current': p_current,
                'p_without': p_without,
                'abs_delta': abs(p_current - p_without),
                'team_a_rating_delta': current.get(a, DEFAULT_BASE) - without.get(a, DEFAULT_BASE),
                'team_b_rating_delta': current.get(b, DEFAULT_BASE) - without.get(b, DEFAULT_BASE),
            })
    return pd.DataFrame(rows, columns=_COLUMNS)


def main() -> None:
    cache = PROCESSED_DIR / 'upcoming_tier1.parquet'
    if not cache.exists():
        print(f'No local fixture cache: {cache}; no live request or output')
        return
    fixtures = pd.read_parquet(cache)
    with db.connect(read_only=True) as con:
        history = match_sequence(con)
        placeholders = placeholder_rows(con)
    ids = sorted(int(value) for value in placeholders.loc[
        placeholders.tier.eq(1), 'match_id'])
    now = pd.Timestamp.now(tz='UTC')
    result = fixture_counterfactuals(history, fixtures, ids, now=now)
    file_mtime = pd.Timestamp(cache.stat().st_mtime, unit='s', tz='UTC')
    print(f'Local cache file mtime {file_mtime.isoformat()} (may be copy time, '
          f'NOT source fetch time); audited at {now.isoformat()}; '
          f'cache rows={len(fixtures)}, future known Tier-1 fixtures={result.match_id.nunique()}, '
          f'independent exclusions={ids}')
    if result.empty:
        print('No eligible future fixture counterfactual. Cache may be stale.')
    else:
        if 'p_team_a_win' in fixtures:
            paired = result.drop_duplicates('match_id').merge(
                fixtures[['match_id', 'p_team_a_win']], on='match_id', validate='one_to_one')
            max_disagreement = (paired.p_current - paired.p_team_a_win).abs().max()
            print(f'Max abs recomputed-vs-cached primary probability: {max_disagreement:.9f}')
            if max_disagreement > 1e-6:
                print('WARNING: cached forecasts differ from snapshot replay; '
                      'do not interpret these as changes to the cached output.')
        print(result.to_string(index=False, float_format=lambda value: f'{value:.9f}'))
    print('Read-only recomputation from local fixtures; not live forecasts or a primary model change.')


if __name__ == '__main__':
    main()
