"""Playoff block on the Champions payload: verified pairings joined to fixtures."""
import copy
import duckdb
import pandas as pd

from vct_quant.champions_status import attach_playoffs, champions_status, playoff_results
from vct_quant.event_bracket import load_bracket_spec


def fixture(match_id, team_a, team_b, p_a, **extra):
    return {
        "match_id": match_id, "start": "2026-10-07T09:00:00+00:00", "best_of": 3,
        "team_a": team_a, "team_b": team_b,
        "logo_a": f"/logos/{team_a}.png", "logo_b": f"/logos/{team_b}.png",
        "tag_a": team_a[:3], "tag_b": None,
        "p_a": p_a, "p_sweep": 0.5, "matches_a": 100, "matches_b": 12,
        "market": None, "spread": None, "volume": None,
        "url": f"https://www.vlr.gg/{match_id}/x", **extra,
    }


def all_fixtures():
    return [
        fixture(754732, "NRG", "T1", 0.6),
        fixture(754733, "Paper Rex", "LOUD", 0.55),
        fixture(754730, "100 Thieves", "G2 Esports", 0.59, start="2026-10-08T09:00:00+00:00"),
        fixture(754731, "Team Vitality", "Nongshim RedForce", 0.41, market=0.45, spread=0.02, volume=1234.0),
    ]


def schedule():
    return [
        {"match_id": 754738, "start": "2026-10-09T09:00:00+00:00", "best_of": 3},
        {"match_id": 754737, "start": "2026-10-18T06:00:00+00:00", "best_of": 5},
        {"match_id": 754730, "start": "2026-10-08T09:00:00+00:00", "best_of": 3},
    ]


def status():
    return {"event_id": 2766, "playoff_routing": "unresolved", "title_odds": None, "groups": {}}


def test_attach_playoffs_joins_pairings_to_fixtures_in_spec_order():
    out = attach_playoffs(status(), load_bracket_spec(2766), all_fixtures(), schedule())
    block = out["playoffs"]
    assert [m["match_id"] for m in block["opening"]] == [754730, 754731, 754732, 754733]
    first = block["opening"][0]
    assert first["stage"] == "Upper Quarterfinals"
    assert [s["name"] for s in first["sides"]] == ["100 Thieves", "G2 Esports"]
    assert [s["team_id"] for s in first["sides"]] == [120, 11058]
    assert first["sides"][0]["p_win"] == 0.59 and abs(first["sides"][1]["p_win"] - 0.41) < 1e-12
    assert first["sides"][0]["logo"] == "/logos/100 Thieves.png"
    assert first["start"] == "2026-10-08T09:00:00+00:00" and first["best_of"] == 3
    assert first["market"] is None
    vit = block["opening"][1]
    assert vit["market"] == {"p_a": 0.45, "spread": 0.02, "volume": 1234.0}
    assert block["observed_at"] == "2026-10-04T16:02:00Z"
    assert len(block["sources"]) >= 2


def test_attach_playoffs_never_adds_title_odds_or_routing():
    out = attach_playoffs(status(), load_bracket_spec(2766), all_fixtures(), schedule())
    assert out["title_odds"] is None and out["playoff_routing"] == "unresolved"
    assert out["playoffs"]["routing"] == "unresolved"


def test_attach_playoffs_flips_when_fixture_orientation_is_reversed():
    flipped = fixture(754732, "T1", "NRG", 0.4)
    fixtures = [flipped] + [f for f in all_fixtures() if f["match_id"] != 754732]
    match = next(m for m in attach_playoffs(status(), load_bracket_spec(2766), fixtures, [])["playoffs"]["opening"]
                 if m["match_id"] == 754732)
    assert [s["name"] for s in match["sides"]] == ["NRG", "T1"]
    assert abs(match["sides"][0]["p_win"] - 0.6) < 1e-12


def test_attach_playoffs_withholds_forecast_on_team_mismatch_or_missing_fixture():
    fixtures = [fixture(754732, "NRG", "Fnatic", 0.6)] + [f for f in all_fixtures() if f["match_id"] not in (754732, 754733)]
    opening = attach_playoffs(status(), load_bracket_spec(2766), fixtures, [])["playoffs"]["opening"]
    by_id = {m["match_id"]: m for m in opening}
    for match_id in (754732, 754733):
        match = by_id[match_id]
        assert match["start"] is None and match["market"] is None
        assert all(s["p_win"] is None for s in match["sides"])
        assert match["sides"][0]["name"] in ("NRG", "Paper Rex")  # pinned names still shown
    assert by_id[754730]["sides"][0]["p_win"] == 0.59


