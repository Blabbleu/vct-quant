"""Numerical audit of the frozen batch BT replay; no model selection."""
from __future__ import annotations

import os
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["OMP_NUM_THREADS"] = "1"

from dataclasses import dataclass
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd
from scipy.optimize import minimize

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from research import batch_bt

YEARS = (2023, 2024, 2025, 2026)
GRAD_TOL = 1e-5
ORIGINAL_OPTIONS = {"maxiter": 20, "ftol": 1e-7, "gtol": 1e-4}
REGISTERED_OPTIONS = {"maxiter": 2000, "ftol": 1e-12, "gtol": 1e-8}
POST_AUDIT_OPTIONS = {"maxiter": 5000, "ftol": 0.0, "gtol": 1e-8}


def select_buckets(frame: pd.DataFrame) -> dict[int, tuple[int, ...]]:
    """Select chronology positions using dates and decisive eligibility only."""
    days = batch_bt.assigned_days(frame)
    buckets = days // 3
    years = pd.to_datetime(frame.completed_at, utc=True).dt.year.to_numpy()
    eligible = (frame.tier.to_numpy() == 1) & np.isin(frame.score_a.to_numpy(), (0, 1))
    selected = {}
    for year in YEARS:
        unique = np.unique(buckets[eligible & (years == year)])
        if len(unique):
            selected[year] = tuple(dict.fromkeys(int(unique[j]) for j in (0, (len(unique)-1)//2, len(unique)-1)))
    return selected


def fit_details(a, b, success, trials, age, nteams, start, options):
    """Same weighted MAP objective and gradient as the frozen implementation."""
    weights = np.exp2(-np.asarray(age, float) / batch_bt.FROZEN_CELL.half_life)
    sw, tw = weights * success, weights * trials
    initial = np.asarray(start, float).copy()

    def objective(s):
        z = s[a] - s[b]
        value = float(np.sum(tw * np.logaddexp(0, z) - sw * z)
                      + batch_bt.FROZEN_CELL.penalty * np.dot(s, s))
        residual = tw * batch_bt.sigmoid(z) - sw
        grad = (np.bincount(a, weights=residual, minlength=nteams)
                - np.bincount(b, weights=residual, minlength=nteams)
                + 2 * batch_bt.FROZEN_CELL.penalty * s)
        return value, grad

    if not len(a) or not np.any(tw):
        x = np.zeros(nteams)
        value, grad = objective(x)
        return x, {"success": True, "reason": "no eligible observations", "iterations": 0,
                   "objective": value, "max_gradient": float(np.max(np.abs(grad), initial=0))}
    result = minimize(objective, initial, jac=True, method="L-BFGS-B", options=options)
    if not np.isfinite(result.x).all():
        raise RuntimeError("BT optimizer produced nonfinite strengths")
    value, grad = objective(result.x)
    return result.x, {"success": bool(result.success), "reason": str(result.message),
                      "iterations": int(result.nit), "objective": value,
                      "max_gradient": float(np.max(np.abs(grad), initial=0))}


@dataclass
class BucketFit:
    year: int
    bucket: int
    cutoff_day: int
    fixture_indices: np.ndarray
    eligible_indices: np.ndarray
    start: np.ndarray
    original: dict
    probabilities: np.ndarray


def frozen_replay_sample(frame: pd.DataFrame, selected: dict[int, tuple[int, ...]]):
    """One exact frozen-cell replay, retaining inputs at selected fit boundaries."""
    frame = frame.sort_values("match_id", kind="stable").reset_index(drop=True)
    day = batch_bt.assigned_days(frame)
    bucket = day // 3
    teams = pd.Index(pd.unique(pd.concat([frame.team_a, frame.team_b], ignore_index=True)))
    a, b = teams.get_indexer(frame.team_a), teams.get_indexer(frame.team_b)
    success, trials = batch_bt.observations(frame, batch_bt.FROZEN_CELL.mode)
    years = pd.to_datetime(frame.completed_at, utc=True).dt.year.to_numpy()
    tier = frame.tier.to_numpy()
    decisive = np.isin(frame.score_a.to_numpy(), (0, 1))
    selected_pairs = {(year, bucket_) for year, buckets in selected.items() for bucket_ in buckets}
    out = np.full(len(frame), np.nan)
    strengths = np.zeros(len(teams))
    previous_bucket = None
    records = []
    recorded_pairs = set()
    for i in range(len(frame)):
        if bucket[i] != previous_bucket:
            cutoff = int(bucket[i] * 3)
            eligible = np.flatnonzero((day[:i] < cutoff) & (trials[:i] > 0))
            start = strengths if previous_bucket is None or bucket[i] > previous_bucket else None
            initial = np.zeros(len(teams)) if start is None else start.copy()
            strengths, diag = fit_details(a[eligible], b[eligible], success[eligible],
                                          trials[eligible], cutoff-day[eligible],
                                          len(teams), initial, ORIGINAL_OPTIONS)
            seen = np.zeros(len(teams), dtype=bool)
            seen[a[eligible]] = True
            seen[b[eligible]] = True
            strengths[~seen] = 0
            previous_bucket = bucket[i]
            end = i + 1
            while end < len(frame) and bucket[end] == bucket[i]:
                end += 1
            for pair in sorted(p for p in selected_pairs - recorded_pairs if p[1] == int(bucket[i])):
                fixtures = np.flatnonzero((years[i:end] == pair[0])
                                              & (tier[i:end] == 1) & decisive[i:end]) + i
                if len(fixtures):
                    records.append(BucketFit(pair[0], pair[1], cutoff, fixtures,
                                             eligible.copy(), initial.copy(), diag.copy(),
                                             batch_bt.sigmoid(strengths[a[fixtures]]-strengths[b[fixtures]])))
                    recorded_pairs.add(pair)
        out[i] = batch_bt.sigmoid(strengths[a[i]] - strengths[b[i]])
    if len(records) != len(selected_pairs):
        raise AssertionError("selected bucket absent from replay")
    return records, (day, a, b, success, trials, len(teams), out, frame.match_id.to_numpy())


def run_pass(records, arrays, options):
    day, a, b, success, trials, nteams, _, match_ids = arrays
    rows = []
    for record in records:
        eligible = record.eligible_indices
        if not np.all(day[eligible] < record.cutoff_day):
            raise AssertionError("refit includes current or later bucket")
        x, diag = fit_details(a[eligible], b[eligible], success[eligible], trials[eligible],
                              record.cutoff_day-day[eligible], nteams, record.start, options)
        seen = np.zeros(nteams, dtype=bool)
        seen[a[eligible]] = True
        seen[b[eligible]] = True
        x[~seen] = 0
        f = record.fixture_indices
        new_p = batch_bt.sigmoid(x[a[f]]-x[b[f]])
        delta = np.abs(new_p-record.probabilities)
        rows.append({"year": record.year, "bucket": record.bucket,
                     "date": str(pd.Timestamp(record.cutoff_day, unit="D").date()),
                     "n_training": len(eligible), "n_fixtures": len(f),
                     "match_ids": match_ids[f].astype(int).tolist(), "original": record.original, "reference": diag,
                     "original_probabilities": record.probabilities.tolist(),
                     "reference_probabilities": new_p.tolist(), "absolute_changes": delta.tolist()})
    return rows


def summarize(rows):
    summary = {}
    for label, subset in [(str(y), [r for r in rows if r["year"] == y]) for y in YEARS] + [("overall", rows)]:
        if not subset:
            continue
        differences = [v for row in subset for v in row["absolute_changes"]]
        summary[label] = {"buckets": len(subset), "fixtures": len(differences),
                          "capped_or_unconverged": sum(r["original"]["iterations"] >= 20
                            or not r["original"]["success"]
                            or r["original"]["max_gradient"] > GRAD_TOL for r in subset),
                          "reference_unconverged": sum(r["reference"]["max_gradient"] > GRAD_TOL
                            or not np.isfinite(r["reference"]["max_gradient"]) for r in subset),
                          "max_abs_change": float(np.max(differences)),
                          "median_abs_change": float(np.median(differences))}
    failed = summary["overall"]["reference_unconverged"] > 0
    material = summary["overall"]["max_abs_change"] >= .005 or summary["overall"]["median_abs_change"] >= .001
    return summary, "INCONCLUSIVE" if failed else "MATERIAL" if material else "STABLE AT THIS SAMPLE"


def main():
    frame = batch_bt.load_matches().sort_values("match_id", kind="stable").reset_index(drop=True)
    selected = select_buckets(frame)
    print("selected buckets (date and eligibility only):", selected, flush=True)
    records, arrays = frozen_replay_sample(frame, selected)
    first = run_pass(records, arrays, REGISTERED_OPTIONS)
    first_summary, first_verdict = summarize(first)
    output = {"registered": {"rows": first, "summary": first_summary, "verdict": first_verdict}}
    if first_verdict == "INCONCLUSIVE":
        print("registered pass INCONCLUSIVE; starting post-audit numerical pass", flush=True)
        second = run_pass(records, arrays, POST_AUDIT_OPTIONS)
        second_summary, second_verdict = summarize(second)
        output["post_audit"] = {"rows": second, "summary": second_summary, "verdict": second_verdict}
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
