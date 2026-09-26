"""Series length for fixtures whose feed omits the format.

The vlrggapi upcoming feed carries no best-of, so it is inferred from the
stage label. Source-checked rule (docs/series-format.md): VCT and Game
Changers main-event lower, middle and grand finals are Bo5; everything else is
Bo3. `scripts/audit_series_format.py` re-measures it against played scores.
"""
import pandas as pd
import pytest

from vct_quant.etl.events import series_best_of
from vct_quant.etl.normalize import official_match_details, official_upcoming
from vct_quant.features.build import add_score_predictions


@pytest.mark.parametrize("event, series, expected", [
    ("Valorant Champions 2026", "Playoffs: Lower Final", 5),
    ("Valorant Champions 2026", "Playoffs: Grand Final", 5),
    ("Valorant Champions 2026", "Playoffs: Upper Final", 3),
    ("Valorant Champions 2026", "Playoffs: Upper Quarterfinals", 3),
    ("Valorant Champions 2026", "Group Stage: Decider (A)", 3),
    ("Valorant Champions 2026", "Group Stage: Winner's (A)", 3),
    ("VCT 2026: EMEA Kickoff", "Main Event: Middle Final", 5),
    ("VCT 2026: Pacific Stage 2", "Playoffs: Lower Round 3", 3),
    ("VCT 2026: Pacific Stage 2", "Lower Final", 5),
    ("VCT 2026: Pacific Stage 2", "LOWER FINAL", 5),
    # Game Changers main events play Bo5 lower finals; small cups do not.
    ("Game Changers 2026: China", "Main Event: Lower Final", 5),
    ("Game Changers 2026: Pacific", "Main Event: Grand Final", 5),
    ("Game Changers 2026: EMEA Cash Cup August", "Lower Final", 3),
    ("Game Changers 2026: Japan Split 2", "Lower Final (A)", 3),
    # Unchanged legacy behaviour: any grand final defaults to Bo5.
    ("Game Changers 2026: EMEA Cash Cup August", "Grand Final", 5),
    # Qualifier brackets inside an event are not the event's final.
    ("Game Changers 2024 LATAM North: Closing", "Lower Final Quals", 3),
    ("Valorant Champions 2026", "", 3),
    ("Valorant Champions 2026", None, 3),
])
def test_series_best_of(event, series, expected):
    assert series_best_of(event, series) == expected


def _payload(series, event="Valorant Champions 2026"):
    return {"data": {"segments": [{
        "team1": "Alpha", "team2": "Bravo", "match_event": event,
        "match_series": series, "unix_timestamp": "2026-10-04 09:00:00",
        "match_page": "754736/alpha-vs-bravo", "time_until_match": "8d",
    }]}}


def _con():
    import duckdb
    con = duckdb.connect()
    con.execute("CREATE TABLE team (team_id BIGINT, name TEXT)")
    con.execute("CREATE TABLE match_team (team_id BIGINT, team_name TEXT)")
    con.execute("CREATE TABLE event (event_id BIGINT, name TEXT, tier SMALLINT)")
    return con


def test_upcoming_lower_final_is_bo5_with_five_map_scores():
    out = official_upcoming(_payload("Playoffs: Lower Final"), _con())
    assert out.best_of.tolist() == [5]

    out["p_team_a_win"] = 0.6
    scored = add_score_predictions(out).iloc[0]
    assert set(scored.score_probabilities) == {"3-0", "3-1", "3-2", "0-3", "1-3", "2-3"}
    assert scored.p_team_a_win == pytest.approx(
        sum(v for k, v in scored.score_probabilities.items() if k.startswith("3-"))
    )
    assert 3 < scored.expected_maps < 5


def test_upcoming_upper_final_stays_bo3():
    assert official_upcoming(_payload("Playoffs: Upper Final"), _con()).best_of.tolist() == [3]


def test_score_fallback_uses_event_and_series_for_old_cache():
    """Cached fixtures written before `best_of` existed are upgraded by the same rule."""
    old = pd.DataFrame({
        "event_name": ["Valorant Champions 2026", "Valorant Champions 2026"],
        "event_series": ["Playoffs: Lower Final", "Playoffs: Upper Final"],
        "p_team_a_win": [0.5, 0.5],
    })
    assert add_score_predictions(old).best_of.tolist() == [5, 3]


def test_match_details_fallback_uses_series_rule_when_map_count_is_odd():
    payload = {"data": {"segments": [{
        "match_id": "754736",
        "event": {"name": "Valorant Champions 2026 Playoffs: Lower Final",
                  "series": "Playoffs: Lower Final"},
        "teams": [{"id": "1", "name": "Alpha", "score": ""},
                  {"id": "2", "name": "Bravo", "score": ""}],
        "maps": [],
    }]}}
    assert official_match_details(payload).best_of.iloc[0] == 5


def test_rule_agrees_with_riot_champions_2026_formats():
    """Riot-sourced formats pinned in the bracket spec (docs/champions-2026-bracket.md)."""
    from vct_quant.event_bracket import load_bracket_spec

    spec = load_bracket_spec(2766)
    for stage, best_of in spec["series_best_of"]["playoffs"].items():
        assert series_best_of("Valorant Champions 2026", f"Playoffs: {stage}") == best_of, stage
    for stage in ("Opening (A)", "Winner's (B)", "Elimination (C)", "Decider (D)"):
        assert series_best_of("Valorant Champions 2026", f"Group Stage: {stage}") == 3


def test_audit_counts_winner_map_agreement():
    from scripts.audit_series_format import label_outcomes

    rows = pd.DataFrame({
        "event_name": ["VCT 2026: EMEA Stage 2"] * 4,
        "series": ["Lower Final", "Lower Final", "Upper Final", "Upper Final"],
        "tier": [1, 1, 1, 1],
        "score_a": [3, 2, 2, 13],   # 13-x is a Bo1 round score: skipped
        "score_b": [1, 0, 1, 7],
    })
    out = label_outcomes(rows).set_index("rule")
    assert out.loc[5, ["n", "agree"]].tolist() == [2, 1]
    assert out.loc[3, ["n", "agree"]].tolist() == [1, 1]
