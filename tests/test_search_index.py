from vct_quant.search_index import build_search_index


def test_search_index_shapes_exact_ids_and_omits_nonofficial_teams():
    result = build_search_index(
        teams=[
            {"team_id": 12, "name": "Team Alpha", "tag": "ALP", "tier": 1},
            {"team_id": 13, "name": "Alpha Academy", "tag": "AA", "tier": 2},
            {"team_id": None, "name": "Name Only", "tag": None, "tier": 1},
            {"team_id": 14, "name": "Community", "tag": "COM", "tier": 3},
        ],
        players=[
            {"player_id": 44, "handle": "Ace", "real_name": "A. Player", "team_id": 12,
             "team_name": "Team Alpha", "photo": "/players/44.png"},
            {"player_id": None, "handle": "Unresolved", "real_name": None, "team_id": None,
             "team_name": None, "photo": None},
        ],
        events=[
            {"event_id": 88, "name": "VCT Masters", "tier": 1},
            {"event_id": 89, "name": "Community Cup", "tier": 3},
        ],
        logos={"12": "/logos/12.png", "13": "https://example.invalid/logo.png"},
    )
    assert result == {
        "teams": [
            {"id": 12, "name": "Team Alpha", "tag": "ALP", "tier": 1,
             "logo": "/logos/12.png"},
            {"id": 13, "name": "Alpha Academy", "tag": "AA", "tier": 2,
             "logo": None},
        ],
        "players": [
            {"id": 44, "handle": "Ace", "real_name": "A. Player", "team_id": 12,
             "team_name": "Team Alpha", "photo": "/players/44.png"}
        ],
        "events": [{"id": 88, "name": "VCT Masters", "tier": 1}],
    }
