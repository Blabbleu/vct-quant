from datetime import datetime, timezone

from scripts.player_coverage_audit import summarize


def test_summarize_reports_latest_coverage_and_series_gap():
    rows = [
        (7, "Alpha", 101, datetime(2025, 1, 1, tzinfo=timezone.utc), 3, 3),
        (7, "Alpha", 102, datetime(2025, 1, 2, tzinfo=timezone.utc), 3, 0),
        (7, "Alpha", 103, datetime(2025, 1, 3, tzinfo=timezone.utc), 0, 0),
        (9, "Beta", 201, datetime(2025, 1, 4, tzinfo=timezone.utc), 0, 0),
    ]

    alpha, beta = summarize(rows)
    assert alpha == {
        "team_id": 7,
        "team": "Alpha",
        "played_series": 3,
        "latest_series_match_id": 103,
        "latest_series_date": "2025-01-03",
        "scored_maps_in_latest_series": 0,
        "scored_maps_in_history": 6,
        "maps_with_player_stats_in_history": 3,
        "scored_maps_missing_player_stats": 3,
        "latest_player_stats_match_id": 101,
        "latest_player_stats_date": "2025-01-01",
        "series_since_player_stats": 2,
        "recent_5_series_with_player_stats": 1,
    }
    assert beta["latest_player_stats_match_id"] is None
    assert beta["series_since_player_stats"] == 1
    assert beta["recent_5_series_with_player_stats"] == 0


def test_summarize_sorts_worst_coverage_first_and_ties_by_name():
    date = datetime(2025, 1, 1, tzinfo=timezone.utc)
    rows = [
        (2, "Zed", 2, date, 0, 0),
        (1, "Alpha", 1, date, 0, 0),
        (3, "Bee", 3, date, 0, 0),
        (3, "Bee", 4, date, 0, 0),
    ]
    assert [row["team"] for row in summarize(rows)] == ["Bee", "Alpha", "Zed"]
    assert summarize(rows)[0]["series_since_player_stats"] == 2
