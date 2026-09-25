"""2027 title audit must distinguish missing titles from unavailable feeds."""
import json
import sys

import pytest

from scripts import open_era_title_audit as titles


def payload(rows):
    return {"status": "success", "data": {"status": 200, "segments": rows}}


def test_later_event_page_can_reveal_2027_title_missing_from_first_page():
    rows = titles.audit([payload([{"title": "VCT 2026: Champions"}]),
                         payload([{"title": "VCT 2027: Pacific LCQ", "event_id": "123"}])],
                        payload([]))
    assert [row["title"] for row in rows] == ["VCT 2027: Pacific LCQ"]
    assert rows[0]["event_id"] == "123"


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
    assert (lcq["tier_if_2026"], lcq["tier_by_title"]) == (1, 2)
    assert (rows[0]["vct_branded"], rows[0]["tier_if_2026"]) == (False, None)
    assert (rows[2]["vct_branded"], rows[2]["tier_if_2026"]) == (True, None)


def test_calendar_tier_audit_uses_each_fixture_start_year_not_a_fixed_2026():
    events = payload([{"title": "VCT 2027: Pacific LCQ", "event_id": "123"}])
    upcoming = payload([
        {"match_event": "VCT 2027: Pacific LCQ", "unix_timestamp": "2026-11-15 09:00:00",
         "match_page": "101/november"},
        {"match_event": "VCT 2027: Pacific LCQ", "unix_timestamp": "2027-01-15 09:00:00",
         "match_page": "102/january"},
    ])
    row = titles.audit(events, upcoming)[0]
    assert row["fixture_calendar_years"] == [2026, 2027]
    assert row["calendar_tier_mismatches"] == [{
        "match_page": "101/november", "scheduled_at": "2026-11-15 09:00:00",
        "calendar_tier": 1, "title_tier": 2,
    }]
    assert row["tier_if_2026"] == 1
    assert "tier_current" not in row


def test_unknown_fixture_date_is_not_counted_as_no_calendar_disagreement():
    row = titles.audit(payload([]), payload([
        {"match_event": "VCT 2027: Pacific LCQ", "unix_timestamp": "TBD", "match_page": "103/tbd"},
    ]))[0]
    assert row["upcoming_fixtures"] == 1
    assert row["unparsed_fixture_dates"] == 1
    assert row["fixture_calendar_years"] == []
    assert row["calendar_tier_mismatches"] == []


def test_error_envelopes_are_not_empty_event_pages():
    for bad in ({"status": "error", "data": {"segments": []}},
                {"status": "success", "data": {"status": 502, "segments": []}},
                {"status": "success", "data": {"status": 200, "segments": {}}}):
        with pytest.raises((ValueError, KeyError)):
            titles.segments(bad)


def test_second_event_page_error_retains_observations_but_marks_incomplete(monkeypatch, capsys):
    def fetch(page, save):
        if page == 2:
            raise ValueError("page 2 down")
        return payload([{"title": "VCT 2027: Pacific LCQ", "event_id": "123"}])

    monkeypatch.setattr(titles.vlrgg, "fetch_events", fetch)
    monkeypatch.setattr(titles.vlrgg, "fetch_upcoming_matches", lambda save: payload([]))
    monkeypatch.setattr(sys, "argv", ["open_era_title_audit.py", "--event-pages", "2"])
    with pytest.raises(SystemExit) as exc:
        titles.main()
    assert exc.value.code == 1
    report = json.loads(capsys.readouterr().out)
    assert report["complete"] is False
    assert report["event_pages_checked"] == [1]
    assert report["event_rows"] == 1
    assert "events_page_2" in report["errors"]
    assert report["observed_2027_titles"][0]["event_id"] == "123"
    assert "season_2027_titles" not in report


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
    assert report["event_rows"] is None and report["fixture_rows"] == 0
    assert report["observed_2027_titles"] == []


def test_partial_upcoming_outage_preserves_event_title_without_false_zero(monkeypatch, capsys):
    monkeypatch.setattr(titles.vlrgg, "fetch_events", lambda page, save: payload([
        {"title": "VCT 2027: Pacific LCQ", "event_id": "123"}]))
    monkeypatch.setattr(titles.vlrgg, "fetch_upcoming_matches", lambda save: payload({}))
    monkeypatch.setattr(sys, "argv", ["open_era_title_audit.py"])
    with pytest.raises(SystemExit) as exc:
        titles.main()
    assert exc.value.code == 1
    report = json.loads(capsys.readouterr().out)
    assert report["complete"] is False
    assert report["event_rows"] == 1 and report["fixture_rows"] is None
    assert "upcoming" in report["errors"]
    assert report["observed_2027_titles"][0]["event_id"] == "123"
    assert report["observed_2027_titles"][0]["upcoming_fixtures"] is None
    assert "season_2027_titles" not in report


def test_partial_event_outage_preserves_fixture_title_without_event_lineage(monkeypatch, capsys):
    monkeypatch.setattr(titles.vlrgg, "fetch_events", lambda page, save: payload({}))
    monkeypatch.setattr(titles.vlrgg, "fetch_upcoming_matches", lambda save: payload([
        {"match_event": "VCT 2027: Pacific LCQ"}]))
    monkeypatch.setattr(sys, "argv", ["open_era_title_audit.py"])
    with pytest.raises(SystemExit) as exc:
        titles.main()
    assert exc.value.code == 1
    report = json.loads(capsys.readouterr().out)
    assert report["event_rows"] is None and report["fixture_rows"] == 1
    assert report["observed_2027_titles"][0]["event_id"] is None
    assert report["observed_2027_titles"][0]["upcoming_fixtures"] == 1