def test_attach_playoffs_schedule_lists_only_later_slots_with_tbd_participants():
    out = attach_playoffs(status(), load_bracket_spec(2766), all_fixtures(), schedule())
    rows = out["playoffs"]["schedule"]
    ids = [r["match_id"] for r in rows]
    assert 754730 not in ids  # opening pairings are not repeated
    assert len(rows) == 10
    assert [r["match_id"] for r in rows if r["start"]] == [754738, 754737]  # chronological, undated last
    gf = next(r for r in rows if r["match_id"] == 754737)
    assert gf["stage"] == "Grand Final" and gf["best_of"] == 5 and gf["start"] == "2026-10-18T06:00:00+00:00"
    assert "sides" not in gf and "team_ids" not in gf
    undated = next(r for r in rows if r["match_id"] == 754743)
    assert undated["start"] is None and undated["best_of"] == 5


def test_attach_playoffs_does_not_mutate_spec_or_invent_without_verified_pairings():
    spec = load_bracket_spec(2766)
    before = copy.deepcopy(spec)
    attach_playoffs(status(), spec, all_fixtures(), schedule())
    assert spec == before
    bare = copy.deepcopy(spec)
    bare["verified_opening_pairings"] = []
    assert "playoffs" not in attach_playoffs(status(), bare, all_fixtures(), schedule())


def playoff_db(rows):
    db = duckdb.connect(":memory:")
    db.execute("CREATE TABLE match (match_id BIGINT, event_id BIGINT, event_series VARCHAR, status VARCHAR, last_seen_at TIMESTAMP, scheduled_at TIMESTAMP, completed_at TIMESTAMP, best_of INT, vlr_url VARCHAR)")
    db.execute("CREATE TABLE match_team (match_id BIGINT, team_number INT, team_id BIGINT, team_name VARCHAR, series_score INT, is_winner BOOLEAN)")
    for mid, event, stage, scores, ids, flags, last_seen in rows:
        db.execute("INSERT INTO match VALUES (?, ?, ?, 'completed', ?, NULL, ?, 3, ?)", [mid, event, stage, last_seen, last_seen, f"https://www.vlr.gg/{mid}/db"])
        for n in range(2):
            db.execute("INSERT INTO match_team VALUES (?, ?, ?, ?, ?, ?)", [mid, n + 1, ids[n], f"Team {ids[n]}", scores[n], flags[n]])
    return db


def row(mid, stage="Upper Quarterfinals", scores=(2, 0), ids=(11058, 120), flags=(True, False), event=2766,
        last_seen="2026-10-08 14:15:20"):
    return mid, event, stage, list(scores), list(ids), list(flags), last_seen


def add_group_row(db, last_seen="2026-10-04 14:15:20"):
    db.execute("INSERT INTO match VALUES (753454, 2766, 'Opening (C)', 'completed', ?, NULL, NULL, NULL, NULL)", [last_seen])
    db.execute("INSERT INTO match_team VALUES (753454, 1, 731, 'Team 731', 0, false), (753454, 2, 11058, 'Team 11058', 2, true)")


def test_playoff_last_seen_advances_top_level_as_of():
    spec = load_bracket_spec(2766)
    db = playoff_db([row(754730)])
    add_group_row(db)
    results = playoff_results(db, spec)
    status = champions_status(db, spec)
    out = attach_playoffs(status, spec, all_fixtures(), schedule(), results)
    assert out["as_of"] == "2026-10-08T14:15:20"
    db.close()


@__import__("pytest").mark.parametrize("playoff_rows", [
    [row(754730, last_seen="2026-10-03 14:15:20")],
    [],
    [row(754730, last_seen=None)],
])
def test_playoff_as_of_does_not_replace_later_group_timestamp(playoff_rows):
    spec = load_bracket_spec(2766)
    db = playoff_db(playoff_rows)
    add_group_row(db)
    results = playoff_results(db, spec)
    status = champions_status(db, spec)
    out = attach_playoffs(status, spec, all_fixtures(), schedule(), results)
    assert out["as_of"] == "2026-10-04T14:15:20"
    db.close()


def test_all_group_and_playoff_timestamps_null_yield_none():
    spec = load_bracket_spec(2766)
    db = playoff_db([row(754730, last_seen=None)])
    add_group_row(db, None)
    results = playoff_results(db, spec)
    assert results.last_seen_at is None
    status = champions_status(db, spec)
    out = attach_playoffs(status, spec, all_fixtures(), schedule(), results)
    assert out["as_of"] is None
    db.close()


