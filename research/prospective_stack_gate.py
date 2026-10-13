"""Read-only prospective scoring of externally captured frozen-stack forecasts."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

CUTOFF = pd.Timestamp('2026-10-13T04:00:00Z')
SEED = 20261013
RESAMPLES = 10_000
MIN_FIXTURES = 150
COLUMNS = ('match_id', 'captured_at', 'kickoff_at', 'team_a_id', 'team_b_id', 'p_stack', 'p_elo')


def _ids(values: pd.Series, name: str) -> pd.Series:
    """Preserve nullable integer IDs from DuckDB's float-backed LEFT JOIN results."""
    result = []
    for value in values:
        if pd.isna(value):
            result.append(pd.NA)
        elif isinstance(value, (int, np.integer)) and not isinstance(value, (bool, np.bool_)):
            result.append(int(value)) if value > 0 else _bad_id(name)
        elif isinstance(value, (float, np.floating)):
            if not math.isfinite(value) or value <= 0 or value > 2**53 or not value.is_integer():
                _bad_id(name)
            result.append(int(value))
        elif isinstance(value, str) and value.isdecimal() and int(value) > 0:
            result.append(int(value))
        else:
            _bad_id(name)
    return pd.Series(pd.array(result, dtype='Int64'), index=values.index)


def _bad_id(name: str) -> None:
    raise ValueError(f'invalid or fractional {name}')


def _times(values: pd.Series, name: str) -> pd.Series:
    # UTC is mandatory in the external snapshot, including when pandas parses it.
    for value in values.dropna():
        if pd.Timestamp(value).tzinfo is None:
            raise ValueError(f'{name} must carry a UTC timezone')
    return pd.to_datetime(values, utc=True, errors='raise')


def read_forecasts(path: str | Path) -> pd.DataFrame:
    return validate_forecasts(pd.read_csv(path))


def validate_forecasts(frame: pd.DataFrame) -> pd.DataFrame:
    if not set(COLUMNS).issubset(frame):
        raise ValueError(f'forecast columns required: {COLUMNS}')
    out = frame.loc[:, COLUMNS].copy()
    for name in ('match_id', 'team_a_id', 'team_b_id'):
        out[name] = _ids(out[name], name)
        if out[name].isna().any():
            raise ValueError(f'null {name} in forecast')
    if out.match_id.duplicated().any():
        raise ValueError('duplicate or revised match_id in forecast snapshot')
    if (out.team_a_id == out.team_b_id).any():
        raise ValueError('identical forecast teams')
    for name in ('captured_at', 'kickoff_at'):
        out[name] = _times(out[name], name)
        if out[name].isna().any():
            raise ValueError(f'null {name} in forecast')
    for name in ('p_stack', 'p_elo'):
        out[name] = pd.to_numeric(out[name], errors='raise')
        if not np.isfinite(out[name]).all() or not out[name].between(0, 1).all():
            raise ValueError(f'invalid {name}')
    return out


def load_settlements(db_path: str | Path) -> pd.DataFrame:
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        return con.execute('''
            SELECT m.match_id, m.event_id, e.tier, m.scheduled_at, m.completed_at,
                   a.team_id AS db_team_a_id, b.team_id AS db_team_b_id,
                   a.is_winner AS a_won, b.is_winner AS b_won
            FROM match m
            LEFT JOIN event e ON e.event_id = m.event_id
            LEFT JOIN match_team a ON a.match_id = m.match_id AND a.team_number = 1
            LEFT JOIN match_team b ON b.match_id = m.match_id AND b.team_number = 2
        ''').df()
    finally:
        con.close()


