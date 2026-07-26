from vct_quant.features.ratings import compute_elo, expected_score, update


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
