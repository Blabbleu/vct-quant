"""The one test worth having: no feature for match i may depend on match i.

Rolling aggregates over a match's own outcome are easy to write by accident and
produce beautiful backtests that mean nothing. This asserts the property
directly rather than trusting that every feature remembered to shift(1).
"""
import pandas as pd

from vct_quant.features.ratings import compute_elo


def _matches(scores):
    teams = [("A", "B"), ("B", "C"), ("A", "C"), ("C", "A"), ("B", "A")]
    return [(i, a, b, s) for i, ((a, b), s) in enumerate(zip(teams, scores))]


def test_flipping_a_result_cannot_change_that_match_or_any_earlier_one():
    original = [1.0, 1.0, 1.0, 1.0, 1.0]
    flipped = list(original)
    flipped[2] = 0.0  # rewrite the outcome of match index 2

    before = pd.DataFrame(compute_elo(_matches(original))[0])
    after = pd.DataFrame(compute_elo(_matches(flipped))[0])

    # Match 2's own prediction, and every prediction before it, must be untouched.
    cols = ["elo_a_pre", "elo_b_pre", "p_a_win"]
    pd.testing.assert_frame_equal(before.loc[:2, cols], after.loc[:2, cols])

    # And the test must be capable of failing: a later prediction has to move,
    # otherwise this would pass just as happily against a no-op implementation.
    assert not before.loc[3:, cols].equals(after.loc[3:, cols])


def test_churn_never_sees_the_outcome():
    """_roster_churn takes only match_id and team columns, so it structurally
    cannot read a result. Asserted by signature so a future edit that starts
    passing scores in has to break this test deliberately."""
    from vct_quant.features.build import _MATCH_SEQUENCE_SQL, _roster_churn

    src = _roster_churn.__code__
    used = set(src.co_names) | set(src.co_varnames)
    assert not {"score_a", "label", "maps_a", "maps_b", "is_winner"} & used
    assert "score_a" in _MATCH_SEQUENCE_SQL  # sanity: the column does exist


def test_margin_signal_never_returns_nan():
    """A single NaN here propagates through every rating that touches those two
    teams, and compute_elo will not raise -- it just returns NaN everywhere."""
    import pandas as pd

    from vct_quant.features.build import margin_signal

    df = pd.DataFrame({
        "maps_a": [2.0, None, 0.0, 1.0],
        "maps_b": [0.0, 1.0, 0.0, None],   # row 2 is a forfeit: no maps played
        "score_a": [1.0, 0.0, 1.0, 1.0],
    })
    out = margin_signal(df)
    assert out.notna().all(), out.tolist()
    assert out.iloc[0] == 1.0            # 2-0 sweep
    assert out.iloc[1] == 0.0            # missing score -> binary result
    assert out.iloc[2] == 1.0            # 0-0 forfeit -> binary result


def test_tier_two_results_do_not_move_shared_elo():
    from vct_quant.features.build import BEST_K, TIER_2_WEIGHT, elo_k

    out = elo_k(pd.Series([1, 2]))
    assert out.tolist() == [BEST_K, BEST_K * TIER_2_WEIGHT]
