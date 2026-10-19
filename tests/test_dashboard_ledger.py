from vct_quant.dashboard import LEDGER


def test_experiment_ledger_rows():
    keys = {"name", "holdout", "score", "verdict"}
    assert all(set(row) == keys for row in LEDGER)
    assert all(
        isinstance(value, str) and value.strip()
        for row in LEDGER
        for value in row.values()
    )
    names = [row["name"] for row in LEDGER]
    assert len(names) == len(set(names))
    assert all(row["verdict"] in {"shipped", "rejected", "not proven", "shadow"}
               for row in LEDGER)
    assert len(LEDGER) >= 26
    assert LEDGER[0]["name"] == "Margin-aware Elo (map share, K=48)"
    assert LEDGER[14]["name"] == "Best-of-aware map Elo"
    assert LEDGER[15:] == [
        {"name": "Round-share series model", "holdout": "2025+26", "score": "t=-1.80/-1.04",
         "verdict": "rejected"},
        {"name": "Lineup player-skill model (ADF)", "holdout": "2025+26", "score": "t=-1.19/-2.68",
         "verdict": "rejected"},
        {"name": "Stacked ensemble (Elo + round-share + lineup)", "holdout": "2025+26", "score": "t=+1.66/+1.29",
         "verdict": "not proven"},
        {"name": "Batch Bradley-Terry refit", "holdout": "2025+26", "score": "t=-2.09/-1.28",
         "verdict": "rejected"},
        {"name": "Gradient-boosted Elo residual", "holdout": "2025+26", "score": "t=+0.00/+0.00",
         "verdict": "rejected"},
        {"name": "State-space map-level Bradley-Terry", "holdout": "2025+26", "score": "t=-2.39/-1.96",
         "verdict": "rejected"},
        {"name": "Stack plus batch BT input", "holdout": "2025+26", "score": "t=+1.63/+1.22",
         "verdict": "not proven"},
        {"name": "Stack with fitted temperature", "holdout": "2025+26", "score": "t=+0.22/+0.85",
         "verdict": "not proven"},
        {"name": "Stack plus fast/slow input", "holdout": "2025+26", "score": "t=+1.42/+0.94",
         "verdict": "not proven"},
        {"name": "Experience-gated stack", "holdout": "2025+26", "score": "t=+1.55/+0.58",
         "verdict": "not proven"},
        {"name": "Stack plus as-of lineup form", "holdout": "2025+26", "score": "t=+2.31/-0.64",
         "verdict": "rejected"},
    ]
