import numpy as np
import pandas as pd
import pytest

from scripts.side_order_audit import by_year, orientation_counts


def test_by_year_uses_decisive_dated_matches_and_ignores_other_tiers():
    rows = pd.DataFrame({
        "year": [2021, 2021, 2021, 2021, 2022, None],
        "tier": [1, 1, 1, 2, 1, 1],
        "score_a": [1.0, 0.0, 0.5, 1.0, 0.0, 1.0],
    })
    p = np.array([0.7, 0.4, 0.9, 0.8, 0.3, 0.6])
    result = by_year(rows, p, tier=1)
    assert [r["year"] for r in result] == [2021, 2022]
    assert result[0]["n"] == 2
    assert result[0]["actual"] == pytest.approx(0.5)
    assert result[0]["predicted"] == pytest.approx(0.55)
    assert result[0]["residual"] == pytest.approx(-0.05)
    assert result[1]["n"] == 1
    assert result[1]["residual"] == pytest.approx(-0.3)


def test_side_flip_reverses_residual_and_z():
    rows = pd.DataFrame({"year": [2022, 2022, 2022], "tier": [3] * 3,
                         "score_a": [1.0, 1.0, 0.0]})
    p = np.array([0.6, 0.3, 0.8])
    a = by_year(rows, p, tier=3)[0]
    flipped = rows.assign(score_a=1 - rows.score_a)
    b = by_year(flipped, 1 - p, tier=3)[0]
    assert b["residual"] == pytest.approx(-a["residual"])
    assert b["z"] == pytest.approx(-a["z"])
    assert a["z"] == pytest.approx((2 - p.sum()) / np.sqrt((p * (1 - p)).sum()))



def test_feed_orientation_counts_exact_named_pairs_without_guessing_aliases():
    rows = pd.DataFrame({"year": [2021, 2022, 2022, 2022, 2022],
                         "tier": [1] * 5, "match_id": [1, 2, 3, 4, 5],
                         "team_a_name": ["Foo", "Team A", "Alpha", "Some Club", "One"],
                         "team_b_name": ["Bar", "Team B", "Beta", "Other", "Two"]})
    feed = pd.DataFrame({"match_id": [2, 3, 4, 5],
                         "name_a": ["Team A", "Beta", "Some Club Esports", "One"],
                         "name_b": ["Team B", "Alpha", "Other", "Two"]})
    result = orientation_counts(rows, feed, tier=1)
    assert result[2021] == {"absent": 1, "same": 0, "flipped": 0, "unmatched": 0}
    assert result[2022] == {"absent": 0, "same": 2, "flipped": 1, "unmatched": 1}


def test_probabilities_must_align_and_be_finite():
    rows = pd.DataFrame({"year": [2022], "tier": [3], "score_a": [1.0]})
    with pytest.raises(ValueError, match="aligned"):
        by_year(rows, [], tier=3)
    with pytest.raises(ValueError, match="finite"):
        by_year(rows, [float("nan")], tier=3)