def test_playoff_results_and_opening_result_follow_pinned_side_order():
    spec = load_bracket_spec(2766)
    db = playoff_db([row(754730, ids=(11058, 120), scores=(2, 0))])
    results = playoff_results(db, spec)
    assert results[754730] == {"team_ids": [11058, 120], "scores": [2, 0]}
    out = attach_playoffs(status(), spec, all_fixtures(), schedule(), results)
    first = out["playoffs"]["opening"][0]
    assert [s["team_id"] for s in first["sides"]] == [120, 11058]
    assert first["result"] == {"winner_team_id": 11058, "scores": [0, 2]}
    db.close()


def test_completed_opening_without_fixture_uses_db_and_team_metadata_without_forecast():
    spec = load_bracket_spec(2766)
    db = playoff_db([row(754730)])
    results = playoff_results(db, spec)
    out = attach_playoffs(status(), spec, [], [], results,
                          logos={"120": "/120.png", "11058": "/11058.png"},
                          tags={"120": "100T", "11058": "G2"})["playoffs"]["opening"][0]
    assert out["best_of"] == 3 and out["url"] == "https://www.vlr.gg/754730/db"
    assert out["played_on"] == "2026-10-08" and out["start"] is None
    assert [(s["logo"], s["tag"]) for s in out["sides"]] == [("/120.png", "100T"), ("/11058.png", "G2")]
    assert all(s["p_win"] is None and s["matches"] is None for s in out["sides"])
    assert out["market"] is None
    no_maps = attach_playoffs(status(), spec, [], [], results)["playoffs"]["opening"][0]
    assert all(s["logo"] is None and s["tag"] is None for s in no_maps["sides"])
    db.close()


def test_later_schedule_played_on_requires_verified_result():
    spec = load_bracket_spec(2766)
    db = playoff_db([row(754734, "Upper Semifinals", (2, 1), (2050, 11058), (True, False)),
                     row(754735, "Upper Semifinals", (2, 0), (3050, 4050), (True, False))])
    results = playoff_results(db, spec)
    slots = [{"match_id": mid, "teams": [f"Team {a}", f"Team {b}"], "team_ids": [a, b]}
             for mid, a, b in ((754734, 2050, 11058), (754735, 3050, 4050))]
    results.pop(754735)
    rows = attach_playoffs(status(), spec, [], slots, results)["playoffs"]["schedule"]
    assert next(r for r in rows if r["match_id"] == 754734)["played_on"] == "2026-10-08"
    assert next(r for r in rows if r["match_id"] == 754735)["played_on"] is None
    db.close()


@__import__("pytest").mark.parametrize("bad", [
    row(754730, scores=(1, 1), flags=(False, False)),
    row(754730, stage="Lower Round 1"),
    row(754730, event=999),
    row(754730, flags=(False, False)),
])
def test_playoff_results_reject_bad_rows_and_list_them(bad):
    spec = load_bracket_spec(2766)
    db = playoff_db([bad])
    results = playoff_results(db, spec)
    assert 754730 not in results and results.unverified == [754730]
    block = attach_playoffs(status(), spec, all_fixtures(), [], results)["playoffs"]
    assert block["opening"][0]["result"] is None
    assert block["unverified_match_ids"] == [754730]
    db.close()


def test_bo5_decisive_score_validation():
    spec = load_bracket_spec(2766)
    db = playoff_db([row(754743, "Lower Final", (3, 2), (10, 20), (True, False)),
                     row(754737, "Grand Final", (2, 1), (30, 40), (True, False))])
    results = playoff_results(db, spec)
    assert results[754743]["scores"] == [3, 2]
    assert 754737 not in results and results.unverified == [754737]
    db.close()


