"""Exact group-qualification odds from the primary Elo pairwise probability."""
import pytest

from vct_quant.group_odds import attach_group_odds, elo_p_win, qualification_odds
from vct_quant.features.ratings import expected_score


def group(results=None, qualifiers=(), unverified=()):
    return {
        "entrants": {"1": "A", "2": "B", "3": "C", "4": "D"},
        "slots": {"opening_1": {"match_id": 11, "team_ids": [1, 2]},
                  "opening_2": {"match_id": 12, "team_ids": [3, 4]},
                  "winners": {"match_id": 13}, "elimination": {"match_id": 14},
                  "decider": {"match_id": 15}},
        "results": results or {},
        "qualifiers": list(qualifiers),
        "unverified_match_ids": list(unverified),
    }


def coin(a, b):
    return 0.5


def test_even_group_gives_every_team_half_a_spot_and_quarter_first():
    odds = qualification_odds(group(), coin)
    assert odds["p_qualify"] == pytest.approx({1: 0.5, 2: 0.5, 3: 0.5, 4: 0.5})
    assert odds["p_first"] == pytest.approx({1: 0.25, 2: 0.25, 3: 0.25, 4: 0.25})


def test_odds_sum_to_two_qualifiers_and_one_group_winner():
    strength = {1: 1700, 2: 1500, 3: 1450, 4: 1600}
    odds = qualification_odds(group(), lambda a, b: expected_score(strength[a], strength[b]))
    assert sum(odds["p_qualify"].values()) == pytest.approx(2.0)
    assert sum(odds["p_first"].values()) == pytest.approx(1.0)
    assert odds["p_qualify"][1] > odds["p_qualify"][4] > odds["p_qualify"][2] > odds["p_qualify"][3]


def test_hand_computed_path_with_played_openers():
    # 1 and 3 won the openers; p(a beats b) = 0.7 for the lower ID.
    results = {"opening_1": {"team_ids": [1, 2], "scores": [2, 0]},
               "opening_2": {"team_ids": [3, 4], "scores": [1, 2]}}
    p = lambda a, b: 0.7 if a < b else 0.3
    odds = qualification_odds(group(results), p)
    # Winners' match 1 vs 4: 1 first with 0.7. Elimination 2 vs 3: 2 wins 0.7.
    assert odds["p_first"] == pytest.approx({1: 0.7, 2: 0.0, 3: 0.0, 4: 0.3})
    # 4 beat 3, so 3 meets 2 in elimination (3 wins 0.3), then the winners'
    # loser: 4 w.p. 0.7 (3 beats 4: 0.7) or 1 w.p. 0.3 (3 beats 1: 0.3).
    p3 = 0.3 * (0.7 * 0.7 + 0.3 * 0.3)
    assert odds["p_qualify"][3] == pytest.approx(p3)
    assert sum(odds["p_qualify"].values()) == pytest.approx(2.0)


def test_played_results_pin_qualified_and_eliminated_teams():
    results = {"opening_1": {"team_ids": [1, 2], "scores": [2, 1]},
               "opening_2": {"team_ids": [3, 4], "scores": [0, 2]},
               "winners": {"team_ids": [1, 4], "scores": [2, 0]},
               "elimination": {"team_ids": [2, 3], "scores": [2, 0]}}
    odds = qualification_odds(group(results, qualifiers=[1]), coin)
    assert odds["p_qualify"] == pytest.approx({1: 1.0, 2: 0.5, 3: 0.0, 4: 0.5})
    assert odds["p_first"] == pytest.approx({1: 1.0, 2: 0.0, 3: 0.0, 4: 0.0})


def test_result_that_does_not_match_its_slot_raises():
    results = {"opening_1": {"team_ids": [1, 2], "scores": [2, 0]},
               "opening_2": {"team_ids": [3, 4], "scores": [2, 0]},
               "winners": {"team_ids": [1, 4], "scores": [2, 0]}}
    with pytest.raises(ValueError):
        qualification_odds(group(results), coin)


def test_pairwise_probability_is_the_primary_elo_formula_with_string_keys():
    ratings = {"1": 1600.0, "2": 1500.0}
    assert elo_p_win(ratings)(1, 2) == expected_score(1600.0, 1500.0)
    assert elo_p_win(ratings)(1, 99) == expected_score(1600.0, 1500.0)


def test_attach_withholds_unverified_or_unrated_groups():
    ratings = {str(t): 1500.0 + t for t in (1, 2, 3, 4)}
    counts = {str(t): 10 for t in (1, 2, 3, 4)}
    status = {"groups": {"A": group(), "B": group(unverified=[11])}}
    attach_group_odds(status, ratings, counts, 99)
    block = status["groups"]["A"]["qualification"]
    assert block["ratings_through_match_id"] == 99
    assert [row["team_id"] for row in block["teams"]] == [4, 3, 2, 1]
    assert sum(row["p_qualify"] for row in block["teams"]) == pytest.approx(2.0)
    assert "withheld" in status["groups"]["B"]["qualification"]
    status = {"groups": {"A": group()}}
    attach_group_odds(status, ratings, {"1": 10, "2": 10, "3": 10}, 99)
    assert "4" in status["groups"]["A"]["qualification"]["withheld"]
