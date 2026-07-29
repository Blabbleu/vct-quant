import json
import sys

import pandas as pd

from vct_quant import cli
from vct_quant import config
from vct_quant.etl import normalize
from vct_quant.features import build


def test_load_vlrgg_dispatches_to_loader(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["vct", "load-vlrgg"])
    monkeypatch.setattr(normalize, "load_vlrgg_match_results", lambda: "loaded")

    cli.main()

    assert capsys.readouterr().out.strip() == "loaded"


def test_load_vlrgg_details_dispatches_to_loader(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["vct", "load-vlrgg-details"])
    monkeypatch.setattr(normalize, "load_vlrgg_match_details", lambda: "loaded details")

    cli.main()

    assert capsys.readouterr().out.strip() == "loaded details"


def test_update_refreshes_results_before_predictions(monkeypatch, tmp_path, capsys):
    from vct_quant.ingest import vlrgg

    calls = []
    monkeypatch.setattr(sys, "argv", ["vct", "update"])
    monkeypatch.setattr(
        vlrgg, "fetch_match_results",
        lambda: calls.append("fetch results") or {"data": {"segments": [1, 2]}},
    )
    monkeypatch.setattr(
        normalize, "load_vlrgg_match_results",
        lambda: calls.append("load results") or "loaded",
    )
    monkeypatch.setattr(
        vlrgg, "fetch_upcoming_matches",
        lambda: calls.append("fetch upcoming") or {"data": {"segments": [1]}},
    )
    monkeypatch.setattr(
        cli, "_materialize_upcoming",
        lambda data: (
            calls.append("predict upcoming") or pd.DataFrame([{"match_id": 1}]),
            tmp_path / "upcoming_tier1.parquet",
        ),
    )

    cli.main()

    assert calls == [
        "fetch results", "load results", "fetch upcoming", "predict upcoming",
    ]
    assert "retained 1 Tier-1" in capsys.readouterr().out


def test_prediction_prints_cached_match(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(config, "PROCESSED_DIR", tmp_path)
    monkeypatch.setattr(cli, "_refresh_prediction", lambda match_id: pd.DataFrame())
    monkeypatch.setattr(sys, "argv", ["vct", "prediction", "698904"])
    pd.DataFrame([{
        "match_id": 698904,
        "event_name": "VCT 2026: Pacific Stage 2",
        "event_series": "Group Stage: Week 3",
        "team_a_name": "Team Secret",
        "team_b_name": "Paper Rex",
        "p_team_a_win": 0.123,
        "p_team_b_win": 0.877,
        "scheduled_at": "2026-07-31 08:00:00+00:00",
        "ratings_through_match_id": 712823,
        "vlr_url": "https://www.vlr.gg/698904/example",
    }]).to_parquet(tmp_path / "upcoming_tier1.parquet", index=False)

    cli.main()

    output = capsys.readouterr().out
    assert "Team Secret: 12.3%" in output
    assert "Paper Rex: 87.7%" in output
    assert "Exact score (Bo3):" in output
    assert "Expected maps:" in output


def test_prediction_falls_back_to_direct_match_details(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(config, "PROCESSED_DIR", tmp_path)
    monkeypatch.setattr(sys, "argv", ["vct", "prediction", "706376"])
    from vct_quant.ingest import vlrgg

    monkeypatch.setattr(vlrgg, "fetch_match_details", lambda match_id: {"id": match_id})
    monkeypatch.setattr(cli, "_predict_match_details", lambda data: pd.DataFrame([{
        "match_id": 706376,
        "event_name": "VCT 2026: Americas Stage 2",
        "event_series": "Group Stage: Week 4",
        "best_of": 3,
        "team_a_name": "KRÜ Esports",
        "team_b_name": "Sentinels",
        "p_team_a_win": 0.4,
        "p_team_b_win": 0.6,
        "scheduled_at": "Saturday, August 8 5:00 PM EDT",
        "ratings_through_match_id": 712823,
        "vlr_url": "https://www.vlr.gg/706376",
    }]))

    cli.main()

    assert "KRÜ Esports: 40.0%" in capsys.readouterr().out


def test_prediction_automatically_uses_announced_maps(monkeypatch, tmp_path, capsys):
    applied = []
    monkeypatch.setattr(config, "PROCESSED_DIR", tmp_path)
    monkeypatch.setattr(sys, "argv", ["vct", "predict", "1", "--json"])
    monkeypatch.setattr(cli, "_refresh_prediction", lambda match_id: pd.DataFrame([{
        "match_id": 1,
        "event_name": "VCT 2026: Americas Stage 2",
        "event_series": "Group Stage",
        "best_of": 3,
        "map_picks": ["Lotus", "Haven", "Ascent"],
        "team_a_name": "Alpha",
        "team_b_name": "Bravo",
        "p_team_a_win": 0.5,
        "p_team_b_win": 0.5,
        "scheduled_at": "soon",
        "ratings_through_match_id": 1,
        "vlr_url": "https://www.vlr.gg/1",
    }]))

    def apply_maps(fixtures, maps):
        applied.extend(maps)
        out = fixtures.copy()
        out["map_predictions"] = [[]]
        return out

    monkeypatch.setattr(build, "add_map_predictions", apply_maps)

    cli.main()

    assert applied == ["Lotus", "Haven", "Ascent"]
    assert json.loads(capsys.readouterr().out)["match_id"] == 1


def test_predictions_emits_json(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(config, "PROCESSED_DIR", tmp_path)
    monkeypatch.setattr(sys, "argv", ["vct", "predictions", "--json"])
    pd.DataFrame([{
        "match_id": 698904,
        "scheduled_at": "2026-07-31 08:00:00+00:00",
        "event_name": "VCT 2026: Pacific Stage 2",
        "team_a_name": "Team Secret",
        "team_b_name": "Paper Rex",
        "p_team_a_win": 0.123,
        "p_team_b_win": 0.877,
    }]).to_parquet(tmp_path / "upcoming_tier1.parquet", index=False)

    cli.main()

    assert json.loads(capsys.readouterr().out)[0]["match_id"] == 698904


def test_ranking_respects_top_and_emits_json(monkeypatch, capsys):
    monkeypatch.setattr(build, "current_rankings", lambda: pd.DataFrame([
        {"rank": 1, "season": 2026, "team_name": "Alpha", "elo": 1600.0,
         "season_matches": 3, "last_match_id": 2},
        {"rank": 2, "season": 2026, "team_name": "Bravo", "elo": 1500.0,
         "season_matches": 3, "last_match_id": 2},
    ]))
    monkeypatch.setattr(sys, "argv", ["vct", "ranking", "--top", "1", "--json"])

    cli.main()

    assert [row["team_name"] for row in json.loads(capsys.readouterr().out)] == ["Alpha"]