def prepare(forecasts: pd.DataFrame, settlements: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    f = validate_forecasts(forecasts)
    s = settlements.copy()
    required = ('match_id', 'event_id', 'tier', 'scheduled_at', 'completed_at',
                'db_team_a_id', 'db_team_b_id', 'a_won', 'b_won')
    if not set(required).issubset(s):
        raise ValueError('settlement columns missing')
    for name in ('match_id', 'event_id', 'db_team_a_id', 'db_team_b_id'):
        s[name] = _ids(s[name], name)
    if s.match_id.isna().any() or s.match_id.duplicated().any():
        raise ValueError('null or duplicate settlement match_id')
    for name in ('scheduled_at', 'completed_at'):
        s[name] = pd.to_datetime(s[name], utc=True, errors='raise')
    admitted = f.loc[(f.captured_at > CUTOFF) & (f.captured_at < f.kickoff_at)].copy()
    joined = admitted.merge(s, on='match_id', how='left', validate='one_to_one', indicator=True)
    # A populated DB schedule is authoritative for contradiction detection; a null
    # schedule is common in the copied historical harvest and is unknown, not false.
    schedule_ok = joined.scheduled_at.isna() | joined.scheduled_at.eq(joined.kickoff_at)
    completion_ok = joined.completed_at.notna() & joined.completed_at.ge(joined.kickoff_at) & joined.completed_at.ge(joined.captured_at)
    orientation_ok = joined.db_team_a_id.eq(joined.team_a_id).fillna(False) & joined.db_team_b_id.eq(joined.team_b_id).fillna(False)
    tier = pd.to_numeric(joined.tier, errors='coerce')
    tier_ok = tier.eq(1)
    decisive = joined.a_won.eq(True).fillna(False) & joined.b_won.eq(False).fillna(False) | joined.a_won.eq(False).fillna(False) & joined.b_won.eq(True).fillna(False)
    eligible = joined.loc[schedule_ok & completion_ok & orientation_ok & tier_ok & decisive].copy()
    eligible['y'] = eligible.a_won.astype(int)
    eligible['year'] = eligible.kickoff_at.dt.year
    # Missing or contradictory settlement data remains visible to the caller.
    # Known out-of-scope tiers and ties are exclusions; unknown or contradictory
    # join fields are incomplete. Neither is counted as a forecasting loss.
    tie = joined.a_won.notna() & joined.b_won.notna() & ~decisive
    excluded = (tier.notna() & ~tier_ok) | (tier_ok & tie)
    incomplete = ~excluded & (~(schedule_ok & completion_ok & orientation_ok) | tier.isna() | joined._merge.ne('both'))
    reason = {'submitted': len(f), 'prestart': len(admitted), 'scored': len(eligible),
              'excluded': int(excluded.sum()), 'incomplete': int(incomplete.sum())}
    return eligible, reason


def _model(y: np.ndarray, p: np.ndarray) -> dict:
    loss = -y * np.log(np.clip(p, 1e-15, 1)) - (1-y) * np.log(np.clip(1-p, 1e-15, 1))
    bins = np.minimum((p * 10).astype(int), 9)
    reliability = []
    for i in range(10):
        mask = bins == i
        n = int(mask.sum())
        reliability.append({'bin': i, 'n': n, 'forecast': float(p[mask].mean()) if n else None,
                            'observed': float(y[mask].mean()) if n else None})
    ece = sum(r['n'] * abs(r['forecast'] - r['observed']) for r in reliability if r['n']) / len(y)
    return {'log_loss': float(loss.mean()), 'brier': float(np.mean((p-y)**2)),
            'accuracy': float(np.mean((p >= .5) == y)), 'ece': float(ece),
            'reliability': reliability}, loss


def cluster_interval(delta: np.ndarray, keys: list[str], *, seed: int = SEED,
                     resamples: int = RESAMPLES) -> list[float] | None:
    groups: dict[str, list[float]] = {}
    for key, value in zip(keys, delta, strict=True):
        groups.setdefault(key, []).append(float(value))
    if len(groups) < 2:
        return None
    totals = np.array([sum(v) for v in groups.values()])
    sizes = np.array([len(v) for v in groups.values()])
    rng = np.random.default_rng(seed)
    draws = rng.integers(len(groups), size=(resamples, len(groups)))
    means = totals[draws].sum(axis=1) / sizes[draws].sum(axis=1)
    return np.percentile(means, [2.5, 97.5]).tolist()


def score(forecasts: pd.DataFrame, settlements: pd.DataFrame) -> dict:
    part, counts = prepare(forecasts, settlements)
    result = {'cutoff': CUTOFF.isoformat(), 'counts': counts, 'years': {},
              'seed': SEED, 'resamples': RESAMPLES, 'promotion': False}
    for year, rows in part.groupby('year', sort=True):
        y = rows.y.to_numpy(float)
        stack, stack_loss = _model(y, rows.p_stack.to_numpy(float))
        elo, elo_loss = _model(y, rows.p_elo.to_numpy(float))
        delta = elo_loss - stack_loss
        sd = float(delta.std(ddof=1)) if len(delta) > 1 else math.nan
        scale = max(1.0, float(np.max(np.abs(delta))))
        paired_t = None if not math.isfinite(sd) or sd <= 1e-12 * scale else float(delta.mean() * math.sqrt(len(delta)) / sd)
        keys = [f'match:{int(mid)}' if pd.isna(eid) else f'event:{int(eid)}'
                for mid, eid in zip(rows.match_id, rows.event_id, strict=True)]
        result['years'][int(year)] = {'n': len(rows), 'event_clusters': len(set(keys)),
                                      'advantage': float(delta.mean()), 'paired_t': paired_t,
                                      'cluster_interval': cluster_interval(delta, keys),
                                      'elo': elo, 'stack': stack}
    years = list(result['years'].values())
    if counts['scored'] < MIN_FIXTURES or counts['incomplete'] or any(r['event_clusters'] < 2 for r in years):
        result['verdict'] = 'PENDING'
    elif all(r['advantage'] > 0 and r['cluster_interval'][0] > 0 and
             r['stack']['ece'] <= r['elo']['ece'] for r in years):
        result['verdict'] = 'SUPPORTING EVIDENCE'
    else:
        result['verdict'] = 'NOT PROVEN'
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('forecast_csv', type=Path)
    parser.add_argument('--db', type=Path, default=Path('data/vct.duckdb'))
    args = parser.parse_args()
    print(json.dumps(score(read_forecasts(args.forecast_csv), load_settlements(args.db)), indent=2, allow_nan=False))


if __name__ == '__main__':
    main()
