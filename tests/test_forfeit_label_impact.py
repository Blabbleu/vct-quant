"""Forfeit-label counterfactual variants (docs/forfeit-labels.md)."""

import pandas as pd

from scripts.forfeit_label_impact import feed_labels, unscored_mask, variants


def _history():
    return pd.DataFrame({
        "match_id": [1, 2, 3, 4],
        "tier": [1, 1, 1, 1],
        "team_a": ["A", "A", "A", "A"],
        "team_b": ["B", "B", "name:tbd", "B"],
        "team_a_name": ["A", "A", "A", "A"],
        "team_b_name": ["B", "B", "TBD", "B"],
        "score_a": [1.0, 0.5, 0.0, 0.5],
        "maps_a": pd.array([2, 0, 0, 1], dtype="Int64"),
        "maps_b": pd.array([0, 0, None, 1], dtype="Int64"),
    })


def _feed():
    return pd.DataFrame([
        {"match_id": 2, "feed_name_1": "A", "feed_name_2": "B", "feed_winner_name": "B"},
        {"match_id": 3, "feed_name_1": "A", "feed_name_2": "TBD", "feed_winner_name": "A"},
        {"match_id": 4, "feed_name_1": "A", "feed_name_2": "B", "feed_winner_name": "A"},
    ])


def test_mask_and_feed_labels_touch_only_unscored_rows():
    h = _history()
    assert unscored_mask(h).tolist() == [False, True, True, False]
    labels = feed_labels(h, _feed())
    assert labels.isna().tolist() == [True, False, False, True]
    assert labels[1] == 0.0 and labels[2] == 1.0  # B won 2; A won the TBD forfeit (flip repaired)


def test_skip_variant_omits_forfeits_from_the_replay():
    runs = variants(_history(), _feed())
    assert runs["current"][0].match_id.tolist() == [1, 2, 3, 4]
    assert runs["skip"][0].match_id.tolist() == [1, 4]
    assert "name:tbd" not in runs["skip"][1]
    assert runs["feed_winner"][1]["name:tbd"] < 1500 < runs["current"][1]["name:tbd"]
