import json

import pandas as pd

from vct_quant.etl import normalize
from vct_quant.etl.events import competition_tier
from vct_quant.etl.normalize import _duration_seconds, _pct, _unambiguous


def test_pct_strips_sign_and_rejects_out_of_range():
    out = _pct(pd.Series(["81%", " 26 %", "0%", "100%", "150%", None, "n/a"]))
    assert list(out[:4]) == [81.0, 26.0, 0.0, 100.0]
    # The schema CHECKs 0-100, so anything outside becomes NULL rather than
    # failing the insert.
    assert out[4:].isna().all()


def test_duration_handles_both_clock_formats():
    out = _duration_seconds(pd.Series(["1:02:40", "46:45", "", None, "abc"]))
    assert out[0] == 3760  # 1h 2m 40s
    assert out[1] == 2805  # 46m 45s
    assert out[2:].isna().all()


def test_unambiguous_drops_names_with_two_ids():
    # "Reused" carries two distinct vlr.gg IDs, so resolving it either way would
    # merge two different entities' histories.
    df = pd.DataFrame({
        "Team": ["Solo", "Reused", "Reused", "NoId", "Dupe", "Dupe"],
        "Team ID": [10.0, 20.0, 21.0, None, 30.0, 30.0],
    })
    out = _unambiguous(df, "Team", "Team ID")
    assert out == {"Solo": 10, "Dupe": 30}
    assert "Reused" not in out and "NoId" not in out


def test_unambiguous_ignores_nonpositive_ids():
    df = pd.DataFrame({"Player": ["a", "b"], "Player ID": [0.0, 5.0]})
    assert _unambiguous(df, "Player", "Player ID") == {"b": 5}


def test_competition_tiers_are_season_aware():
    assert competition_tier("VCT 2026: Americas Stage 2") == 1
    assert competition_tier("Valorant Masters Toronto 2025") == 1
    assert competition_tier("Champions Tour North America Stage 2: Challengers", 2022) == 1
    assert competition_tier("Challengers League Brazil: Split 1", 2023) == 2
    assert competition_tier("VCT 2025: Americas Ascension") == 2
    assert competition_tier("Nerd Street Summer Championship 2022") is None
    assert competition_tier("VCT OFF//SEASON Spotlight Series 2024: Americas") is None
    assert competition_tier("Game Changers 2025: Championship Seoul") is None


def test_vlrgg_match_keeps_its_event_id_and_title(tmp_path, monkeypatch):
    monkeypatch.setattr(normalize, "RAW_VLRGG_DIR", tmp_path)
    event = {
        "event_id": "42", "title": "VCT 2026: Americas Stage 2",
        "status": "completed", "region": "na", "dates": "Jul 1—2",
        "prize": "$1", "thumb": "logo", "url_path": "/event/42",
    }
    match = {
        "match_id": "99", "url": "/99/a-vs-b", "date": "Wed, July 01, 2026",
        "status": "Completed", "event_series": "Grand Final",
        "team1": {"name": "A", "score": "2"},
        "team2": {"name": "B", "score": "1"},
    }
    (tmp_path / "events_page001_test.json").write_text(
        json.dumps({"data": {"segments": [event]}})
    )
    (tmp_path / "event_matches_42_test.json").write_text(
        json.dumps({"data": {"segments": [match]}})
    )

    events = normalize._vlrgg_events()
    matches = normalize._vlrgg_event_matches(events)

    assert events.iloc[0][["event_id", "tier"]].tolist() == [42, 1]
    assert matches.iloc[0][["event_id", "event_name", "event_series"]].tolist() == [
        42, "VCT 2026: Americas Stage 2", "Grand Final",
    ]
