"""Finished-match result detail is shown only when canonical rows verify it."""
import pandas as pd
import pytest

from vct_quant.match_result import result_detail

URL = "https://www.vlr.gg/1/a-vs-b"


def teams(a=(10, "Alpha", 2, True), b=(20, "Bravo", 1, False)):
    return pd.DataFrame([(1, *a), (2, *b)], columns=[
        "team_number", "team_id", "team_name", "series_score", "is_winner"])


def meta(**kw):
    base = {"match_id": 1, "status": "completed", "completed_at": "2026-09-24T00:00Z",
            "scheduled_at": None, "best_of": 3, "vlr_url": URL,
            "last_seen_at": "2026-09-24T17:00Z"}
    return {**base, **kw}


def maps(rows):
    return pd.DataFrame(rows, columns=["map_number", "map_name", "rounds_1", "rounds_2"])


GOOD_MAPS = maps([(1, "Lotus", 13, 6), (2, "split", 10, 13), (3, "Bind", 13, 11)])


def test_verified_result_is_oriented_to_the_forecast_sides():
    # Forecast lists Bravo first: the result must be flipped to that orientation.
    r = result_detail(meta(), teams(), GOOD_MAPS, "20", "10", p_team_a=0.4)
    assert r["status"] == "verified" and r["reason"] is None
    assert (r["maps_a"], r["maps_b"], r["winner"]) == (1, 2, "b")
    assert r["maps_complete"] is True
    assert r["maps"] == [
        {"number": 1, "map": "Lotus", "rounds_a": 6, "rounds_b": 13},
        {"number": 2, "map": "Split", "rounds_a": 13, "rounds_b": 10},
        {"number": 3, "map": "Bind", "rounds_a": 11, "rounds_b": 13}]
    assert r["completed_on"] == "2026-09-24" and r["source_url"] == URL
    assert r["as_of"].startswith("2026-09-24T17:00")
    assert r["pre_start_winner_p"] == pytest.approx(0.6)


def test_name_key_matches_normalized_canonical_name():
    r = result_detail(meta(), teams(b=(None, " Bravo ", 1, False)), GOOD_MAPS, "10", "name:bravo")
    assert r["status"] == "verified" and r["winner"] == "a"
    assert r["pre_start_winner_p"] is None


def test_forecast_name_key_matches_side_resolved_to_an_id_later():
    r = result_detail(meta(), teams(), GOOD_MAPS, "name:bravo", "10", p_team_a=0.3)
    assert r["status"] == "verified" and r["winner"] == "b" and (r["maps_a"], r["maps_b"]) == (1, 2)
    assert r["maps"][0] == {"number": 1, "map": "Lotus", "rounds_a": 6, "rounds_b": 13}


def test_both_forecast_sides_cannot_claim_the_same_canonical_side():
    # "name:alpha" and "10" are both keys of side 1; Bravo is unmatched.
    r = result_detail(meta(), teams(), GOOD_MAPS, "name:alpha", "10")
    assert r["status"] == "unverified" and "teams" in r["reason"]


def test_series_result_stands_without_map_rows():
    r = result_detail(meta(), teams(), maps([]), "10", "20")
    assert r["status"] == "verified" and r["maps_complete"] is False and r["maps"] == []


@pytest.mark.parametrize("bad", [
    maps([(1, "Lotus", 13, 6), (2, "Split", 13, 10)]),          # maps 2-0 vs series 2-1
    maps([(1, "Lotus", 13, 6), (2, "Split", 10, 13), (3, "TBD", 13, 11)]),
    maps([(1, "Lotus", 13, 6), (2, "Split", 10, 13), (3, "Bind", 13, 13)]),
    maps([(1, "Lotus", 13, 6), (2, "Split", 10, 13), (3, "Bind", None, 11)]),
    maps([(1, "Lotus", 13, 6), (1, "Split", 10, 13), (3, "Bind", 13, 11)]),
])
def test_inconsistent_maps_are_withheld_but_series_stays(bad):
    r = result_detail(meta(), teams(), bad, "10", "20")
    assert r["status"] == "verified" and r["maps_complete"] is False and r["maps"] == []


def test_not_completed_is_none():
    assert result_detail(meta(status="upcoming"), teams(), GOOD_MAPS, "10", "20") is None
    assert result_detail(None, teams(), GOOD_MAPS, "10", "20") is None


@pytest.mark.parametrize("m,t,reason", [
    (meta(), teams(b=(30, "Charlie", 1, False)), "teams"),
    (meta(), teams(a=(10, "Alpha", 2, False)), "score"),
    (meta(), teams(a=(10, "Alpha", 1, False), b=(20, "Bravo", 0, True)), "score"),
    (meta(), teams(a=(10, "Alpha", None, True)), "score"),
    (meta(best_of=5), teams(), "score"),
    (meta(), teams(a=(10, "Alpha", 1, None), b=(20, "Bravo", 1, None)), "score"),
    (meta(), teams(a=(10, "Alpha", 3, True)), "score"),
    (meta(completed_at=None), teams(), "date"),
    (meta(completed_at="2026-09-20T00:00Z", scheduled_at="2026-09-24T09:00Z"), teams(), "date"),
    (meta(), teams(b=(10, "Alpha", 1, False)), "teams"),
])
def test_unverifiable_rows_are_flagged_not_shown(m, t, reason):
    r = result_detail(m, t, GOOD_MAPS, "10", "20", p_team_a=0.7)
    assert r["status"] == "unverified" and reason in r["reason"]
    assert r["maps"] == [] and r["winner"] is None and r["pre_start_winner_p"] is None
    assert r["source_url"] == URL


def test_unknown_best_of_accepts_only_decisive_series_scores():
    ok = result_detail(meta(best_of=None), teams(), GOOD_MAPS, "10", "20")
    assert ok["status"] == "verified"
    bo1 = result_detail(meta(best_of=1), teams(a=(10, "Alpha", 1, True), b=(20, "Bravo", 0, False)),
                        maps([(1, "Ascent", 13, 3)]), "10", "20")
    assert bo1["status"] == "verified" and bo1["maps_complete"] is True


def _history_teams(rows):
    import pandas as pd
    return pd.DataFrame(rows, columns=["team_number", "team_id", "team_name"])


def test_history_keys_upgrade_name_key_to_same_side_id():
    from vct_quant.match_result import history_keys
    teams = _history_teams([(1, 731, "TYLOO"), (2, 11058, "G2 Esports")])
    assert history_keys(teams, "731", "name:g2 esports") == ("731", "11058")
    # forecast oriented the other way round
    assert history_keys(teams, "name:g2 esports", "731") == ("11058", "731")


def test_history_keys_keep_logged_keys_when_ambiguous_or_mismatched():
    from vct_quant.match_result import history_keys
    teams = _history_teams([(1, 731, "TYLOO"), (2, 11058, "G2 Esports")])
    assert history_keys(teams, "731", "name:nrg") == ("731", "name:nrg")
    assert history_keys(teams, "name:tyloo", "name:tyloo") == ("name:tyloo", "name:tyloo")
    assert history_keys(_history_teams([(1, 731, "TYLOO")]), "731", "name:g2 esports") == (
        "731", "name:g2 esports")
    assert history_keys(None, "1", "2") == ("1", "2")
    same = _history_teams([(1, 5, "X"), (2, 5, "X")])
    assert history_keys(same, "5", "name:x") == ("5", "name:x")
