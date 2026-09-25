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
    assert row["candidate_scope_changes"] == [{
        "match_page": "101/november", "scheduled_at": "2026-11-15 09:00:00",
        "current_tier": 1, "candidate_tier": 2,
    }]
    assert "tier_current" not in row


def test_candidate_scope_audit_catches_long_prefix_hidden_from_current_mismatch():
    title = "Champions Tour 2027: Pacific LCQ"
    events = payload([{"title": title, "event_id": "123"}])
    upcoming = payload([
        {"match_event": title, "unix_timestamp": "2026-11-15 09:00:00",
         "match_page": "101/november"},
        {"match_event": title, "unix_timestamp": "2027-01-15 09:00:00",
         "match_page": "102/january"},
    ])
    row = titles.audit(events, upcoming)[0]
    assert row["calendar_tier_mismatches"] == []  # Both current paths say Tier 1.
    assert row["candidate_tier_if_2026"] == 2
    assert row["candidate_tier_by_title"] == 2
    assert row["candidate_scope_changes"] == [
        {"match_page": "101/november", "scheduled_at": "2026-11-15 09:00:00",
         "current_tier": 1, "candidate_tier": 2},
        {"match_page": "102/january", "scheduled_at": "2027-01-15 09:00:00",
         "current_tier": 1, "candidate_tier": 2},
    ]


def test_candidate_scope_audit_does_not_assume_year_on_feed_outage():
    row = titles.audit(payload([{"title": "Champions Tour 2027: Pacific LCQ"}]), None)[0]
    assert row["candidate_tier_if_2026"] == 2
    assert row["candidate_scope_changes"] is None


def test_unknown_fixture_date_is_not_counted_as_no_calendar_disagreement():
    row = titles.audit(payload([]), payload([
        {"match_event": "VCT 2027: Pacific LCQ", "unix_timestamp": "TBD", "match_page": "103/tbd"},
    ]))[0]
    assert row["upcoming_fixtures"] == 1
    assert row["unparsed_fixture_dates"] == 1
    assert row["fixture_calendar_years"] == []
    assert row["calendar_tier_mismatches"] == []


def test_yearless_open_title_is_flagged_from_late_2026_fixture_not_called_2027():
    upcoming = payload([
        {"match_event": "VCT Pacific: Open Qualifier", "unix_timestamp": "2026-11-15 09:00:00",
         "match_page": "201/open"},
        {"match_event": "VCT Pacific: Open Qualifier", "unix_timestamp": "2026-12-01 09:00:00",
         "match_page": "202/open"},
        {"match_event": "VCT Pacific: Open Qualifier", "unix_timestamp": "2026-09-01 09:00:00"},
        {"match_event": "VCT 2026: Pacific LCQ", "unix_timestamp": "2026-11-15 09:00:00"},
        {"match_event": "Third Party Open Qualifier", "unix_timestamp": "2027-01-01 09:00:00"},
        {"match_event": "VCT Pacific: Kickoff", "unix_timestamp": "2027-01-01 09:00:00"},
        {"match_event": "VCT Pacific: LCQ", "unix_timestamp": "TBD"},
    ])
    assert titles.audit(payload([]), upcoming) == []
    assert titles.yearless_open_candidates(upcoming) == [{
        "title": "VCT Pacific: Open Qualifier", "fixture_count": 2,
        "fixtures": [{"match_page": "201/open", "scheduled_at": "2026-11-15 09:00:00"},
                     {"match_page": "202/open", "scheduled_at": "2026-12-01 09:00:00"}],
    }]


def test_yearless_event_candidates_include_upcoming_open_stages_without_fixtures():
    events = [payload([
        {"title": "VCT Pacific: Open Qualifier", "status": "upcoming", "dates": "Nov 15—20",
         "event_id": "301", "url_path": "https://www.vlr.gg/event/301/open"},
        {"title": "VCT Americas: LCQ", "status": "ongoing", "dates": "Nov 1—10",
         "event_id": "302"},
        {"title": "VCT Pacific: Kickoff", "status": "upcoming"},
        {"title": "VCT 2026: Pacific Open Qualifier", "status": "upcoming"},
        {"title": "Community Open Qualifier", "status": "upcoming"},
        {"title": "VCT Pacific: Open Playoffs", "status": "completed"},
    ])]
    assert titles.yearless_open_event_candidates(events) == [{
        "title": "VCT Pacific: Open Qualifier", "event_id": "301",
        "event_url": "https://www.vlr.gg/event/301/open", "status": "upcoming",
        "dates_raw": "Nov 15—20",
    }]
    assert titles.yearless_open_event_candidates([]) is None


