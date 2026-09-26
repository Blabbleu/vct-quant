"""Fail-closed group routing using pinned IDs, without title odds."""
import json
from pathlib import Path

import pytest

from vct_quant.event_bracket import detail_result, group_progress, load_bracket_spec


SPEC = load_bracket_spec(2766)
ARCHIVE = Path("data/raw/vlrgg")


def test_champions_archived_detail_scores_feed_pinned_group_openers():
    files = [list(ARCHIVE.glob(f"match_details_{match_id}_*.json"))
             for match_id in (753454, 753460)]
    if any(not matches for matches in files):
        pytest.skip("read-only raw details not present in clean checkout")
    observed = {match_id: detail_result(json.loads(matches[-1].read_text()), match_id)
                for match_id, matches in zip((753454, 753460), files)}
    assert observed == {
        753454: result([731, 11058], [0, 2]),
        753460: result([11060, 1034], [0, 2]),
    }
    assert group_progress(SPEC, "C", {753454: observed[753454]})["qualifiers"] == []
    assert group_progress(SPEC, "D", {753460: observed[753460]})["qualifiers"] == []


def test_champions_detail_adapter_rejects_nonfinal_or_inconsistent_winner():
    payload = {"status": "success", "data": {"status": 200, "segments": [{
        "match_id": "753454", "status": "final", "maps": [],
        "teams": [{"id": "731", "score": "0", "is_winner": False},
                  {"id": "11058", "score": "2", "is_winner": True}],
    }]}}
    assert detail_result(payload, 753454) == result([731, 11058], [0, 2])
    payload["data"]["segments"][0]["status"] = "live"
    with pytest.raises(ValueError):
        detail_result(payload, 753454)
    payload["data"]["segments"][0]["status"] = "final"
    payload["data"]["segments"][0]["teams"][0]["is_winner"] = True
    with pytest.raises(ValueError):
        detail_result(payload, 753454)
    payload["data"]["segments"][0]["teams"][0]["is_winner"] = False
    with pytest.raises(ValueError):
        detail_result(payload, 753455)

@pytest.mark.parametrize("scores", ([1, 0], [3, 0], [2, 2], [2, 3]))
def test_champions_group_final_requires_two_map_wins(scores):
    payload = {"status": "success", "data": {"status": 200, "segments": [{
        "match_id": "753454", "status": "final", "maps": [],
        "teams": [{"id": "731", "score": str(scores[0]), "is_winner": scores[0] > scores[1]},
                  {"id": "11058", "score": str(scores[1]), "is_winner": scores[1] > scores[0]}],
    }]}}
    with pytest.raises(ValueError, match="best-of-three"):
        detail_result(payload, 753454)
    with pytest.raises(ValueError, match="best-of-three"):
        group_progress(SPEC, "C", {753454: result([731, 11058], scores)})


def test_champions_group_accepts_three_map_final():
    assert group_progress(SPEC, "C", {753454: result([731, 11058], [2, 1])})["qualifiers"] == []


def result(teams, scores):
    return {"team_ids": list(teams), "scores": list(scores)}


def test_champions_group_routes_played_openers_to_next_two_slots():
    group = SPEC["groups"]["C"]
    observed = {
        group["opening_1"]["match_id"]: result([731, 11058], [0, 2]),
        group["opening_2"]["match_id"]: result([474, 624], [1, 2]),
    }
    progress = group_progress(SPEC, "C", observed)
    assert progress["expected"] == {"winners": [11058, 624], "elimination": [731, 474]}
    assert progress["qualifiers"] == []


def test_champions_group_completed_graph_has_two_distinct_qualifiers():
    group = SPEC["groups"]["C"]
    observed = {
        group["opening_1"]["match_id"]: result([731, 11058], [0, 2]),
        group["opening_2"]["match_id"]: result([474, 624], [1, 2]),
        group["winners"]["match_id"]: result([11058, 624], [2, 1]),
        group["elimination"]["match_id"]: result([731, 474], [2, 1]),
        group["decider"]["match_id"]: result([624, 731], [2, 0]),
    }
    progress = group_progress(SPEC, "C", observed)
    assert progress["expected"]["decider"] == [624, 731]
    assert progress["qualifiers"] == [11058, 624]


@pytest.mark.parametrize("key,played", [
    ("opening_1", result([731, 11058], [1, 1])),
    ("opening_1", result([731, 11058], [None, 2])),
    ("opening_1", result([731, 99999], [0, 2])),
    ("opening_1", result([11058, 731], [0, 2])),
    ("winners", result([11058, 624], [2, 0])),
])
def test_champions_group_rejects_ambiguous_or_unverified_results(key, played):
    group = SPEC["groups"]["C"]
    with pytest.raises(ValueError):
        group_progress(SPEC, "C", {group[key]["match_id"]: played})
