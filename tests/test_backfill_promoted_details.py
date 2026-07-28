from scripts.backfill_promoted_details import player_rows


def test_player_rows_accepts_self_hosted_segments_wrapper():
    payload = {
        "data": {
            "segments": [{
                "maps": [{"players": {"team1": [{}, {}], "team2": [{}]}}],
            }]
        }
    }

    assert player_rows(payload) == 3