def test_yearless_primary_stage_leads_include_kickoff_and_cups_not_open_stages():
    events = [payload([
        {"title": "VCT Americas: Kickoff", "status": "upcoming", "event_id": "401"},
        {"title": "Champions Tour Pacific: Cup 1", "status": "upcoming", "event_id": "402"},
        {"title": "VCT EMEA: Open Qualifier", "status": "upcoming", "event_id": "403"},
        {"title": "VCT 2026: Kickoff", "status": "upcoming", "event_id": "404"},
        {"title": "VCT Pacific: Cup 2", "status": "completed", "event_id": "405"},
    ])]
    upcoming = payload([
        {"match_event": "VCT Americas: Kickoff", "unix_timestamp": "2026-11-15 09:00:00",
         "match_page": "401/kickoff"},
        {"match_event": "Champions Tour Pacific: Cup 1", "unix_timestamp": "2027-04-10 09:00:00",
         "match_page": "402/cup"},
        {"match_event": "VCT Americas: Kickoff", "unix_timestamp": "2026-10-01 09:00:00"},
        {"match_event": "VCT EMEA: Open Qualifier", "unix_timestamp": "2027-01-01 09:00:00"},
        {"match_event": "VCT 2026: Kickoff", "unix_timestamp": "2027-01-01 09:00:00"},
    ])
    assert [row["event_id"] for row in titles.yearless_primary_event_candidates(events)] == ["402", "401"]
    assert [row["title"] for row in titles.yearless_primary_candidates(upcoming)] == [
        "Champions Tour Pacific: Cup 1", "VCT Americas: Kickoff"]
    assert titles.yearless_primary_event_candidates([]) is None
    assert titles.yearless_primary_candidates(None) is None


def test_primary_stage_leads_remain_unknown_on_partial_outage(monkeypatch, capsys):
    monkeypatch.setattr(titles.vlrgg, "fetch_events", lambda page, save: payload([
        {"title": "VCT Americas: Kickoff", "status": "upcoming", "event_id": "401"}]))
    monkeypatch.setattr(titles.vlrgg, "fetch_upcoming_matches", lambda save: payload({}))
    monkeypatch.setattr(sys, "argv", ["open_era_title_audit.py"])
    with pytest.raises(SystemExit):
        titles.main()
    report = json.loads(capsys.readouterr().out)
    assert report["yearless_primary_event_candidates"][0]["event_id"] == "401"
    assert report["yearless_primary_candidates"] is None
    assert report["complete"] is False


def test_yearless_event_candidates_survive_partial_upcoming_outage(monkeypatch, capsys):
    monkeypatch.setattr(titles.vlrgg, "fetch_events", lambda page, save: payload([
        {"title": "VCT Pacific: Open Qualifier", "status": "upcoming", "event_id": "301"}]))
    monkeypatch.setattr(titles.vlrgg, "fetch_upcoming_matches", lambda save: payload({}))
    monkeypatch.setattr(sys, "argv", ["open_era_title_audit.py"])
    with pytest.raises(SystemExit):
        titles.main()
    report = json.loads(capsys.readouterr().out)
    assert report["yearless_open_event_candidates"][0]["event_id"] == "301"
    assert report["yearless_open_candidates"] is None


def test_yearless_candidates_survive_partial_event_outage(monkeypatch, capsys):
    monkeypatch.setattr(titles.vlrgg, "fetch_events", lambda page, save: payload({}))
    monkeypatch.setattr(titles.vlrgg, "fetch_upcoming_matches", lambda save: payload([
        {"match_event": "VCT Pacific: LCQ", "unix_timestamp": "2027-01-15 09:00:00",
         "match_page": "203/lcq"}]))
    monkeypatch.setattr(sys, "argv", ["open_era_title_audit.py"])
    with pytest.raises(SystemExit):
        titles.main()
    report = json.loads(capsys.readouterr().out)
    assert report["yearless_open_candidates"][0]["title"] == "VCT Pacific: LCQ"
    assert report["complete"] is False


