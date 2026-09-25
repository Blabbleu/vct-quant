"""Read-only impact of each retained Tier-1 completed/TBD match."""
import pandas as pd
import pytest

from scripts.placeholder_impact import compare_replays


def test_compare_replays_removes_only_requested_match_and_aligns_by_id():
    history = pd.DataFrame([
        (10, 1, 'a', 'tbd', 1., 2., 0.),
        (11, 2, 'a', 'b', 1., 2., 0.),
        (12, 1, 'a', 'b', 1., 2., 0.),
        (13, 1, 'a', 'b', 0., 0., 2.),
    ], columns=['match_id', 'tier', 'team_a', 'team_b', 'score_a', 'maps_a', 'maps_b'])
    rows, ratings = compare_replays(history, {10})
    assert rows.match_id.tolist() == [12, 13]
    assert (rows.abs_delta > 0).all()
    assert ratings['a'] != 0
    assert ratings['tbd'] != 0
    # Tier-2 removal carries K=0; it cannot affect official Elo.
    zero_rows, zero_ratings = compare_replays(history, {11})
    assert zero_rows.abs_delta.eq(0).all()
    assert all(v == 0 for v in zero_ratings.values())


def test_compare_replays_refuses_nonexistent_ids():
    history = pd.DataFrame([
        (10, 1, 'a', 'b', 1., 2., 0.),
    ], columns=['match_id', 'tier', 'team_a', 'team_b', 'score_a', 'maps_a', 'maps_b'])
    with pytest.raises(ValueError, match='not in history'):
        compare_replays(history, {99})
