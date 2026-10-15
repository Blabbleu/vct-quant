from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from research.asof_player_form import replay, coverage


def fixture():
    matches = pd.DataFrame([
        (1, 1, 2023, "1", "2", 1.0),
        (2, 1, 2023, "2", "1", 0.0),
        (3, 1, 2024, "1", "2", 1.0),
    ], columns=["match_id", "tier", "year", "team_a", "team_b", "score_a"])
    identities = []
    stats = []
    for mid in (1, 2, 3):
        for side in (1, 2):
            team = (side if mid != 2 else 3 - side)
            identities.append((mid, mid, side, team, team, f"team{team}"))
            for slot in range(1, 6):
                stats.append((mid, mid, side, slot, f"p{team}_{slot}", float(mid)))
    identities = pd.DataFrame(identities, columns=["match_id", "map_id", "team_number", "score_team_id", "match_team_id", "match_team_name"])
    stats = pd.DataFrame(stats, columns=["match_id", "map_id", "team_number", "player_slot", "player_key", "rating"])
    return matches, identities, stats


def test_asof_ignores_current_players_identity_and_result_but_next_responds():
    m, i, s = fixture()
    base = replay(m, i, s)
    changed_m = m.copy()
    changed_m.loc[1, "score_a"] = 1.0
    changed_s = s.loc[s.match_id.ne(2)].copy()
    changed_i = i.copy()
    changed_i.loc[changed_i.match_id.eq(2) & changed_i.team_number.eq(1), "score_team_id"] = 999
    altered = replay(changed_m, changed_i, changed_s)
    pd.testing.assert_series_equal(base.loc[1], altered.loc[1])
    assert base.loc[2, "player_form_a"] != altered.loc[2, "player_form_a"]
    assert base.loc[1, "prior_lineup_a"] and base.loc[1, "prior_lineup_b"]
    assert base.loc[1, "player_form_a"] == 1.0
    assert base.loc[1, "player_form_b"] == 1.0


def test_incomplete_and_missing_prior_lineups():
    m, i, s = fixture()
    s = s.loc[~((s.match_id == 1) & (s.team_number == 2) & (s.player_slot == 5))]
    out = replay(m, i, s)
    assert not out.loc[0, "prior_lineup_a"]
    assert out.loc[0, "player_form_missing_a"]
    assert out.loc[1, "prior_lineup_b"]  # reversed: B is team 1
    assert not out.loc[1, "prior_lineup_a"]
    assert np.isnan(out.loc[1, "player_form_a"])


def test_duplicate_player_quarantines_only_that_side():
    m, i, s = fixture()
    s.loc[(s.match_id == 1) & (s.team_number == 1) & (s.player_slot == 5), "player_key"] = "p1_4"
    out = replay(m, i, s)
    assert not out.loc[1, "prior_lineup_b"]
    assert out.loc[1, "prior_lineup_a"]


def test_substitution_keeps_previous_lineup_and_valid_map_ratings():
    m, i, s = fixture()
    # Two maps for match 2. Team 1 changes one player between them.
    extra_i = i.loc[i.match_id.eq(2)].copy()
    extra_i["map_id"] = 20
    extra_s = s.loc[s.match_id.eq(2)].copy()
    extra_s["map_id"] = 20
    extra_s.loc[extra_s.player_key.eq("p1_5"), "player_key"] = "new"
    extra_s["rating"] = 9.0
    out = replay(m, pd.concat([i, extra_i]), pd.concat([s, extra_s]))
    assert out.loc[2, "prior_lineup_a"]
    assert out.loc[2, "player_form_a"] == pytest.approx(3.5)


@pytest.mark.parametrize("mutation", ["duplicate", "mismatch", "wrong_key", "invalid_side"])
def test_bad_map_mapping_quarantines_both_sides(mutation):
    m, i, s = fixture()
    if mutation == "duplicate":
        i = pd.concat([i, i.loc[i.match_id.eq(1) & i.team_number.eq(1)]])
    elif mutation == "mismatch":
        i.loc[i.match_id.eq(1) & i.team_number.eq(1), "score_team_id"] = 77
    elif mutation == "wrong_key":
        i.loc[i.match_id.eq(1) & i.team_number.eq(1), "match_team_id"] = 77
        i.loc[i.match_id.eq(1) & i.team_number.eq(1), "score_team_id"] = 77
    else:
        s.loc[s.match_id.eq(1) & s.team_number.eq(1), "team_number"] = 3
    out = replay(m, i, s)
    assert not out.loc[1, "prior_lineup_a"]
    assert not out.loc[1, "prior_lineup_b"]


def test_quarantined_map_keeps_lineup_but_valid_map_ratings_enter_history():
    m, i, s = fixture()
    # Match 2: valid map has rating 9 for the old lineup, second map contradicts identity.
    s.loc[s.match_id.eq(2), "rating"] = 9.0
    extra_i = i.loc[i.match_id.eq(2)].copy()
    extra_i["map_id"] = 20
    extra_i.loc[extra_i.team_number.eq(1), "score_team_id"] = 999
    extra_s = s.loc[s.match_id.eq(2)].copy()
    extra_s["map_id"] = 20
    extra_s["rating"] = 100.0
    out = replay(m, pd.concat([i, extra_i]), pd.concat([s, extra_s]))
    assert out.loc[2, "prior_lineup_a"] and out.loc[2, "prior_lineup_b"]
    assert out.loc[2, "player_form_a"] == pytest.approx(5.0)
    assert out.loc[2, "player_form_b"] == pytest.approx(5.0)


def test_nonincreasing_and_identical_keys_raise():
    m, i, s = fixture()
    for bad in (m.iloc[[1, 0]].reset_index(drop=True), m.assign(match_id=[1, 1, 3]), m.assign(team_b=["1", "1", "2"])):
        with pytest.raises(ValueError):
            replay(bad, i, s)


def test_null_score_id_no_contradiction_and_coverage_counts():
    m, i, s = fixture()
    i["score_team_id"] = pd.NA
    f = replay(m, i, s)
    c = coverage(m, f, f, pd.Series([True, False, True]))
    row = c.loc[c.year.eq(2023)].iloc[0]
    assert row.rows == 2
    assert row.complete_prior_sides == 2
    assert row.both_prior_lineups == 1
    assert row.missing_prior_sides == 2
    assert row.missing_ratings_in_complete_prior_lineups == 0
    assert row.both_asof_form == 1
    assert row.both_current_roster_form == 1
    assert row.both_complete_current_rosters == 1


def test_complete_prior_lineup_with_no_rating_history():
    m, i, s = fixture()
    s.loc[s.match_id.eq(1) & s.team_number.eq(1), "rating"] = np.nan
    out = replay(m, i, s)
    assert out.loc[1, "prior_lineup_b"]
    assert out.loc[1, "players_lacking_ratings_b"] == 5
    assert out.loc[1, "rating_coverage_b"] == 0.0
    assert out.loc[1, "player_form_missing_b"]
    assert np.isnan(out.loc[1, "player_form_diff"])
