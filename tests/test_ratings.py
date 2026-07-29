from vct_quant.features.ratings import (
    compute_elo,
    expected_score,
    map_score_probabilities,
    series_score_probabilities,
    update,
)


def test_expected_score_symmetry():
    assert expected_score(1500, 1500) == 0.5
    assert abs(expected_score(1600, 1400) + expected_score(1400, 1600) - 1.0) < 1e-12


def test_update_zero_sum():
    ra, rb = update(1500, 1500, 1.0)
    assert ra > 1500 > rb
    assert abs((ra - 1500) + (rb - 1500)) < 1e-12


def test_compute_elo_is_point_in_time():
    rows, final = compute_elo([("m1", "A", "B", 1.0), ("m2", "A", "B", 1.0)])
    # First match must be rated with both teams at the base rating.
    assert rows[0]["elo_a_pre"] == rows[0]["elo_b_pre"] == 1500.0
    assert rows[0]["p_a_win"] == 0.5
    # A won m1, so A enters m2 favored.
    assert rows[1]["elo_a_pre"] > rows[1]["elo_b_pre"]
    assert rows[1]["p_a_win"] > 0.5
    assert final["A"] > final["B"]


def test_compute_elo_accepts_per_match_k():
    ms = [("m1", "A", "B", 1.0), ("m2", "C", "D", 1.0)]
    # A big K on the first match must move A further than the small K moves C.
    _, final = compute_elo(ms, k=[64.0, 8.0])
    assert final["A"] - 1500 == 8 * (final["C"] - 1500)
    # A scalar k must still behave exactly as before.
    assert compute_elo(ms, k=32.0)[1] == compute_elo(ms, k=[32.0, 32.0])[1]


def test_compute_elo_initial_ratings_are_seeded_not_mutated():
    seed = {"A": 1700.0}
    rows, final = compute_elo([("m1", "A", "B", 1.0)], initial=seed)
    assert rows[0]["elo_a_pre"] == 1700.0  # seeded, not the 1500 default
    assert rows[0]["elo_b_pre"] == 1500.0  # unseeded teams still fall back
    assert final["A"] > 1700.0
    assert seed == {"A": 1700.0}  # caller's dict untouched


def test_score_probabilities_sum_to_one_and_preserve_series_probability():
    for best_of in (3, 5):
        scores = series_score_probabilities(0.7, best_of)
        a_wins = sum(p for score, p in scores.items() if score[0] > score[-1])

        assert abs(sum(scores.values()) - 1.0) < 1e-12
        assert abs(a_wins - 0.7) < 1e-12


def test_known_maps_produce_non_identical_score_probabilities():
    scores = map_score_probabilities([0.6, 0.7, 0.8])

    assert abs(scores["2-0"] - 0.42) < 1e-12
    assert abs(scores["2-1"] - 0.368) < 1e-12
    assert abs(scores["0-2"] - 0.12) < 1e-12
    assert abs(scores["1-2"] - 0.092) < 1e-12
