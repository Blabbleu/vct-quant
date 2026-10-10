"""Pre-match round-share generative series benchmark; run as a script."""
from __future__ import annotations

from collections import defaultdict, deque
from itertools import product
from math import comb, log, sqrt
from pathlib import Path
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from vct_quant import db
from vct_quant.features.build import elo_k, margin_signal, match_sequence
from vct_quant.features.ratings import compute_elo

GRID = tuple(product((10, 30, 100), (100, 500), (0.25, 0.5, 1.0)))


def team_key(team_id: object, team_name: object) -> str:
    if not pd.isna(team_id):
        return str(int(team_id))
    return "name:" + str(team_name).strip().lower()


def valid_map_rows(rows: list[tuple], expected: tuple[str, str]) -> tuple[int, int] | None:
    """Rows are (side, score, match-team id, match-team name, score-team id)."""
    if len(rows) != 2 or {row[0] for row in rows} != {1, 2}:
        return None
    ordered = sorted(rows, key=lambda row: row[0])
    for side, row in enumerate(ordered):
        _, score, team_id, team_name, score_team_id = row
        if team_key(team_id, team_name) != expected[side]:
            return None
        if pd.isna(score) or int(score) != score or score < 0:
            return None
        if not pd.isna(score_team_id) and not pd.isna(team_id) and int(score_team_id) != int(team_id):
            return None
    return int(ordered[0][1]), int(ordered[1][1])


def load_maps(con, expected: dict[int, tuple[str, str]]) -> tuple[dict[int, list[tuple[int, int]]], dict[str, int]]:
    """Load scores without map names; reject incomplete and identity-misaligned maps."""
    rows = con.execute("""
        SELECT mm.match_id, mm.match_map_id, s.team_number, s.total_rounds,
               mt.team_id, mt.team_name, s.team_id AS score_team_id
        FROM match_map mm
        LEFT JOIN match_map_team_score s ON s.match_map_id = mm.match_map_id
        LEFT JOIN match_team mt ON mt.match_id = mm.match_id AND mt.team_number = s.team_number
        ORDER BY mm.match_id, mm.match_map_id, s.team_number
    """).fetchall()
    grouped: dict[tuple[int, int], list[tuple]] = defaultdict(list)
    for match_id, map_id, *rest in rows:
        grouped[(match_id, map_id)].append(tuple(rest))
    result: dict[int, list[tuple[int, int]]] = defaultdict(list)
    counts = {"total": len(grouped), "valid": 0, "rejected": 0, "alignment_rejected": 0, "skipped": 0}
    for (match_id, _), score_rows in grouped.items():
        pair = expected.get(match_id)
        if pair is None:
            counts["skipped"] += 1
            continue
        sides = valid_map_rows(score_rows, pair)
        if sides is None:
            counts["rejected"] += 1
            if len(score_rows) == 2 and {r[0] for r in score_rows} == {1, 2}:
                if any(team_key(r[2], r[3]) != pair[int(r[0]) - 1] or
                       (not pd.isna(r[4]) and not pd.isna(r[2]) and int(r[4]) != int(r[2]))
                       for r in score_rows):
                    counts["alignment_rejected"] += 1
            continue
        result[match_id].append(sides)
        counts["valid"] += 1
    return dict(result), counts


def sigmoid(x: float) -> float:
    return 1.0 / (1.0 + np.exp(-x))


def logit(p: float) -> float:
    p = min(max(float(p), 1e-12), 1 - 1e-12)
    return log(p / (1 - p))


def map_probability(p: float) -> float:
    q = 1 - p
    regulation = sum(comb(12 + k, k) * p**13 * q**k for k in range(12))
    tie = comb(24, 12) * p**12 * q**12
    overtime = p * p / (p * p + q * q) if 0 < p < 1 else p
    return regulation + tie * overtime


def series_probability(p_map: float, best_of: int) -> float:
    if best_of not in (1, 3, 5):
        raise ValueError("unsupported best-of")
    needed = best_of // 2 + 1
    return sum(comb(best_of, k) * p_map**k * (1 - p_map)**(best_of - k)
               for k in range(needed, best_of + 1))


def predict_sequence(matches: pd.DataFrame, maps: dict[int, list[tuple[int, int]]],
                     cell: tuple[int, int, float]) -> pd.DataFrame:
    n_maps, alpha, gamma = cell
    history: dict[str, deque[tuple[int, int]]] = defaultdict(lambda: deque(maxlen=n_maps))
    output = []
    for row in matches.itertuples(index=False):
        prior_a, prior_b = history[row.team_a], history[row.team_b]
        covered = bool(prior_a and prior_b and row.best_of in (1, 3, 5)
                       and any(w + l > 0 for w, l in prior_a)
                       and any(w + l > 0 for w, l in prior_b))
        p = row.p_elo
        if covered:
            wa, la = map(sum, zip(*prior_a))
            wb, lb = map(sum, zip(*prior_b))
            ra = (wa + alpha / 2) / (wa + la + alpha)
            rb = (wb + alpha / 2) / (wb + lb + alpha)
            p_round = sigmoid(logit(ra) - logit(rb))
            p = sigmoid(gamma * logit(series_probability(map_probability(p_round), int(row.best_of))))
        output.append((row.match_id, p, covered, len(maps.get(row.match_id, ()))))
        # Advance both teams only after the whole series prediction.
        for score_a, score_b in maps.get(row.match_id, ()):
            prior_a.append((score_a, score_b))
            prior_b.append((score_b, score_a))
    return pd.DataFrame(output, columns=["match_id", "p_model", "covered", "valid_maps"])