def test_error_envelopes_are_not_empty_event_pages():
    for bad in ({"status": "error", "data": {"segments": []}},
                {"status": "success", "data": None},
                {"status": "success", "data": {"status": 200}},
                {"status": "success", "data": {"status": 502, "segments": []}},
                {"status": "success", "data": {"status": 200, "segments": {}}}):
        with pytest.raises(ValueError):
            titles.segments(bad)


def test_duplicate_event_page_is_incomplete_not_extra_coverage(monkeypatch, capsys):
    first = payload([{"title": "VCT 2026: Champions", "event_id": "101"}])
    monkeypatch.setattr(titles.vlrgg, "fetch_events", lambda page, save: first)
    monkeypatch.setattr(titles.vlrgg, "fetch_upcoming_matches", lambda save: payload([]))
    monkeypatch.setattr(sys, "argv", ["open_era_title_audit.py", "--event-pages", "2"])
    with pytest.raises(SystemExit) as exc:
        titles.main()
    assert exc.value.code == 1
    report = json.loads(capsys.readouterr().out)
    assert report["complete"] is False
    assert report["event_pages_checked"] == [1]
    assert report["event_rows"] == 1
    assert "duplicate of page 1" in report["errors"]["events_page_2"]
    assert report["observed_2027_titles"] == []


def test_distinct_empty_event_pages_do_not_falsely_trigger_duplicate(monkeypatch, capsys):
    monkeypatch.setattr(titles.vlrgg, "fetch_events", lambda page, save: payload([]))
    monkeypatch.setattr(titles.vlrgg, "fetch_upcoming_matches", lambda save: payload([]))
    monkeypatch.setattr(sys, "argv", ["open_era_title_audit.py", "--event-pages", "2"])
    titles.main()
    report = json.loads(capsys.readouterr().out)
    assert report["complete"] is True
    assert report["event_pages_checked"] == [1, 2]


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


def test_live_pagination_stops_after_first_failure_but_still_checks_upcoming(monkeypatch, capsys):
    fetched = []
    def fetch(page, save):
        fetched.append(page)
        if page == 2:
            raise ValueError("page 2 down")
        return payload([{"title": "VCT 2027: Pacific LCQ", "event_id": "123"}])

    monkeypatch.setattr(titles.vlrgg, "fetch_events", fetch)
    monkeypatch.setattr(titles.vlrgg, "fetch_upcoming_matches", lambda save: payload([]))
    monkeypatch.setattr(sys, "argv", ["open_era_title_audit.py", "--event-pages", "9"])
    with pytest.raises(SystemExit) as exc:
        titles.main()
    assert exc.value.code == 1
    report = json.loads(capsys.readouterr().out)
    assert fetched == [1, 2]  # Do not hammer a failing upstream eight more times.
    assert report["event_pages_requested"] == 9
    assert report["event_pages_checked"] == [1]
    assert report["event_pages_skipped"] == [3, 4, 5, 6, 7, 8, 9]
    assert "events_page_2" in report["errors"]
    assert report["fixture_rows"] == 0
    assert report["observed_2027_titles"][0]["event_id"] == "123"


def test_archive_page_failure_does_not_hide_later_independent_files(tmp_path, monkeypatch, capsys):
    first = tmp_path / "first.json"
    missing = tmp_path / "missing.json"
    third = tmp_path / "third.json"
    feed = tmp_path / "feed.json"
    first.write_text(json.dumps(payload([])))
    third.write_text(json.dumps(payload([{"title": "VCT 2027: Pacific LCQ", "event_id": "123"}])))
    feed.write_text(json.dumps(payload([])))
    monkeypatch.setattr(sys, "argv", ["open_era_title_audit.py", "--events-json",
                                   str(first), str(missing), str(third), "--upcoming-json", str(feed)])
    with pytest.raises(SystemExit) as exc:
        titles.main()
    assert exc.value.code == 1
    report = json.loads(capsys.readouterr().out)
    assert report["event_pages_checked"] == [1, 3]
    assert report["event_pages_skipped"] == []
    assert report["observed_2027_titles"][0]["event_id"] == "123"


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
    assert report["yearless_open_candidates"] is None
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
