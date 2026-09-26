"""Static Champions 2026 bracket is a source-checked *schedule*, not simulated odds."""
import json
from pathlib import Path

import pytest
from vct_quant.event_bracket import load_bracket_spec, validate_bracket_spec

ARCHIVE = Path("data/raw/vlrgg/event_matches_2766_20260926T021503Z.json")


def test_champions_bracket_has_complete_distinct_slots():
    spec = load_bracket_spec(2766)
    assert spec["event_id"] == 2766
    assert spec["playoff_seeding"] == "unresolved"
    assert spec["playoff_advancement"] == "unresolved"
    assert len(spec["groups"]) == 4
    assert len(spec["playoffs"]) == 14
    assert len({slot["match_id"] for group in spec["groups"].values() for slot in group.values()} | {slot["match_id"] for slot in spec["playoffs"]}) == 34
    assert validate_bracket_spec(spec) is None


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
