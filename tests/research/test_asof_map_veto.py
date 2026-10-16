"""Synthetic bridge, veto arithmetic, and strictly prior replay checks."""
import math

import pandas as pd

from research.asof_map_veto import build_series, replay


def fixtures():
    matches = pd.DataFrame([
        dict(match_id=mid, team_a="1", team_b="2", team_a_name="Red",
             team_b_name="Blue", maps_a=1, maps_b=0, year=2023, tier=1, score_a=1.0)
        for mid in (10, 20, 30)
    ])
    drafts, scores, ids = [], [], []
    for mid, banned, winner in ((10, "Bind", "Red"), (20, "Haven", "Blue"),
                                (30, "Bind", "Red")):
        common = {"year": 2023, "Tournament": "Event", "Stage": "Final",
                  "Match Type": "Bo3", "Match Name": f"Red vs Blue {mid}"}
        ids.append({**common, "Match ID": mid, "Map": "Bind", "Game ID": mid * 10})
        for team in ("Red", "Blue"):
            drafts.append({**common, "Team": team, "Action": "ban" if team == "Red" else "pick",
                           "Map": banned if team == "Red" else ("Haven" if banned == "Bind" else "Bind")})
        scores.append({**common, "Map": "Bind", "Team A": "Red", "Team B": "Blue",
                       "Team A Score": 13 if winner == "Red" else 10,
                       "Team B Score": 13 if winner == "Blue" else 10})
    return matches, pd.DataFrame(drafts), pd.DataFrame(scores), pd.DataFrame(ids)


def test_current_and_later_drafts_and_results_do_not_change_earlier_features():
    matches, drafts, scores, ids = fixtures()
    series, pools, failures = build_series(matches, drafts, scores, ids)
    assert failures.empty
    original = replay(matches, series, pools)
    assert original.loc[0, "prior_draft_series_a"] == 0
    assert original.loc[1, "prior_draft_series_a"] == 1
    drafts.loc[drafts["Match Name"].eq("Red vs Blue 30"), "Map"] = "Haven"
    scores.loc[scores["Match Name"].eq("Red vs Blue 30"), "Team A Score"] = 2
    revised_series, revised_pools, _ = build_series(matches, drafts, scores, ids)
    revised = replay(matches, revised_series, revised_pools)
    pd.testing.assert_frame_equal(original.iloc[:3], revised.iloc[:3])
    # A changed current result cannot affect that match's own feature either.
    scores.loc[scores["Match Name"].eq("Red vs Blue 20"), "Team A Score"] = 2
    changed_series, changed_pools, _ = build_series(matches, drafts, scores, ids)
    changed = replay(matches, changed_series, changed_pools)
    pd.testing.assert_frame_equal(original.iloc[:2], changed.iloc[:2])


def test_two_map_weighted_edge_and_shrinkage():
    matches, _, _, _ = fixtures()
    # Red banned Bind once; neither Blue series banned a pool map.
    series = {
        10: {0: {"draft": True, "bans": {"Bind"}, "results": [("Haven", 1)]},
             1: {"draft": True, "bans": set(), "results": [("Haven", 0)]}},
        20: {0: {"draft": True, "bans": set(), "results": [("Bind", 0)]},
             1: {"draft": True, "bans": set(), "results": [("Bind", 1)]}},
    }
    result = replay(matches, series, {30: frozenset({"Bind", "Haven"})})
    assert result.loc[2, "prior_draft_series_a"] == 2
    assert result.loc[2, "prior_draft_series_b"] == 2
    # Bind weight .5 and difference -1/6; Haven weight 1 and difference +1/6.
    assert math.isclose(result.loc[2, "veto_edge"], 1 / 18, abs_tol=1e-12)


def test_ambiguous_bridge_is_excluded_and_duplicate_rows_drop():
    matches, drafts, scores, ids = fixtures()
    drafts = pd.concat([drafts, drafts.iloc[[0]]], ignore_index=True)
    ids = pd.concat([ids, ids.iloc[[0]].assign(**{"Match ID": 99})], ignore_index=True)
    series, _, failures = build_series(matches, drafts, scores, ids)
    assert 10 not in series
    assert "ambiguous_id_bridge" in set(failures.reason)