def test_later_slot_sides_join_fixture_in_both_orientations_and_completed_result():
    spec = load_bracket_spec(2766)
    for reversed_fixture in (False, True):
        slot_fixture = fixture(754734, *(('Team Vitality', 'G2 Esports') if reversed_fixture else ('G2 Esports', 'Team Vitality')), .62)
        slot = {"match_id": 754734, "start": "2026-10-10T00:00:00+00:00", "best_of": 3,
                "teams": ["G2 Esports", "Team Vitality"], "team_ids": [11058, 2050]}
        db = playoff_db([row(754734, "Upper Semifinals", (2, 1), (2050, 11058), (True, False)),
                         row(754735, "Upper Semifinals", (2, 0), (3050, 4050), (True, False))])
        results = playoff_results(db, spec)
        out = attach_playoffs(status(), spec, [slot_fixture], [slot], results)["playoffs"]
        later = next(item for item in out["schedule"] if item["match_id"] == 754734)
        assert [s["team_id"] for s in later["sides"]] == [11058, 2050]
        assert [s["name"] for s in later["sides"]] == ["Team 11058", "Team 2050"]
        assert [s["logo"] for s in later["sides"]] == [f"/logos/{slot_fixture['team_b' if reversed_fixture else 'team_a']}.png",
                                                            f"/logos/{slot_fixture['team_a' if reversed_fixture else 'team_b']}.png"]
        assert [s["tag"] for s in later["sides"]] == [slot_fixture["tag_b" if reversed_fixture else "tag_a"],
                                                          slot_fixture["tag_a" if reversed_fixture else "tag_b"]]
        assert [s["matches"] for s in later["sides"]] == ([12, 100] if reversed_fixture else [100, 12])
        assert [s["p_win"] for s in later["sides"]] == ([.38, .62] if reversed_fixture else [.62, .38])
        assert later["result"] == {"winner_team_id": 2050, "scores": [1, 2]}
        completed_only = next(item for item in out["schedule"] if item["match_id"] == 754735)
        assert [side["team_id"] for side in completed_only["sides"]] == [3050, 4050]
        assert [side["name"] for side in completed_only["sides"]] == ["Team 3050", "Team 4050"]
        assert completed_only["result"] == {"winner_team_id": 3050, "scores": [2, 0]}
        db.close()


def test_named_schedule_sides_and_tbd_sides_with_results():
    spec = load_bracket_spec(2766)
    entries = [{"match_id": 754738, "start": None, "best_of": 3, "teams": ["NRG", "T1"], "team_ids": [1034, 14]}]
    block = attach_playoffs(status(), spec, [fixture(754738, "NRG", "T1", .7)], entries, {})["playoffs"]
    row_known = next(r for r in block["schedule"] if r["match_id"] == 754738)
    row_tbd = next(r for r in block["schedule"] if r["match_id"] == 754739)
    assert [s["name"] for s in row_known["sides"]] == ["NRG", "T1"]
    assert row_known["sides"][0]["p_win"] == .7 and abs(row_known["sides"][1]["p_win"] - .3) < 1e-12
    assert row_tbd["sides"] is None


def test_playoff_schedule_adds_numeric_team_keys_only(tmp_path, monkeypatch):
    import vct_quant.dashboard as dashboard
    monkeypatch.setattr(dashboard, "PROCESSED_DIR", tmp_path)
    pd.DataFrame([
        {"match_id": 754739, "scheduled_at": pd.Timestamp("2026-10-09"), "best_of": 3,
         "team_a_name": "T1", "team_b_name": "Paper Rex", "team_a_key": "14", "team_b_key": "624"},
        {"match_id": 754738, "scheduled_at": pd.Timestamp("2026-10-09"), "best_of": 3,
         "team_a_name": "TBD", "team_b_name": "TBD", "team_a_key": "TBD", "team_b_key": "TBD"},
    ]).to_parquet(tmp_path / "upcoming_tier1.parquet")
    rows = dashboard.playoff_schedule([754739, 754738])
    named = next(r for r in rows if r["match_id"] == 754739)
    tbd = next(r for r in rows if r["match_id"] == 754738)
    assert named["teams"] == ["T1", "Paper Rex"] and named["team_ids"] == [14, 624]
    assert "teams" not in tbd and "team_ids" not in tbd


def _prediction_rows():
    return pd.DataFrame([
        {"match_id": 754738, "scheduled_at": pd.Timestamp("2026-10-09 11:00Z"), "best_of": 3,
         "team_a_name": "Old A", "team_b_name": "Old B", "team_a_key": "1", "team_b_key": "2",
         "predicted_at": pd.Timestamp("2026-10-08 10:00Z")},
        {"match_id": 754738, "scheduled_at": pd.Timestamp("2026-10-09 12:00Z"), "best_of": 5,
         "team_a_name": "100 Thieves", "team_b_name": "Nongshim RedForce", "team_a_key": "120", "team_b_key": "11060",
         "predicted_at": pd.Timestamp("2026-10-09 11:00Z")},
    ])


