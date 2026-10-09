"""Static Champions 2026 bracket is a source-checked *schedule*, not simulated odds."""
import json
from pathlib import Path

import pytest
from vct_quant.event_bracket import load_bracket_spec, playoff_feeds, validate_bracket_spec

ARCHIVE = Path("data/raw/vlrgg/event_matches_2766_20260926T021503Z.json")


def test_champions_bracket_has_complete_distinct_slots():
    spec = load_bracket_spec(2766)
    assert spec["event_id"] == 2766
    assert spec["playoff_seeding"] == "unresolved"
    assert isinstance(spec["playoff_advancement"], dict)
    assert len(spec["groups"]) == 4
    assert len(spec["playoffs"]) == 14
    assert len({slot["match_id"] for group in spec["groups"].values() for slot in group.values()} | {slot["match_id"] for slot in spec["playoffs"]}) == 34
    assert validate_bracket_spec(spec) is None


def test_champions_series_formats_follow_riot_official_overview():
    spec = load_bracket_spec(2766)
    assert spec["series_best_of"] == {
        "groups": 3,
        "playoffs": {stage: (5 if stage in ("Lower Final", "Grand Final") else 3)
                     for stage in (
                         "Upper Quarterfinals", "Upper Semifinals", "Upper Final",
                         "Lower Round 1", "Lower Round 2", "Lower Round 3",
                         "Lower Final", "Grand Final"
                     )},
    }
    for broken in (None, {"groups": 5, "playoffs": spec["series_best_of"]["playoffs"]},
                   {"groups": 3, "playoffs": {**spec["series_best_of"]["playoffs"], "Grand Final": 3}},
                   {"groups": True, "playoffs": spec["series_best_of"]["playoffs"]}):
        altered = json.loads(json.dumps(spec))
        if broken is None:
            del altered["series_best_of"]
        else:
            altered["series_best_of"] = broken
        with pytest.raises(ValueError, match="series format"):
            validate_bracket_spec(altered)


def test_champions_bracket_matches_archived_event_stage_and_openers():
    if not ARCHIVE.exists():
        pytest.skip("raw event snapshot is not checked into git")
    spec = load_bracket_spec(2766)
    archive = json.loads(ARCHIVE.read_text())["data"]["segments"]
    actual = {int(row["match_id"]): row for row in archive}
    slots = [slot for group in spec["groups"].values() for slot in group.values()] + spec["playoffs"]
    assert {slot["match_id"] for slot in slots} == set(actual)
    for slot in slots:
        row = actual[slot["match_id"]]
        assert slot["stage"] == row["event_series"]
        if slot.get("teams"):
            assert slot["stage"].startswith("Opening")
            assert slot["teams"] == [row["team1"]["name"], row["team2"]["name"]]


def test_champions_group_openers_have_16_unique_entrants():
    spec = load_bracket_spec(2766)
    names = [team for group in spec["groups"].values() for key in ("opening_1", "opening_2") for team in group[key]["teams"]]
    ids = [team_id for group in spec["groups"].values() for key in ("opening_1", "opening_2") for team_id in group[key]["team_ids"]]
    assert len(names) == len(set(names)) == 16
    assert len(ids) == len(set(ids)) == 16
    assert all(isinstance(team_id, int) and team_id > 0 for team_id in ids)


@pytest.mark.parametrize("bad_ids, error", [
    (None, "missing opening team IDs"),
    ([120], "invalid opening team IDs"),
    ([True, 14], "invalid opening team IDs"),
    ([120, 120], "duplicate opening team ID"),
])
def test_champions_rejects_missing_or_ambiguous_team_identity(bad_ids, error):
    spec = load_bracket_spec(2766)
    slot = spec["groups"]["A"]["opening_1"]
    if bad_ids is None:
        del slot["team_ids"]
    else:
        slot["team_ids"] = bad_ids
    with pytest.raises(ValueError, match=error):
        validate_bracket_spec(spec)


def test_champions_archived_detail_entrants_match_pinned_ids():
    spec = load_bracket_spec(2766)
    for match_id in (753454, 753460):
        files = list(Path("data/raw/vlrgg").glob(f"match_details_{match_id}_*.json"))
        if not files:
            pytest.skip("archived match detail not checked into git")
        detail = json.loads(files[-1].read_text())["data"]["segments"][0]
        assert int(detail["match_id"]) == match_id
        slot = next(slot for group in spec["groups"].values() for slot in group.values() if slot["match_id"] == match_id)
        assert slot["teams"] == [team["name"] for team in detail["teams"]]
        assert slot["team_ids"] == [int(team["id"]) for team in detail["teams"]]


