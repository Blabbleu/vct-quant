"""Exact-score distribution served to the desk for each upcoming fixture."""
import math

import pandas as pd
import pytest

from vct_quant.dashboard import score_distribution
from vct_quant.features.ratings import series_score_probabilities


def test_bo3_distribution_in_display_order():
    scores = series_score_probabilities(0.6, 3)
    out = score_distribution(scores, 3)
    assert [row["score"] for row in out] == ["2-0", "2-1", "1-2", "0-2"]
    assert sum(row["p"] for row in out) == pytest.approx(1)
    assert out[0]["p"] + out[1]["p"] == pytest.approx(0.6)


def test_bo5_distribution_has_six_scores():
    out = score_distribution(series_score_probabilities(0.55, 5), 5)
    assert [row["score"] for row in out] == ["3-0", "3-1", "3-2", "2-3", "1-3", "0-3"]


def test_parquet_struct_nulls_for_other_format_are_dropped():
    """A parquet struct column unions keys across rows: a Bo3 row read back
    beside a Bo5 row carries 3-x keys as None, which must not be served."""
    bo3 = series_score_probabilities(0.6, 3)
    padded = {**{k: None for k in ("3-0", "3-1", "3-2", "0-3", "1-3", "2-3")}, **bo3}
    out = score_distribution(padded, 3)
    assert [row["score"] for row in out] == ["2-0", "2-1", "1-2", "0-2"]


def test_round_trip_through_parquet(tmp_path):
    frame = pd.DataFrame({
        "best_of": [3, 5],
        "score_probabilities": [series_score_probabilities(0.6, 3),
                                series_score_probabilities(0.6, 5)],
    })
    path = tmp_path / "f.parquet"
    frame.to_parquet(path)
    back = pd.read_parquet(path)
    for row in back.itertuples():
        out = score_distribution(row.score_probabilities, row.best_of)
        assert len(out) == (4 if row.best_of == 3 else 6)
        assert sum(r["p"] for r in out) == pytest.approx(1)


@pytest.mark.parametrize("bad", [
    None,
    float("nan"),
    {},
    {"2-0": 0.5, "0-2": 0.5},                       # incomplete Bo3
    {"2-0": 0.5, "2-1": 0.5, "1-2": 0.5, "0-2": 0.5},  # does not sum to 1
    {"2-0": math.nan, "2-1": 0.4, "1-2": 0.3, "0-2": 0.3},
])
def test_unusable_distribution_is_none(bad):
    assert score_distribution(bad, 3) is None


def test_mismatched_format_is_none():
    assert score_distribution(series_score_probabilities(0.6, 3), 5) is None
