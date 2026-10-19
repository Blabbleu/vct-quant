import math

import numpy as np
import pandas as pd
import pytest

from research.exact_score_dependence import (
    assert_elo_equality, candidate_c, conditional_loss, filter_legal_scores,
    independent, series_loss, tuning_diagnostics,
)
from vct_quant.features.ratings import series_score_probabilities


def sample_rows():
    return pd.DataFrame([
        (1, "Tier 1", 2023, 1, 1, 0, 1, 0.6, "1-0"),  # Bo1
        (2, "Tier 1", 2023, 2, 1, 1, 0.5, 0.6, "1-1"),  # Bo2 draw
        (3, "Tier 1", 2024, 3, None, 0, 1, 0.6, "<NA>-0"),
        (4, "Tier 1", 2024, 3, 2, 2, 1, 0.6, "2-2"),
        (5, "Tier 2", 2023, 3, 2, 1, 1, 0.6, "2-1"),
        (6, "Tier 2", 2024, 5, 3, 1, 1, 0.6, "3-1"),
        (7, "Tier 2", 2024, 5, 3, 3, 1, 0.6, "3-3"),
    ], columns=["match_id", "pool", "year", "best_of", "maps_a", "maps_b",
                "score_a", "p_a_win", "unused"])


def test_legal_filter_and_grouped_drop_counts():
    kept, counts = filter_legal_scores(sample_rows())
    assert kept.match_id.tolist() == [5, 6]
    got = {(r.pool, r.year, r.filter_reason): r.n for r in counts.itertuples()}
    assert got[("Tier 1", 2023, "other_format")] == 2
    assert got[("Tier 1", 2024, "forfeit_missing_score")] == 1
    assert got[("Tier 1", 2024, "impossible_score")] == 1
    assert got[("Tier 2", 2023, "eligible")] == 1
    assert got[("Tier 2", 2024, "eligible")] == 1
    assert got[("Tier 2", 2024, "impossible_score")] == 1


@pytest.mark.parametrize("best_of", [3, 5])
def test_candidate_zero_and_preserved_series_probability(best_of):
    a = best_of // 2 + 1
    for p in (0.2, 0.5, 0.83):
        expected = series_score_probabilities(p, best_of)
        actual = candidate_c(p, best_of, 0)
        assert actual.keys() == expected.keys()
        for key in expected:
            assert actual[key] == pytest.approx(expected[key], abs=1e-12)
        for theta in (-2, -0.7, 0, 1.4, 2):
            shifted = candidate_c(p, best_of, theta)
            assert sum(shifted.values()) == pytest.approx(1, abs=1e-12)
            assert sum(v for k, v in shifted.items() if k.startswith(f"{a}-")) == pytest.approx(p, abs=1e-12)


def test_conditional_decomposition():
    p, score = 0.68, "1-2"
    dist = independent(p, 3)
    assert -math.log(dist[score]) == pytest.approx(series_loss(score, p) + conditional_loss(score, p, dist))


def test_full_pool_elo_equality_guard():
    sequence = pd.DataFrame({
        "match_id": [1, 2, 3, 4],
        "team_a": ["a", "b", "c", "a"],
        "team_b": ["b", "c", "a", "c"],
        "tier": [1, 2, 1, 1],
        "signal": [1., 0., 0.5, 1.],
        "year": [2023, 2024, 2025, 2026],
    })
    got = assert_elo_equality(sequence)
    assert len(got) == 4
    assert np.isfinite(got).all()
    assert got[1] < 0.5  # Tier 2 inherits the official pool's earlier rating
    with pytest.raises(ValueError):
        assert_elo_equality(sequence.iloc[::-1])


def test_tuning_diagnostics_and_future_refusal():
    frame = pd.DataFrame({
        "year": [2023, 2024, 2024],
        "best_of": [3, 3, 3],
        "p_a_win": [0.5, 0.65, 0.92],
        "score": ["2-0", "2-1", "0-2"],
        "score_a": [1., 1., 0.],
    })
    d = tuning_diagnostics(frame)
    assert d["n"] == 3
    assert sum(b["n"] for b in d["bins"]) == 3
    assert d["observed"] == pytest.approx(2 / 3)
    with pytest.raises(ValueError, match="through 2024"):
        tuning_diagnostics(pd.concat([frame, frame.assign(year=2025)]))
