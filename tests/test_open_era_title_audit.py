"""2027 title audit must distinguish missing titles from unavailable feeds."""
import json
import sys

import pytest

from scripts import open_era_title_audit as titles


def payload(rows):
    return {"status": "success", "data": {"status": 200, "segments": rows}}


def test_2027_titles_join_events_and_fixtures_without_inventing_tiers():
    events = payload([
        {"title": "VCT 2027: Pacific LCQ", "event_id": "123", "url_path": "https://www.vlr.gg/event/123/example"},
        {"title": "Esports Nations Cup 2027", "event_id": "456"},
        {"title": "VCT 2026: Pacific LCQ", "event_id": "789"},
    ])
    upcoming = payload([{"match_event": "VCT 2027: Pacific LCQ"},
                        {"match_event": "VCT 2027: Pacific LCQ"},
                        {"match_event": "VCT Cup Americas 2027"}])
    rows = titles.audit(events, upcoming)
    assert [row["title"] for row in rows] == [
        "Esports Nations Cup 2027", "VCT 2027: Pacific LCQ", "VCT Cup Americas 2027"]
    lcq = rows[1]
    assert lcq["event_id"] == "123"
    assert lcq["event_url"] == "https://www.vlr.gg/event/123/example"
    assert lcq["upcoming_fixtures"] == 2
    assert (lcq["tier_current"], lcq["tier_by_title"]) == (1, 2)
    assert (rows[0]["vct_branded"], rows[0]["tier_current"]) == (False, None)
    assert (rows[2]["vct_branded"], rows[2]["tier_current"]) == (True, None)


def test_error_envelopes_are_not_empty_event_pages():
    for bad in ({"status": "error", "data": {"segments": []}},
                {"status": "success", "data": {"status": 502, "segments": []}},
                {"status": "success", "data": {"status": 200, "segments": {}}}):
        with pytest.raises((ValueError, KeyError)):
            titles.segments(bad)


def test_partial_feed_failure_exits_nonzero_without_claiming_no_titles(monkeypatch, capsys):
    def unavailable(*args, **kwargs):
        raise ValueError("feed unavailable")

    monkeypatch.setattr(titles.vlrgg, "fetch_events", unavailable)
    monkeypatch.setattr(titles.vlrgg, "fetch_upcoming_matches", lambda save: payload([]))
    monkeypatch.setattr(sys, "argv", ["open_era_title_audit.py"])
    with pytest.raises(SystemExit) as exc:
        titles.main()
    assert exc.value.code == 1
    report = json.loads(capsys.readouterr().out)
    assert report["complete"] is False
    assert "events" in report["errors"]
    assert "season_2027_titles" not in report
