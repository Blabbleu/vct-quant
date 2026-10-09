import pytest

from vct_quant.event_bracket import load_bracket_spec, playoff_feeds
from vct_quant.features.ratings import expected_score
from vct_quant.playoff_odds import project_playoffs


def _entrants(spec):
    return {row["match_id"]: tuple(row["team_ids"])
            for row in spec["verified_opening_pairings"]}


def test_coin_flip_title_and_reach_probabilities():
    spec = load_bracket_spec(2766)
    result = project_playoffs(spec, _entrants(spec), {}, lambda a, b: 0.5)
    assert all(abs(row["p_title"] - 1 / 8) < 1e-9 for row in result["teams"].values())
    assert all(abs(row["p_reach"]["Upper Semifinals"] - 0.5) < 1e-9
               for row in result["teams"].values())
    assert all(abs(sum(candidate["p_pairing"] for candidate in slot["candidates"]) - 1) < 1e-9
               for slot in result["slots"].values())
    assert abs(sum(team["p_title"] for team in result["teams"].values()) - 1) < 1e-9


def test_strength_ordering_is_monotone_and_titles_sum_to_one():
    spec = load_bracket_spec(2766)
    teams = [team for pair in _entrants(spec).values() for team in pair]
    ratings = {team: float(team) for team in teams}
    result = project_playoffs(
        spec, _entrants(spec), {},
        lambda a, b: expected_score(ratings[a], ratings[b]))
    ordered = sorted(teams, key=lambda team: ratings[team])
    assert all(result["teams"][a]["p_title"] <= result["teams"][b]["p_title"]
               for a, b in zip(ordered, ordered[1:]))
    assert abs(sum(row["p_title"] for row in result["teams"].values()) - 1) < 1e-9


def test_played_uqf_and_lr1_yield_hand_computed_lr2_pairings():
    spec = load_bracket_spec(2766)
    entrants = _entrants(spec)
    feeds = playoff_feeds(spec)
    results = {}
    outcomes = {}
    # The four quarterfinals are fixed, with the first entrant winning each.
    for mid, pair in entrants.items():
        results[mid] = {"team_ids": list(pair), "scores": [2, 0]}
        outcomes[mid] = (pair[0], pair[1])
    # LR1 is fixed as well. Its first routed team wins each series.
    for mid in (754738, 754739):
        a, b = feeds[mid]
        pair = tuple(outcomes[source][0 if take == "winner" else 1]
                     for source, take in (a, b))
        results[mid] = {"team_ids": list(pair), "scores": [2, 0]}
        outcomes[mid] = (pair[0], pair[1])

    output = project_playoffs(spec, entrants, results,
                              lambda a, b: 0.7 if a < b else 0.3)
    # 754735 pairs the winners of 754732/754733. If its first side wins,
    # the second side loses (probability .7 when the first team ID is lower);
    # otherwise the first side loses. The 754740 first side is fixed by LR1.
    expected = {
        (11058, 624): 0.3,
        (11058, 1034): 0.7,
    }
    actual = output["slots"][754740]["candidates"]
    actual_probs = {tuple(c["team_ids"]): c["p_pairing"] for c in actual}
    assert set(actual_probs) == set(expected)
    assert all(abs(actual_probs[pair] - probability) < 1e-9
               for pair, probability in expected.items())
    actual_p_a = {tuple(c["team_ids"]): c["p_a"] for c in actual}
    assert set(actual_p_a) == {(11058, 624), (11058, 1034)}
    assert all(abs(actual_p_a[pair] - 0.3) < 1e-9 for pair in actual_p_a)


def test_result_must_match_routed_pair():
    spec = load_bracket_spec(2766)
    entrants = _entrants(spec)
    results = {754730: {"team_ids": list(entrants[754730]), "scores": [2, 0]},
               754731: {"team_ids": list(entrants[754731]), "scores": [2, 0]},
               754734: {"team_ids": [999, 998], "scores": [2, 0]}}
    with pytest.raises(ValueError, match="routed playoff pair"):
        project_playoffs(spec, entrants, results, lambda a, b: 0.5)


@pytest.mark.parametrize("probability", [1.2, float("nan")])
def test_invalid_pairwise_probability_is_rejected(probability):
    spec = load_bracket_spec(2766)
    with pytest.raises(ValueError, match="invalid pairwise probability"):
        project_playoffs(spec, _entrants(spec), {}, lambda a, b: probability)
