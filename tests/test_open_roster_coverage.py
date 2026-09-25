"""2027 roster-collection targets stay point-in-time and bounded."""

import pandas as pd
import pytest

from scripts.open_roster_coverage import calendar_coverage, detail_backlog, season_open_matches


def test_november_2026_match_in_2027_open_event_is_selected():
    history = pd.DataFrame({
        "match_id": [10, 11, 12, 13, 14],
        "tier": [2, 2, 1, 2, 2],
        "team_a": ["a"] * 5, "team_b": ["b"] * 5,
    })
    metadata = pd.DataFrame({
        "match_id": [10, 11, 12, 13, 14],
        "event_name": ["VCT 2027: North America Open Qualifier",
                       "VCT 2026: North America Open Qualifier",
                       "VCT 2027: Americas Kickoff",
                       "VCT 2027: Pacific Last Chance Qualifier",
                       "VCT 2027: Pacific Wild Card"],
        "completed_at": pd.to_datetime(["2026-11-01", "2026-11-02", "2027-01-01",
                                        None, "2027-02-01"], utc=True),
    })
    assert season_open_matches(history, metadata, 2027).match_id.tolist() == [10, 14]


def test_backlog_ranks_latest_before_missing_and_dedupes_shared_games():
    matches = pd.DataFrame({
        "match_id": [1, 2, 3, 4], "team_a": ["a", "a", "a", "c"],
        "team_b": ["b", "c", "d", "d"],
    })
    full = frozenset("abcde")
    rosters = {(3, 1): full, (3, 2): full, (4, 1): full, (4, 2): full}
    # Team a's last two are 3 and 2. Team b's only game is 1, and c's
    # latest is 4. The older 1 is still selected on behalf of b.
    assert detail_backlog(matches, rosters, per_team=2) == ([1, 2], 8, 4)
    assert detail_backlog(matches, rosters, per_team=1) == ([1], 8, 4)


def test_coverage_uses_actual_completion_year_not_event_season():
    history = pd.DataFrame({"match_id": [1, 2], "tier": [2, 1]})
    metadata = pd.DataFrame({
        "match_id": [1, 2],
        "completed_at": pd.to_datetime(["2026-11-01", "2027-01-01"], utc=True),
    })
    rosters = {(1, 1): frozenset("abcde"), (2, 2): frozenset("abc")}
    assert calendar_coverage(history, metadata, rosters, (2026, 2027)) == [
        (2026, 1, 0, 0, 0), (2026, 2, 1, 2, 1),
        (2027, 1, 1, 2, 0), (2027, 2, 0, 0, 0),
    ]


def test_backlog_excludes_placeholder_and_rejects_invalid_limit():
    matches = pd.DataFrame({"match_id": [1], "team_a": ["name:tbd"], "team_b": ["name:tbd"]})
    assert detail_backlog(matches, {}, 1) == ([], 0, 0)
    with pytest.raises(ValueError, match="positive"):
        detail_backlog(matches, {}, 0)
