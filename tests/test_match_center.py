"""The Match Center movement series uses only comparable pre-start observations."""
import pandas as pd

from vct_quant.match_center import movement, recent_form, map_pool_from_rows


def test_map_pool_point_in_time_and_identity():
    rows = pd.DataFrame([
        (1, 1, "2026-09-20", "1", "2", "A", "B", "Ascent", 13, 8),
        (2, 1, "2026-09-21", "3", "1", "C", "A", "ascent", 7, 13),
        (3, 1, "2026-09-22", "1", "4", "A", "D", "Bind", 8, 13),
        (4, 3, "2026-09-22", "1", "5", "A", "E", "Bind", 13, 0),
        (5, 1, "2026-09-25", "1", "6", "A", "F", "Ascent", 13, 0),
        (6, 1, "2026-09-23", "1", "7", "A", "G", "Ascent", 13, 0),
        (7, 1, "2026-09-23", "1", "8", "A", "TBD", "Ascent", 13, 0),
        (8, 1, None, "1", "9", "A", "H", "Ascent", 13, 0),
        (9, 1, "2026-09-23", "1", "10", "A", "I", "Ascent", None, 0),
        (10, 1, "2026-09-23", "1", "11", "A", "J", "Ascent", 13, 13),
    ], columns=["match_id", "tier", "completed_at", "team_a", "team_b", "team_a_name", "team_b_name", "map_name", "rounds_a", "rounds_b"])
    pool = map_pool_from_rows(rows, "1", "2", 5, "2026-09-25T20:00Z", limit=3)
    assert pool == {"a": [{"map": "Ascent", "played": 2, "won": 2, "round_share": 26 / 41},
                          {"map": "Bind", "played": 1, "won": 0, "round_share": 8 / 21}],
                    "b": [{"map": "Ascent", "played": 1, "won": 0, "round_share": 8 / 21}]}


def test_map_pool_window_is_last_maps_not_last_series():
    rows = pd.DataFrame([
        (1, 1, "2026-09-20", "1", "2", "A", "B", "Bind", 13, 1),
        (2, 1, "2026-09-21", "1", "3", "A", "C", "Ascent", 0, 13),
        (3, 1, "2026-09-22", "1", "4", "A", "D", "Ascent", 13, 1),
    ], columns=["match_id", "tier", "completed_at", "team_a", "team_b", "team_a_name", "team_b_name", "map_name", "rounds_a", "rounds_b"])
    assert map_pool_from_rows(rows, "1", "5", 4, "2026-09-25T00:00Z", limit=2)["a"] == [
        {"map": "Ascent", "played": 2, "won": 1, "round_share": 13 / 27}]



def test_recent_form_is_point_in_time_and_separates_rating_pools():
    rows = pd.DataFrame([
        (3, 1, "1", "9", "A", "X", 1., 2, 0, "2026-09-20T10:00Z"),
        (4, 2, "1", "8", "A", "Y", 0., 0, 2, "2026-09-21T10:00Z"),
        (5, 1, "7", "1", "Z", "A", 1., 2, 1, "2026-09-22T10:00Z"),
        (6, 1, "1", "6", "A", "TBD", 1., 2, 0, "2026-09-23T10:00Z"),
        (7, 1, "1", "5", "A", "F", 1., None, None, "2026-09-23T11:00Z"),
        (8, 1, "1", "4", "A", "D", 0., 1, 2, "2026-09-26T10:00Z"),
        (9, 1, "1", "3", "A", "B", 1., 2, 0, "2026-09-24T10:00Z"),
        (10, 1, "1", "2", "A", "B", 1., 2, 0, "2026-09-23T10:00Z"),
        (11, 1, "1", "2", "A", "B", 1., 2, 0, None),
        (1, 1, "1", "2", "A", "B", 1., 2, 0, "2026-09-25T00:00Z"),
    ], columns=["match_id", "tier", "team_a", "team_b", "team_a_name",
                "team_b_name", "score_a", "maps_a", "maps_b", "completed_at"])
    result = recent_form(rows, "1", "2", 10, "2026-09-25T20:00Z")
    assert [(x["match_id"], x["result"], x["opponent"]) for x in result["a"]] == [
        (9, "W", "B"), (5, "L", "Z"), (3, "W", "X")]
    assert result["b"] == []


