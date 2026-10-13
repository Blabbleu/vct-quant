"""Prospective cohort and read-only settlement join regression checks."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from research import prospective_stack_gate as gate


def forecast(mid=1, **kw):
    row = dict(match_id=mid, captured_at='2026-10-14T00:00:00Z',
               kickoff_at='2026-10-14T01:00:00Z', team_a_id=11,
               team_b_id=12, p_stack=.7, p_elo=.6)
    row.update(kw)
    return row


def settlement(mid=1, **kw):
    row = dict(match_id=mid, event_id=20, tier=1, scheduled_at=None,
               completed_at='2026-10-14T03:00:00Z', db_team_a_id=11,
               db_team_b_id=12, a_won=True, b_won=False)
    row.update(kw)
    return row


def test_null_schedule_and_nullable_float_ids_score():
    s = pd.DataFrame([settlement()])
    for col in ('match_id', 'event_id', 'db_team_a_id', 'db_team_b_id'):
        s[col] = s[col].astype(float)
    rows, counts = gate.prepare(pd.DataFrame([forecast()]), s)
    assert counts['scored'] == 1
    assert rows.iloc[0].event_id == 20
    assert rows.iloc[0].y == 1


def test_fractional_ids_are_rejected():
    s = pd.DataFrame([settlement(event_id=20.5)])
    with pytest.raises(ValueError, match='fractional event_id'):
        gate.prepare(pd.DataFrame([forecast()]), s)


@pytest.mark.parametrize('f,s', [
    (forecast(captured_at='2026-10-13T04:00:00Z'), settlement()),
    (forecast(captured_at='2026-10-14T01:00:00Z'), settlement()),
    (forecast(), settlement(db_team_a_id=12, db_team_b_id=11)),
    (forecast(), settlement(tier=2)),
    (forecast(), settlement(a_won=False, b_won=False)),
    (forecast(), settlement(completed_at='2026-10-13T23:00:00Z')),
    (forecast(), settlement(scheduled_at='2026-10-14T02:00:00Z')),
])
def test_ineligible_never_scores(f, s):
    result = gate.score(pd.DataFrame([f]), pd.DataFrame([s]))
    assert result['counts']['scored'] == 0
    assert result['verdict'] == 'PENDING'
    assert result['years'] == {}


def test_absent_forecast_and_revisions():
    empty = gate.score(pd.DataFrame(columns=gate.COLUMNS), pd.DataFrame([settlement()]))
    assert empty['counts']['scored'] == 0
    assert empty['verdict'] == 'PENDING' and empty['years'] == {} and not empty['promotion']
    with pytest.raises(ValueError, match='duplicate or revised'):
        gate.prepare(pd.DataFrame([forecast(), forecast(p_stack=.9)]), pd.DataFrame([settlement()]))


def test_null_schedule_future_settlement_and_whole_event_reproducibility():
    forecasts = []
    settlements = []
    for i in range(150):
        event = i // 10
        win = i % 3 != 0
        forecasts.append(forecast(i+1, p_stack=(.72 if i % 5 else .7) if win else .3,
                                  p_elo=.6 if win else .4))
        settlements.append(settlement(i+1, event_id=event+1, a_won=win, b_won=not win))
    f, s = pd.DataFrame(forecasts), pd.DataFrame(settlements)
    a = gate.score(f, s)
    b = gate.score(f, s)
    assert a == b
    row = a['years'][2026]
    assert row['n'] == 150 and row['event_clusters'] == 15
    assert row['cluster_interval'][0] > 0
    assert row['paired_t'] is not None
    assert a['verdict'] == 'SUPPORTING EVIDENCE'
    # Draw event totals [2, -1] and sizes [2, 1], rather than individual rows.
    draws = np.random.default_rng(gate.SEED).integers(2, size=(100, 2))
    expected = np.percentile(np.array([2., -1.])[draws].sum(axis=1) /
                             np.array([2, 1])[draws].sum(axis=1), [2.5, 97.5]).tolist()
    assert gate.cluster_interval(np.array([1., 1., -1.]), ['a', 'a', 'b'], resamples=100) == expected


def test_constant_delta_has_null_t_with_150_rows():
    f = pd.DataFrame([forecast(i+1, p_stack=.7, p_elo=.6) for i in range(150)])
    s = pd.DataFrame([settlement(i+1, event_id=i//10+1) for i in range(150)])
    assert gate.score(f, s)['years'][2026]['paired_t'] is None


def test_single_row_has_null_t_and_no_interval():
    year = gate.score(pd.DataFrame([forecast()]), pd.DataFrame([settlement()]))['years'][2026]
    assert year['paired_t'] is None and year['cluster_interval'] is None


def test_exclusions_and_incomplete_are_separate():
    f = pd.DataFrame([forecast(1), forecast(2), forecast(3)])
    s = pd.DataFrame([settlement(1, tier=2), settlement(2, a_won=False, b_won=False)])
    result = gate.score(f, s)
    assert result['counts'] == {'submitted': 3, 'prestart': 3, 'scored': 0,
                                'excluded': 2, 'incomplete': 1}
    assert result['verdict'] == 'PENDING'


def test_copied_db_schema_join_and_historical_guard():
    from pathlib import Path
    db = Path('data/vct.duckdb')
    if not db.exists():
        pytest.skip('copied DB unavailable')
    rows = gate.load_settlements(db)
    good = rows.loc[rows.db_team_a_id.notna() & rows.db_team_b_id.notna() & rows.completed_at.notna() & rows.scheduled_at.isna()]
    if good.empty:
        pytest.skip('no copied row with complete orientation and null schedule')
    row = good.iloc[0]
    # The real copied row proves exact ID/orientation join. Its historical completion
    # must prevent a fabricated post-cutoff pre-start forecast from scoring.
    fake = pd.DataFrame([forecast(int(row.match_id), team_a_id=int(row.db_team_a_id),
                                  team_b_id=int(row.db_team_b_id))])
    assert int(row.match_id) == int(fake.iloc[0].match_id)
    assert int(row.db_team_a_id) == int(fake.iloc[0].team_a_id)
    assert int(row.db_team_b_id) == int(fake.iloc[0].team_b_id)
    joined, counts = gate.prepare(fake, rows)
    assert counts['prestart'] == 1
    assert counts['scored'] == 0
    assert joined.empty
