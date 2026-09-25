import json

import pandas as pd
import pytest

from vct_quant.etl import normalize
from vct_quant.etl import events
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
    assert competition_tier("Game Changers 2025: Championship Seoul") == 3


def test_vct_2027_open_stages_stay_out_of_tier_1():
    # vlr.gg has no 2027 names yet; these follow its 2023-26 "VCT YYYY:" pattern.
    # Replace with the real titles once the Kickoff qualifiers are listed.
    assert competition_tier("VCT 2027: Americas Kickoff") == 1
    assert competition_tier("VCT 2027: EMEA Cup 1") == 1
    assert competition_tier("Valorant Masters Santiago 2027") == 1
    assert competition_tier("VCT 2027: North America Open Qualifier") == 2
    assert competition_tier("VCT 2027: Türkiye Open Qualifiers 2") == 2
    assert competition_tier("VCT 2027: EMEA Open Playoffs") == 2
    assert competition_tier("VCT 2027: Pacific Wild Card") == 2
    assert competition_tier("VCT 2027: Pacific Last Chance Qualifier") == 2
    # Pre-2027 LCQs were partner teams playing for Champions: still Tier 1.
    assert competition_tier("Champions Tour 2023: Pacific Last Chance Qualifier", 2023) == 1
    assert competition_tier("VCT 2024: Pacific Last Chance Qualifier") == 1


def test_opt_in_uses_2027_event_season_for_november_2026_lcq(monkeypatch):
    # November qualifiers feed the 2027 circuit, but their fixture calendar
    # year is 2026. The opt-in must not relabel the 2026 Champions LCQ.
    monkeypatch.setattr(events, "OPEN_ERA_TITLE_SEASON", True, raising=False)
    assert competition_tier("VCT 2027: Pacific Last Chance Qualifier", 2026) == 2
    assert competition_tier("Champions Tour 2027: Pacific LCQ", 2026) == 2
    assert competition_tier("VCT 2026: Pacific Last Chance Qualifier", 2027) == 1


def test_opt_in_classifies_long_champions_tour_open_stages(monkeypatch):
    title = "Champions Tour 2027: Americas Open Qualifiers"
    assert competition_tier(title, 2026) == 1  # Disabled: primary scope unchanged.
    monkeypatch.setattr(events, "OPEN_ERA_TITLE_SEASON", True)
    assert competition_tier(title, 2026) == 2
    assert competition_tier("Champions Tour 2026: Americas Open Qualifiers", 2026) == 1


def test_explicit_candidate_override_is_pure_and_keeps_primary_off():
    title = "Champions Tour 2027: Americas Open Qualifiers"
    assert events.OPEN_ERA_TITLE_SEASON is False
    assert competition_tier(title, 2026, title_season_override=True) == 2
    assert competition_tier(title, 2026) == 1
    assert competition_tier(title, 2026, title_season_override=False) == 1
    assert events.OPEN_ERA_TITLE_SEASON is False


def test_open_era_title_season_flag_is_off_by_default():
    assert events.OPEN_ERA_TITLE_SEASON is False
    assert competition_tier("VCT 2027: Pacific Last Chance Qualifier", 2026) == 1


def test_stored_event_lcq_reclassification_is_opt_in(monkeypatch):
    import duckdb
    from vct_quant.etl.normalize import LoadReport, _classify_stored_events

    con = duckdb.connect()
    con.execute("CREATE TABLE event (event_id BIGINT, name TEXT, dates_raw TEXT, tier SMALLINT)")
    con.execute("INSERT INTO event VALUES (1, 'VCT 2027: Pacific LCQ', '2026', 1)")
    _classify_stored_events(con, LoadReport())
    assert con.execute("SELECT tier FROM event").fetchone() == (1,)
    monkeypatch.setattr(events, "OPEN_ERA_TITLE_SEASON", True)
    _classify_stored_events(con, LoadReport())
    assert con.execute("SELECT tier FROM event").fetchone() == (2,)


def test_untiered_vct_titles_flags_only_unknown_official_events():
    from vct_quant.etl.events import untiered_vct_titles

    assert untiered_vct_titles([
        "VCT 2027: Americas Kickoff",
        "VCT OFF//SEASON Spotlight Series 2024: EMEA",
        "NECC Valorant Champions Finals - Spring 2023",
        "Red Bull Home Ground",
        "VCT Cup Americas 2027",
    ]) == ["VCT Cup Americas 2027"]


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