def test_recent_form_sorts_by_completion_date_not_match_id():
    rows = pd.DataFrame([
        (2, 1, "1", "3", "A", "Old", 1., 2, 0, "2026-09-22T00:00Z"),
        (3, 1, "1", "4", "A", "New ID", 1., 2, 0, "2026-09-21T00:00Z"),
    ], columns=["match_id", "tier", "team_a", "team_b", "team_a_name",
                "team_b_name", "score_a", "maps_a", "maps_b", "completed_at"])
    assert [x["match_id"] for x in recent_form(rows, "1", "5", 4, "2026-09-23T00:00Z")["a"]] == [2, 3]


def test_recent_form_excludes_gc_and_future_id_even_when_date_is_past():
    rows = pd.DataFrame([
        (1, 3, "1", "2", "A", "B", 1., 2, 0, "2026-09-20T10:00Z"),
        (21, 1, "1", "2", "A", "B", 1., 2, 0, "2026-09-20T10:00Z"),
    ], columns=["match_id", "tier", "team_a", "team_b", "team_a_name",
                "team_b_name", "score_a", "maps_a", "maps_b", "completed_at"])
    assert recent_form(rows, "1", "2", 10, "2026-09-25T00:00Z") == {"a": [], "b": []}



def test_movement_keeps_prestart_snapshots_of_the_latest_pairing():
    log = pd.DataFrame([
        {"match_id": 42, "predicted_at": "2026-09-25T08:00Z", "scheduled_at": "2026-09-25T12:00Z",
         "team_a_name": "A", "team_b_name": "B", "team_a_key": "id:1", "team_b_key": "id:2",
         "p_team_a_win": .55, "p_market_a": .51, "market_spread": .04, "market_slug": "m1"},
        {"match_id": 42, "predicted_at": "2026-09-25T09:00Z", "scheduled_at": "2026-09-25T12:00Z",
         "team_a_name": "B", "team_b_name": "A", "team_a_key": "id:2", "team_b_key": "id:1",
         "p_team_a_win": .46, "p_market_a": .49, "market_spread": .04, "market_slug": "m1"},
        {"match_id": 42, "predicted_at": "2026-09-25T10:00Z", "scheduled_at": "2026-09-25T12:00Z",
         "team_a_name": "A", "team_b_name": "B", "team_a_key": "id:1", "team_b_key": "id:2",
         "p_team_a_win": .58, "p_market_a": .53, "market_spread": .06, "market_slug": "m1"},
        {"match_id": 42, "predicted_at": "2026-09-25T12:01Z", "scheduled_at": "2026-09-25T12:00Z",
         "team_a_name": "A", "team_b_name": "B", "team_a_key": "id:1", "team_b_key": "id:2",
         "p_team_a_win": .99, "p_market_a": .99, "market_spread": .02, "market_slug": "m1"},
    ])
    result = movement(log, 42)
    assert result["match_id"] == 42
    assert result["team_a"] == "A"
    assert result["team_b"] == "B"
    assert [x["elo"] for x in result["points"]] == [.55, .58]
    assert [x["market"] for x in result["points"]] == [.51, .53]
    assert [x["observed_at"] for x in result["points"]] == ["2026-09-25T08:00:00+00:00", "2026-09-25T10:00:00+00:00"]


def test_movement_unknown_match_is_none():
    assert movement(pd.DataFrame(), 99) is None


def test_movement_does_not_join_different_market_contracts():
    log = pd.DataFrame([
        {"match_id": 8, "predicted_at": "2026-09-25T08:00Z", "scheduled_at": "2026-09-25T12:00Z",
         "team_a_name": "A", "team_b_name": "B", "team_a_key": "a", "team_b_key": "b",
         "p_team_a_win": .55, "p_market_a": .51, "market_spread": .02, "market_slug": "old"},
        {"match_id": 8, "predicted_at": "2026-09-25T09:00Z", "scheduled_at": "2026-09-25T12:00Z",
         "team_a_name": "A", "team_b_name": "B", "team_a_key": "a", "team_b_key": "b",
         "p_team_a_win": .58, "p_market_a": .54, "market_spread": .02, "market_slug": "new"},
    ])
    assert [p["elo"] for p in movement(log, 8)["points"]] == [.55, .58]
    assert [p["market"] for p in movement(log, 8)["points"]] == [None, .54]
    assert [p["spread"] for p in movement(log, 8)["points"]] == [None, .02]


H2H_COLUMNS = ["match_id", "tier", "team_a", "team_b", "team_a_name", "team_b_name",
               "score_a", "maps_a", "maps_b", "completed_at"]


