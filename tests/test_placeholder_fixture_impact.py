"""A read-only diagnostic must not confuse stale cache with a live forecast."""
import pandas as pd

from scripts.placeholder_fixture_impact import fixture_counterfactuals


def test_fixture_counterfactuals_scopes_future_tier1_known_teams_and_computes_each_id():
    history = pd.DataFrame([
        (10, 1, 'a', 'tbd', 1., 2., 0.),
        (11, 1, 'a', 'c', 0., 2., 0.),
    ], columns=['match_id', 'tier', 'team_a', 'team_b', 'score_a', 'maps_a', 'maps_b'])
    fixtures = pd.DataFrame([
        (30, '2026-10-01T00:00:00Z', 1, 'a', 'c', 'A', 'C'),
        (31, '2026-09-01T00:00:00Z', 1, 'a', 'c', 'A', 'C'),
        (32, '2026-10-01T00:00:00Z', 3, 'a', 'c', 'A', 'C'),
        (33, '2026-10-01T00:00:00Z', 1, 'a', 'tbd', 'A', 'TBD'),
        (34, 'TBD', 1, 'a', 'c', 'A', 'C'),
    ], columns=['match_id', 'scheduled_at', 'tier', 'team_a_key', 'team_b_key',
                'team_a_name', 'team_b_name'])
    out = fixture_counterfactuals(history, fixtures, [10, 11],
                                  now=pd.Timestamp('2026-09-25T09:00:00Z'))
    assert out.match_id.tolist() == [30, 30]
    assert out.excluded_id.tolist() == [10, 11]
    assert out.loc[out.excluded_id.eq(10), 'abs_delta'].iloc[0] > 0
    assert out.loc[out.excluded_id.eq(11), 'abs_delta'].iloc[0] > 0
    assert out['p_current'].between(0, 1).all()
    assert out['p_without'].between(0, 1).all()


def test_fixture_counterfactuals_refuses_missing_history_id():
    history = pd.DataFrame([(10, 1, 'a', 'b', 1., 2., 0.)],
                           columns=['match_id', 'tier', 'team_a', 'team_b',
                                    'score_a', 'maps_a', 'maps_b'])
    fixtures = pd.DataFrame(columns=['match_id', 'scheduled_at', 'tier', 'team_a_key',
                                     'team_b_key', 'team_a_name', 'team_b_name'])
    import pytest
    with pytest.raises(ValueError, match='not in history'):
        fixture_counterfactuals(history, fixtures, [99],
                                now=pd.Timestamp('2026-09-25T09:00:00Z'))