def test_champions_validator_rejects_duplicate_slot_id_and_unsupported_event():
    spec = load_bracket_spec(2766)
    spec["playoffs"][0]["match_id"] = spec["groups"]["A"]["opening_1"]["match_id"]
    import pytest
    with pytest.raises(ValueError, match="duplicate match ID"):
        validate_bracket_spec(spec)
    with pytest.raises(ValueError, match="unsupported event"):
        load_bracket_spec(0)


@pytest.mark.parametrize("change,error", [
    (lambda s: s["groups"]["B"]["opening_1"]["teams"].__setitem__(0, "100 Thieves"), "duplicate opening entrant"),
    (lambda s: s["groups"]["C"]["decider"].update(teams=["TBD", "TBD"]), "future participants"),
    (lambda s: s["playoffs"][0].update(stage="Upper Final"), "incomplete playoff stage counts"),
    (lambda s: s.update(playoff_seeding="A1 vs B2"), "playoff routing"),
])
def test_bracket_rejects_unverified_or_incomplete_routes(change, error):
    spec = load_bracket_spec(2766)
    change(spec)
    with pytest.raises(ValueError, match=error):
        validate_bracket_spec(spec)


def test_champions_pins_only_officially_verified_quarterfinal_pairings():
    spec = load_bracket_spec(2766)
    pairings = spec["verified_opening_pairings"]
    assert [row["match_id"] for row in pairings] == [754730, 754731, 754732, 754733]
    assert [row["teams"] for row in pairings] == [
        ["100 Thieves", "G2 Esports"],
        ["Team Vitality", "Nongshim RedForce"],
        ["NRG", "T1"],
        ["Paper Rex", "LOUD"],
    ]
    assert spec["playoff_seeding"] == "unresolved"
    assert validate_bracket_spec(spec) is None


def test_champions_playoff_routes_are_source_checked():
    assert playoff_feeds(load_bracket_spec(2766)) == {
        754734: ((754730, "winner"), (754731, "winner")),
        754735: ((754732, "winner"), (754733, "winner")),
        754738: ((754730, "loser"), (754731, "loser")),
        754739: ((754732, "loser"), (754733, "loser")),
        754740: ((754738, "winner"), (754735, "loser")),
        754741: ((754739, "winner"), (754734, "loser")),
        754742: ((754740, "winner"), (754741, "winner")),
        754736: ((754734, "winner"), (754735, "winner")),
        754743: ((754736, "loser"), (754742, "winner")),
        754737: ((754736, "winner"), (754743, "winner")),
    }


@pytest.mark.parametrize("mutate", [
    lambda s: s["playoff_advancement"]["slots"]["754735"]["a"].update(**{"from": 754730, "take": "winner"}),
    lambda s: s["playoff_advancement"]["slots"]["754734"]["a"].update(**{"from": 999999}),
    lambda s: s["playoff_advancement"]["slots"]["754738"]["a"].update(**{"from": 754740}),
    lambda s: s["playoff_advancement"]["slots"]["754734"]["a"].update(take="draw"),
    lambda s: s["playoff_advancement"]["slots"].pop("754734"),
    lambda s: s["playoff_advancement"]["slots"].update({"999999": {"a": {"from": 754730, "take": "winner"}, "b": {"from": 754731, "take": "winner"}, "basis": "observed"}}),
    lambda s: s["playoff_advancement"]["slots"]["754740"]["a"].update(**{"from": 754739, "take": "loser"}),
    lambda s: s["playoff_advancement"].update(sources=["http://example.org"]),
])
def test_champions_rejects_invalid_playoff_routing(mutate):
    spec = load_bracket_spec(2766)
    mutate(spec)
    with pytest.raises(ValueError, match="routing"):
        validate_bracket_spec(spec)


@pytest.mark.parametrize("mutate, error", [
    (lambda s: s["verified_opening_pairings"][0].update(match_id=754731), "quarterfinal slot"),
    (lambda s: s["verified_opening_pairings"][0]["team_ids"].__setitem__(0, 2059), "inconsistent team identity"),
    (lambda s: s["verified_opening_pairings"][0]["teams"].__setitem__(1, "LOUD"), "inconsistent team identity"),
    (lambda s: s["verified_opening_pairings"][1]["team_ids"].__setitem__(0, 120), "inconsistent team identity"),
    (lambda s: s.update(playoff_draw_sources=["http://not-https.example", "https://example.org"]), "provenance"),
    (lambda s: s["verified_opening_pairings"].pop(), "provenance"),
])
def test_champions_rejects_unverified_quarterfinal_pairings(mutate, error):
    spec = load_bracket_spec(2766)
    mutate(spec)
    with pytest.raises(ValueError, match=error):
        validate_bracket_spec(spec)