def test_head_to_head_is_point_in_time_exact_identity_and_oriented():
    from vct_quant.match_center import head_to_head
    rows = pd.DataFrame([
        (1, 1, "1", "2", "A", "B", 1., 2, 1, "2026-01-10T00:00Z"),   # A beats B
        (2, 1, "2", "1", "B", "A", 1., 2, 0, "2026-02-10T00:00Z"),   # B beats A, reversed sides
        (3, 3, "1", "2", "A", "B", 1., 2, 0, "2026-03-10T00:00Z"),   # Game Changers pool
        (4, 1, "1", "9", "A", "C", 1., 2, 0, "2026-03-11T00:00Z"),   # other opponent
        (5, 1, "1", "2", "A", "B", .5, 1, 1, "2026-03-12T00:00Z"),   # Bo2 draw
        (6, 1, "1", "2", "A", "B", 1., None, None, "2026-03-13T00:00Z"),  # forfeit / no maps
        (7, 1, "1", "2", "A", "B", 1., 2, 0, None),                  # undated
        (8, 1, "1", "2", "A", "B", 0., 0, 2, "2026-09-25T00:00Z"),   # same UTC day as refresh
        (30, 1, "1", "2", "A", "B", 1., 2, 0, "2026-03-14T00:00Z"),  # later match ID
        (9, 1, "name:a", "2", "A", "B", 1., 2, 0, "2026-03-15T00:00Z"),  # name alias, not ID 1
        (10, 1, "1", "1", "A", "A", 1., 2, 0, "2026-03-16T00:00Z"),  # malformed self-match
    ], columns=H2H_COLUMNS)
    h2h = head_to_head(rows, "1", "2", 20, "2026-09-25T20:00Z")
    assert [(r["match_id"], r["winner"], r["maps_a"], r["maps_b"]) for r in h2h["series"]] == [
        (2, "b", 0, 2), (1, "a", 2, 1)]
    assert (h2h["wins_a"], h2h["wins_b"], h2h["played"]) == (1, 1, 2)
    assert h2h["series"][0]["completed_at"].startswith("2026-02-10")


def test_head_to_head_limit_keeps_newest_but_counts_all():
    from vct_quant.match_center import head_to_head
    rows = pd.DataFrame([
        (i, 1, "1", "2", "A", "B", 1., 2, 0, f"2026-0{i}-01T00:00Z") for i in range(1, 5)
    ], columns=H2H_COLUMNS)
    h2h = head_to_head(rows, "1", "2", 10, "2026-09-01T00:00Z", limit=2)
    assert [r["match_id"] for r in h2h["series"]] == [4, 3]
    assert (h2h["wins_a"], h2h["wins_b"], h2h["played"]) == (4, 0, 4)


def test_head_to_head_empty_and_identical_keys():
    from vct_quant.match_center import head_to_head
    empty = {"series": [], "wins_a": 0, "wins_b": 0, "played": 0}
    assert head_to_head(pd.DataFrame(), "1", "2", 5, "2026-09-01T00:00Z") == empty
    rows = pd.DataFrame([(1, 1, "1", "1", "A", "A", 1., 2, 0, "2026-01-01T00:00Z")], columns=H2H_COLUMNS)
    assert head_to_head(rows, "1", "1", 5, "2026-09-01T00:00Z") == empty


def test_movement_tolerates_missing_slug_in_nullable_string_column():
    # The live log stores market_slug as pandas "string": an unmatched early
    # refresh is <NA>, and `<NA> == "slug"` is NA, whose truth value raises.
    log = pd.DataFrame([
        {"match_id": 9, "predicted_at": "2026-09-25T08:00Z", "scheduled_at": "2026-09-29T12:00Z",
         "team_a_name": "A", "team_b_name": "B", "team_a_key": "1", "team_b_key": "2",
         "p_team_a_win": .55, "p_market_a": None, "market_spread": None, "market_slug": None},
        {"match_id": 9, "predicted_at": "2026-09-25T09:00Z", "scheduled_at": "2026-09-29T12:00Z",
         "team_a_name": "A", "team_b_name": "B", "team_a_key": "1", "team_b_key": "2",
         "p_team_a_win": .56, "p_market_a": .47, "market_spread": .02, "market_slug": "s"},
    ])
    log["market_slug"] = log.market_slug.astype("string")
    points = movement(log, 9)["points"]
    assert [p["market"] for p in points] == [None, .47]