def ece(y: np.ndarray, p: np.ndarray) -> float:
    bins = np.minimum((p * 10).astype(int), 9)
    return sum(abs(y[bins == i].mean() - p[bins == i].mean()) * (bins == i).sum()
               for i in range(10) if (bins == i).any()) / len(y)


def metrics(frame: pd.DataFrame) -> dict:
    y = frame.score_a.to_numpy(dtype=float)
    p = np.clip(frame.p_model.to_numpy(dtype=float), 1e-12, 1 - 1e-12)
    q = np.clip(frame.p_elo.to_numpy(dtype=float), 1e-12, 1 - 1e-12)
    loss = -(y * np.log(p) + (1 - y) * np.log(1 - p))
    base = -(y * np.log(q) + (1 - y) * np.log(1 - q))
    delta = base - loss
    t = float(delta.mean() / (delta.std(ddof=1) / sqrt(len(delta)))) if len(delta) > 1 and delta.std(ddof=1) > 0 else 0.0
    return dict(n=len(frame), covered=int(frame.covered.sum()), maps=int(frame.valid_maps.sum()),
                loss=loss.mean(), elo_loss=base.mean(), brier=np.mean((p-y)**2),
                elo_brier=np.mean((q-y)**2), accuracy=np.mean((p >= .5) == y),
                elo_accuracy=np.mean((q >= .5) == y), t=t, ece=ece(y, p), elo_ece=ece(y, q))


def main() -> None:
    con = db.connect(read_only=True)
    try:
        matches = match_sequence(con).reset_index(drop=True)
        assert "best_of" not in matches.columns, "match_sequence unexpectedly contains best_of"
        formats = con.execute("SELECT match_id, best_of FROM match").df()
        expected = {int(r.match_id): (r.team_a, r.team_b) for r in matches.itertuples(index=False)}
        maps, availability = load_maps(con, expected)
        map_totals = dict(con.execute("SELECT match_id, count(*) FROM match_map GROUP BY match_id").fetchall())
    finally:
        con.close()
    elo = pd.DataFrame(compute_elo(zip(matches.match_id, matches.team_a, matches.team_b,
                                        margin_signal(matches)), k=elo_k(matches.tier))[0])
    matches = matches.merge(elo[["match_id", "p_a_win"]], on="match_id", validate="one_to_one")
    matches = matches.rename(columns={"p_a_win": "p_elo"}).merge(formats, on="match_id", validate="one_to_one")
    matches["test_year"] = pd.to_datetime(matches.completed_at, utc=True).dt.year
    eligible = matches.tier.eq(1) & matches.score_a.isin((0.0, 1.0)) & matches.test_year.between(2023, 2026)
    print("Map availability:", availability)
    training = eligible & matches.test_year.isin((2023, 2024))
    scored = []
    for cell in GRID:
        predictions = predict_sequence(matches, maps, cell)
        joined = matches.join(predictions.set_index("match_id"), on="match_id", validate="one_to_one")
        scored.append((metrics(joined.loc[training])["loss"], cell))
    winner = min(scored, key=lambda item: item[0])
    print("Grid winner:", winner[1], "train log loss:", f"{winner[0]:.6f}")
    predictions = predict_sequence(matches, maps, winner[1])
    joined = matches.join(predictions.set_index("match_id"), on="match_id", validate="one_to_one")
    print("year n covered valid_maps all_maps model_loss elo_loss model_brier elo_brier model_acc elo_acc t model_ece elo_ece")
    by_year = {}
    for year in (2023, 2024, 2025, 2026):
        subset = joined.loc[eligible & matches.test_year.eq(year)]
        if subset.empty:
            print(year, "no completed binary matches")
            continue
        m = metrics(subset)
        by_year[year] = m
        all_maps = sum(map_totals.get(int(match_id), 0) for match_id in subset.match_id)
        print(year, m["n"], m["covered"], m["maps"], all_maps, *(f"{m[k]:.6f}" for k in
              ("loss", "elo_loss", "brier", "elo_brier", "accuracy", "elo_accuracy", "t", "ece", "elo_ece")))
        for label, column in (("model", "p_model"), ("elo", "p_elo")):
            bins = np.minimum((subset[column].to_numpy() * 10).astype(int), 9)
            print(year, label, "calibration:", [(i, int((bins == i).sum()),
                  round(float(subset.score_a.to_numpy()[bins == i].mean()), 4),
                  round(float(subset[column].to_numpy()[bins == i].mean()), 4))
                  for i in range(10) if (bins == i).any()])
    if all(y in by_year for y in (2025, 2026)):
        a, b = by_year[2025], by_year[2026]
        verdict = ("WIN" if all(m["t"] > 2 and m["ece"] <= m["elo_ece"] for m in (a, b))
                   else "TIE / not proven" if all(m["t"] > 0 for m in (a, b)) else "LOSS / reject")
        print("Verdict:", verdict)


if __name__ == "__main__":
    main()
