import pytest

from vct_quant.features import glicko


def test_win_probability_equal_ratings_is_a_coin_flip():
    assert glicko.win_probability(1500, 200, 1500, 50) == pytest.approx(0.5)


def test_win_probability_shrinks_toward_half_when_uncertain():
    assert glicko.win_probability(1600, 50, 1500, 50) == pytest.approx(0.63684, abs=1e-4)
    assert glicko.win_probability(1600, 350, 1500, 350) == pytest.approx(0.57667, abs=1e-4)


def test_update_matches_hand_computed_values():
    r, rd = glicko.update(1500, 200, 1400, 30, 1.0)
    assert r == pytest.approx(1563.43, abs=0.01)
    assert rd == pytest.approx(175.22, abs=0.01)

    r, rd = glicko.update(1500, 200, 1400, 30, 0.0)
    assert r == pytest.approx(1387.49, abs=0.01)


def test_update_always_shrinks_rd_and_draw_between_equals_moves_nothing():
    r, rd = glicko.update(1500, 350, 1500, 350, 0.5)
    assert r == pytest.approx(1500)
    assert rd < 350


def test_compute_glicko_is_point_in_time_and_inflates_rd_across_seasons():
    matches = [(1, 2024, "a", "b", 1.0), (2, 2024, "a", "b", 1.0), (3, 2025, "a", "b", 1.0)]
    plain, _ = glicko.compute_glicko(matches)
    season, _ = glicko.compute_glicko(matches, season_c=100)

    assert plain[0]["glicko_a_pre"] == glicko.BASE  # first row sees no result yet
    assert plain[1]["glicko_a_pre"] > glicko.BASE
    assert plain[1]["rd_a_pre"] < plain[0]["rd_a_pre"]
    assert season[1]["rd_a_pre"] == pytest.approx(plain[1]["rd_a_pre"])  # same year
    assert season[2]["rd_a_pre"] > plain[2]["rd_a_pre"]  # new year widens RD


def test_compute_glicko_widens_rd_only_for_the_team_whose_roster_changed():
    matches = [(1, 2024, "a", "b", 1.0), (2, 2024, "a", "b", 1.0)]
    churn = [(float("nan"), float("nan")), (1.0, 0.0)]  # a fielded a whole new roster
    plain, _ = glicko.compute_glicko(matches, churn=churn)
    roster, _ = glicko.compute_glicko(matches, churn=churn, roster_c=100)

    assert roster[0]["rd_a_pre"] == pytest.approx(plain[0]["rd_a_pre"])  # NaN = no change
    assert roster[1]["rd_b_pre"] == pytest.approx(plain[1]["rd_b_pre"])  # b kept its roster
    assert roster[1]["rd_a_pre"] ** 2 == pytest.approx(plain[1]["rd_a_pre"] ** 2 + 100**2)