def test_playoff_schedule_falls_back_to_latest_prediction_log(tmp_path, monkeypatch):
    import vct_quant.dashboard as dashboard
    monkeypatch.setattr(dashboard, "PROCESSED_DIR", tmp_path)
    _prediction_rows().to_parquet(tmp_path / "prediction_log.parquet")
    row = dashboard.playoff_schedule([754738])[0]
    assert row == {"match_id": 754738, "start": "2026-10-09T12:00:00+00:00", "best_of": 5,
                   "teams": ["100 Thieves", "Nongshim RedForce"], "team_ids": [120, 11060]}


def test_playoff_schedule_prefers_named_upcoming_row(tmp_path, monkeypatch):
    import vct_quant.dashboard as dashboard
    monkeypatch.setattr(dashboard, "PROCESSED_DIR", tmp_path)
    pd.DataFrame([{"match_id": 754738, "scheduled_at": pd.Timestamp("2026-10-09 13:00Z"), "best_of": 3,
                   "team_a_name": "Upcoming A", "team_b_name": "Upcoming B", "team_a_key": "3", "team_b_key": "4"}]
                 ).to_parquet(tmp_path / "upcoming_tier1.parquet")
    _prediction_rows().to_parquet(tmp_path / "prediction_log.parquet")
    row = dashboard.playoff_schedule([754738])[0]
    assert row["start"] == "2026-10-09T13:00:00+00:00" and row["best_of"] == 3
    assert row["teams"] == ["Upcoming A", "Upcoming B"]


def test_playoff_schedule_replaces_tbd_upcoming_with_log_names(tmp_path, monkeypatch):
    import vct_quant.dashboard as dashboard
    monkeypatch.setattr(dashboard, "PROCESSED_DIR", tmp_path)
    pd.DataFrame([{"match_id": 754738, "scheduled_at": pd.Timestamp("2026-10-09 10:00Z"), "best_of": 3,
                   "team_a_name": "TBD", "team_b_name": "TBD", "team_a_key": "TBD", "team_b_key": "TBD"}]
                 ).to_parquet(tmp_path / "upcoming_tier1.parquet")
    _prediction_rows().to_parquet(tmp_path / "prediction_log.parquet")
    row = dashboard.playoff_schedule([754738])[0]
    assert row["teams"] == ["100 Thieves", "Nongshim RedForce"]


def test_playoff_schedule_non_numeric_log_keys_only_add_start_and_format(tmp_path, monkeypatch):
    import vct_quant.dashboard as dashboard
    monkeypatch.setattr(dashboard, "PROCESSED_DIR", tmp_path)
    log = _prediction_rows().iloc[[1]].copy()
    log["team_a_key"] = "name:g2 esports"
    log.to_parquet(tmp_path / "prediction_log.parquet")
    row = dashboard.playoff_schedule([754738])[0]
    assert row["start"] and row["best_of"] == 5
    assert "teams" not in row and "team_ids" not in row


def test_playoff_schedule_log_works_without_upcoming_and_neither_file_is_empty(tmp_path, monkeypatch):
    import vct_quant.dashboard as dashboard
    monkeypatch.setattr(dashboard, "PROCESSED_DIR", tmp_path)
    _prediction_rows().to_parquet(tmp_path / "prediction_log.parquet")
    assert dashboard.playoff_schedule([754738])[0]["teams"] == ["100 Thieves", "Nongshim RedForce"]
    (tmp_path / "prediction_log.parquet").unlink()
    assert dashboard.playoff_schedule([754738]) == []


def test_log_fallback_schedule_attaches_verified_completed_result(tmp_path, monkeypatch):
    import vct_quant.dashboard as dashboard
    monkeypatch.setattr(dashboard, "PROCESSED_DIR", tmp_path)
    _prediction_rows().to_parquet(tmp_path / "prediction_log.parquet")
    slot = dashboard.playoff_schedule([754738])
    spec = load_bracket_spec(2766)
    result_db = playoff_db([row(754738, "Lower Round 1", (2, 1), (120, 11060), (True, False))])
    results = playoff_results(result_db, spec)
    out = attach_playoffs(status(), spec, [], slot, results)["playoffs"]["schedule"]
    match = next(item for item in out if item["match_id"] == 754738)
    assert match["start"] == "2026-10-09T12:00:00+00:00"
    assert [side["team_id"] for side in match["sides"]] == [120, 11060]
    assert match["result"] == {"winner_team_id": 120, "scores": [2, 1]}
    result_db.close()
