"""Pre-match opening/latest-observed market diagnostics."""
import pandas as pd
import pytest

from scripts.market_history import observed_pairs


def test_observed_pairs_keep_first_and_last_liquid_pre_match_quotes():
    start = pd.Timestamp('2026-09-26 12:00', tz='UTC')
    log = pd.DataFrame([
        dict(match_id=1, predicted_at=start - pd.Timedelta(days=3), scheduled_at=start,
             team_a_id=10, team_a_key='id:10', team_b_key='id:20',
             team_a_name='Alpha', team_b_name='Bravo', market_slug='alpha-bravo',
             p_market_a=.4, market_spread=.02, p_team_a_win=.55),
        dict(match_id=1, predicted_at=start - pd.Timedelta(days=1), scheduled_at=start,
             team_a_id=10, team_a_key='id:10', team_b_key='id:20',
             team_a_name='Alpha', team_b_name='Bravo', market_slug='alpha-bravo',
             p_market_a=.9, market_spread=.12, p_team_a_win=.56),
        dict(match_id=1, predicted_at=start - pd.Timedelta(hours=2), scheduled_at=start,
             team_a_id=10, team_a_key='id:10', team_b_key='id:20',
             team_a_name='Alpha', team_b_name='Bravo', market_slug='alpha-bravo',
             p_market_a=.6, market_spread=.02, p_team_a_win=.57),
        dict(match_id=1, predicted_at=start + pd.Timedelta(hours=1), scheduled_at=start,
             team_a_id=10, team_a_key='id:10', team_b_key='id:20',
             team_a_name='Alpha', team_b_name='Bravo', market_slug='alpha-bravo',
             p_market_a=.7, market_spread=.02, p_team_a_win=.58),
    ])
    results = pd.DataFrame([{'match_id': 1, 'team_id': 10, 'team_name': 'Alpha',
                             'is_winner': True}])
    out = observed_pairs(log, results)
    assert len(out) == 1
    row = out.iloc[0]
    assert row.y == 1
    assert row.p_market_open == pytest.approx(.4)
    assert row.p_market_latest == pytest.approx(.6)
    assert row.p_elo_open == pytest.approx(.55)
    assert row.p_elo_latest == pytest.approx(.57)
    assert row.latest_hours_to_start == pytest.approx(2)


def test_observed_pairs_exclude_ambiguous_market_and_team_orientation():
    start = pd.Timestamp('2026-09-26 12:00', tz='UTC')
    records = []
    for mid, second_slug, second_team in [(1, 'different', 'id:20'), (2, 'same', 'id:10')]:
        for hours, slug, team in [(4, 'same', 'id:20'), (2, second_slug, second_team)]:
            records.append(dict(match_id=mid, predicted_at=start - pd.Timedelta(hours=hours),
                                scheduled_at=start, team_a_id=10, team_a_key='id:10',
                                team_b_key=team, team_a_name='Alpha', team_b_name='Bravo',
                                market_slug=slug, p_market_a=.5, market_spread=.01,
                                p_team_a_win=.5))
    results = pd.DataFrame([{'match_id': mid, 'team_id': 10, 'team_name': 'Alpha',
                             'is_winner': True} for mid in (1, 2)])
    assert observed_pairs(pd.DataFrame(records), results).empty
