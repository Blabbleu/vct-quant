"""The placeholder audit scores aligned later matches, never the invalid rows."""
import pandas as pd
import pytest

from scripts.placeholder_scoring import scored_replays


def test_scored_replays_only_known_later_tier1_winners_in_fixed_years():
    history = pd.DataFrame([
        (10, 1, 2024, 'a', 'tbd', 1., 2., 0.),
        (11, 1, 2025, 'a', 'b', 1., 2., 0.),
        (12, 2, 2025, 'a', 'b', 1., 2., 0.),
        (13, 1, 2026, 'b', 'a', 0.5, 1., 1.),
        (14, 1, 2026, 'b', 'a', 0., 0., 2.),
        (15, 1, 2024, 'b', 'a', 1., 2., 0.),
    ], columns=['match_id', 'tier', 'year', 'team_a', 'team_b',
                'score_a', 'maps_a', 'maps_b'])
    history['team_a_name'] = history.team_a
    history['team_b_name'] = history.team_b
    rows = scored_replays(history, {10})
    assert rows.match_id.tolist() == [11, 14]
    assert rows.y.tolist() == [1., 0.]
    assert rows.p_current.between(0, 1).all()
    assert rows.p_without.between(0, 1).all()
    assert rows.loc[rows.match_id.eq(11), 'p_current'].item() != rows.loc[
        rows.match_id.eq(11), 'p_without'].item()


def test_scored_replays_rejects_absent_exclusion():
    history = pd.DataFrame({'match_id': [10]})
    with pytest.raises(ValueError, match='not in history'):
        scored_replays(history, {99})
