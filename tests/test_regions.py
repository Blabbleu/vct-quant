import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

path = Path(__file__).parents[1] / "scripts" / "benchmark_regions.py"
spec = importlib.util.spec_from_file_location("benchmark_regions", path)
regions = importlib.util.module_from_spec(spec)
spec.loader.exec_module(regions)


def frame(rows):
    return pd.DataFrame(rows, columns=[
        "international", "region_a", "region_b", "elo_a", "elo_b", "p_elo", "signal",
    ])


def test_offsets_are_point_in_time_and_learn_from_international_results():
    df = frame([
        (True, "EMEA", "China", 1500, 1500, 0.5, 1.0),   # EMEA beats China
        (False, "EMEA", "EMEA", 1600, 1500, 0.64, 1.0),  # regional: untouched
        (True, "EMEA", "China", 1500, 1500, 0.5, 1.0),
    ])
    p = regions.offset_probabilities(df, k=32)

    assert p[0] == pytest.approx(0.5)  # nothing learned yet: no leakage
    assert p[1] == pytest.approx(0.64)  # regional match keeps raw Elo
    # after one win: EMEA +16, China -16, so a 32-point edge
    assert p[2] == pytest.approx(1 / (1 + 10 ** (-32 / 400)))


def test_k_zero_is_raw_elo():
    df = frame([(True, "EMEA", "China", 1550, 1500, 0.57, 0.0)] * 3)
    assert np.allclose(regions.offset_probabilities(df, k=0), 0.57, atol=0.01)