def test_archived_error_feed_does_not_poison_event_and_match_replay(tmp_path, monkeypatch):
    """An HTTP-200 failure archived by ingestion must not mask older good raw."""
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
    def good(row):
        return {"status": "success", "data": {"status": 200, "segments": [row]}}

    (tmp_path / "events_page001_20260925T000000Z.json").write_text(json.dumps(good(event)))
    (tmp_path / "event_matches_42_20260925T000000Z.json").write_text(json.dumps(good(match)))
    # Invalid success and explicit error envelopes are both saved for diagnosis.
    (tmp_path / "events_page001_20260925T010000Z.json").write_text(json.dumps({
        "status": "error", "data": {"status": 503, "message": "Circuit open"}}))
    (tmp_path / "event_matches_42_20260925T010000Z.json").write_text(json.dumps({
        "status": "success", "data": {"status": 200, "segments": None}}))
    with pytest.warns(UserWarning, match="invalid archived vlrggapi feed") as caught:
        events = normalize._vlrgg_events()
        matches = normalize._vlrgg_event_matches(events)
    assert len(caught) == 2
    assert events.event_id.tolist() == [42]
    assert matches.match_id.tolist() == [99]


def test_match_detail_replay_keeps_valid_snapshot_before_poison(tmp_path, monkeypatch):
    import json
    import pytest
    from vct_quant.etl import normalize

    monkeypatch.setattr(normalize, "RAW_VLRGG_DIR", tmp_path)
    good = {"status": "success", "data": {"status": 200, "segments": [
        {"match_id": "42", "teams": [{"id": "17", "name": "NRG"}], "maps": []}
    ]}}
    (tmp_path / "match_details_42_20260925T070000Z.json").write_text(json.dumps(good))
    poison = {"status": "error", "data": {"segments": None}}
    (tmp_path / "match_details_42_20260925T080000Z.json").write_text(json.dumps(poison))
    (tmp_path / "match_details_43_20260925T080000Z.json").write_text(json.dumps(poison))
    with pytest.warns(UserWarning, match="Skipping invalid archived detail") as recorded:
        assert normalize._vlrgg_match_details() == good["data"]["segments"]
    assert len(recorded) == 2
    assert "match_details_42_20260925T080000Z.json" in str(recorded[0].message)
    assert "match_details_43_20260925T080000Z.json" in str(recorded[1].message)


def test_match_details_skip_matches_whose_maps_already_exist(tmp_path, monkeypatch):
    # Kaggle can load a match's maps without any player rows. A detail payload
    # for that match must not re-insert the maps (duplicate map_number).
    import duckdb

    from vct_quant import db

    monkeypatch.setattr(normalize, "RAW_VLRGG_DIR", tmp_path)
    con = duckdb.connect()
    db.init_db(con)
    con.execute("INSERT INTO match (match_id, status) VALUES (10267, 'completed')")
    con.execute("INSERT INTO match_map (match_id, map_number, map_name) VALUES (10267, 1, 'Bind')")
    (tmp_path / "match_details_10267_test.json").write_text(json.dumps({"data": {
        "match_id": "10267",
        "teams": [],
        "maps": [{
            "map_name": "Bind",
            "score": {"team1": 13, "team2": 3},
            "players": {"team1": [{"name": "p1", "kills": "20"}], "team2": []},
        }],
    }}))

    normalize.load_vlrgg_match_details(con)

    assert con.execute("SELECT count(*) FROM match_map").fetchone() == (1,)


def test_match_details_resolve_missing_team_ids(tmp_path, monkeypatch):
    # The event feed carries names only, so "NRG" never matched "NRG Esports"
    # and started a separate 1500-rated history. Detail payloads carry IDs.
    import duckdb

    from vct_quant import db

    monkeypatch.setattr(normalize, "RAW_VLRGG_DIR", tmp_path)
    con = duckdb.connect()
    db.init_db(con)
    con.execute("INSERT INTO team (team_id, name) VALUES (1034, 'NRG Esports')")
    for match_id in (1, 2):
        con.execute(f"INSERT INTO match (match_id, status) VALUES ({match_id}, 'completed')")
        con.execute(f"""INSERT INTO match_team (match_id, team_number, team_id, team_name)
                        VALUES ({match_id}, 1, NULL, 'NRG'), ({match_id}, 2, NULL, 'LEVIATÁN')""")
    # Only match 1 has a detail payload; its IDs must also resolve match 2.
    (tmp_path / "match_details_1_test.json").write_text(json.dumps({"data": {
        "match_id": "1",
        "teams": [{"id": "1034", "name": "NRG"}, {"id": "2359", "name": "LEVIATÁN"}],
        "maps": [],
    }}))

    normalize.load_vlrgg_match_details(con)

    rows = con.execute(
        "SELECT match_id, team_name, team_id FROM match_team ORDER BY match_id, team_number"
    ).fetchall()
    assert rows == [(1, "NRG", 1034), (1, "LEVIATÁN", 2359), (2, "NRG", 1034), (2, "LEVIATÁN", 2359)]
    assert con.execute("SELECT name FROM team WHERE team_id = 2359").fetchone() == ("LEVIATÁN",)
