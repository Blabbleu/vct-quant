"""The map-veto feasibility audit must not treat played maps as pre-match vetoes."""
import pandas as pd

from scripts.map_veto_feasibility import summarize


def test_sweep_can_cover_played_maps_but_never_full_pool():
    rows = pd.DataFrame([
        dict(match_id=1, year=2025, best_of=3, maps_a=2, maps_b=0,
             map_count=2, scored_maps=2, named_maps=2, picks=0),
        dict(match_id=2, year=2025, best_of=3, maps_a=2, maps_b=1,
             map_count=3, scored_maps=3, named_maps=3, picks=1),
        dict(match_id=3, year=2025, best_of=5, maps_a=3, maps_b=0,
             map_count=3, scored_maps=3, named_maps=3, picks=0),
    ])
    record = summarize(rows).iloc[0]
    assert record.series == 3
    assert record.played_maps_covered == 3
    assert record.full_pool_observed == 1
    assert record.early_finishes == 2
    assert record.early_with_full_pool == 0
    assert record.series_with_picks == 1


def test_missing_or_duplicate_map_detail_cannot_pass_and_bo1_is_excluded():
    rows = pd.DataFrame([
        dict(match_id=1, year=2024, best_of=3, maps_a=2, maps_b=1,
             map_count=3, scored_maps=2, named_maps=3, picks=0),
        dict(match_id=2, year=2024, best_of=3, maps_a=2, maps_b=1,
             map_count=3, scored_maps=3, named_maps=2, picks=0),
        dict(match_id=3, year=2026, best_of=3, maps_a=None, maps_b=None,
             map_count=3, scored_maps=3, named_maps=3, picks=0),
        dict(match_id=4, year=2026, best_of=1, maps_a=1, maps_b=0,
             map_count=1, scored_maps=1, named_maps=1, picks=1),
    ])
    summary = summarize(rows)
    assert summary.year.tolist() == [2024, 2026]
    assert summary.series.tolist() == [2, 1]
    assert summary.played_maps_covered.tolist() == [0, 0]
    assert summary.full_pool_observed.tolist() == [0, 0]
    assert summary.series_with_picks.tolist() == [0, 0]


def test_empty_rows():
    rows = pd.DataFrame(columns=["year", "best_of"])
    assert summarize(rows).empty
