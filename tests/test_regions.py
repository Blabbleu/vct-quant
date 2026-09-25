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


@pytest.mark.parametrize(("subregion", "territory"), [
    ("North America", "Americas"), ("Latin America North", "Americas"),
    ("Latin America South", "Americas"), ("Brazil", "Americas"),
    ("Europe", "EMEA"), ("Turkiye", "EMEA"), ("Türkiye", "EMEA"),
    ("MENA", "EMEA"), ("South Korea", "Pacific"), ("Japan", "Pacific"),
    ("Thailand", "Pacific"), ("Indonesia", "Pacific"),
    ("Vietnam", "Pacific"), ("Southeast Asia", "Pacific"),
    ("South Asia", "Pacific"), ("Oceania", "Pacific"),
    ("China", "China"),
])
def test_official_2027_open_qualifier_subregion_maps_to_territory(subregion, territory):
    title = f"VCT 2027: {subregion} Open Qualifiers"
    assert regions.territory_for_event(title) == territory


def test_non_official_or_ambiguous_event_is_not_a_region_signal():
    assert regions.territory_for_event("Brazil Open Qualifier 2026") is None
    assert regions.territory_for_event("VCT 2027: Open Qualifiers") is None
    assert regions.territory_for_event("VCT 2027: Americas Kickoff") == "Americas"


def test_tier2_qualifier_assigns_region_before_tier1_international():
    history = pd.DataFrame([
        (1, 2, "VCT 2027: South Asia Open Qualifiers", "rookie", "local"),
        (2, 1, "Valorant Champions 2027", "rookie", "other"),
    ], columns=["match_id", "tier", "event_name", "team_a", "team_b"])
    assigned = regions.assign_regions(history)
    assert assigned.region_a.tolist() == ["Pacific", "Pacific"]
    assert assigned.region_b.iloc[0] == "Pacific"
    assert pd.isna(assigned.region_b.iloc[1])
    assert assigned.match_id.tolist() == [1, 2]


def test_2027_regional_matches_without_numeric_date_raw_are_kept():
    history = pd.DataFrame([
        (1, 1, 2026.0, "VCT 2026: Americas Stage 2"),
        (2, 2, float("nan"), "VCT 2027: Brazil Open Qualifiers"),
        (3, 1, float("nan"), "VCT 2027: Americas Kickoff"),
        (4, 2, float("nan"), "VCT 2026: Brazil Open Qualifiers"),
    ], columns=["match_id", "tier", "year", "event_name"])
    assert history.loc[regions.region_history_mask(history), "match_id"].tolist() == [1, 2, 3]


def test_2027_season_label_is_available_for_future_cohort():
    df = pd.DataFrame({
        "year": [2026.0, float("nan"), float("nan")],
        "event_name": ["VCT 2026: Americas", "VCT 2027: Americas Kickoff", "Random 2027 Event"],
    })
    assert regions.with_2027_season(df).year.tolist()[:2] == [2026.0, 2027.0]
    assert pd.isna(regions.with_2027_season(df).year.iloc[2])
