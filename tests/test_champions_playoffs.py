"""Playoff block on the Champions payload: verified pairings joined to fixtures."""
import copy

from vct_quant.champions_status import attach_playoffs
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
    assert undated["start"] is None and undated["best_of"] is None


def test_attach_playoffs_does_not_mutate_spec_or_invent_without_verified_pairings():
    spec = load_bracket_spec(2766)
    before = copy.deepcopy(spec)
    attach_playoffs(status(), spec, all_fixtures(), schedule())
    assert spec == before
    bare = copy.deepcopy(spec)
    bare["verified_opening_pairings"] = []
    assert "playoffs" not in attach_playoffs(status(), bare, all_fixtures(), schedule())
