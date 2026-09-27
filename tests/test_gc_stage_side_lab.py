import numpy as np
import pandas as pd

from scripts import gc_side_lab, gc_stage_side_lab as lab


def test_stage_bucket_is_literal_and_case_insensitive():
    assert lab.stage_bucket("Upper Quarterfinals") == "upper"
    assert lab.stage_bucket("LOWER ROUND 1") == "lower"
    assert lab.stage_bucket("Group A") == "other"
    assert lab.stage_bucket(None) == "other"


def test_constant_stage_offsets_match_existing_fixed_h_replay():
    df = pd.DataFrame({
        "team_a": ["a", "b", "a", "c"],
        "team_b": ["b", "c", "c", "a"],
        "score_a": [1.0, 0.0, 1.0, 0.5],
        "maps_a": [2, 0, 2, 1], "maps_b": [0, 2, 0, 1],
        "rounds_a": [26, 18, 26, 24], "rounds_b": [18, 26, 18, 24],
        "stage_bucket": ["upper", "lower", "other", "upper"],
    })
    got = lab.replay(df, (30.0, 30.0, 30.0))
    expected = gc_side_lab.replay(
        df.team_a.to_numpy(), df.team_b.to_numpy(),
        __import__("vct_quant.features.build", fromlist=["margin_signal"]).margin_signal(df).to_numpy(),
        192.0, 30.0,
    )
    assert np.allclose(got, expected)


def test_select_tie_break_is_closest_to_reference_then_lexicographic():
    losses = {(20.0, 40.0, 30.0): 0.5, (40.0, 20.0, 30.0): 0.5,
              (30.0, 30.0, 30.0): 0.6}
    assert lab.select(losses) == (20.0, 40.0, 30.0)


def test_paired_t_positive_means_candidate_better():
    assert lab.paired_t(np.array([0.7, 0.8, 0.6]), np.array([0.6, 0.7, 0.5])) > 0
