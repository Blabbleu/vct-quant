import json
import math

import numpy as np
import pandas as pd
import pytest

from research import asof_form_holdout as holdout
from research import asof_form_holdout_power as power

FROZEN = json.loads(holdout.FROZEN_PATH.read_text())
DESIGN = json.loads(holdout.DESIGN_PATH.read_text())


def rows(differences, elo=None):
    """Exact y=1 fixtures: each requested difference is log(candidate / Elo)."""
    e = np.full(len(differences), 0.5) if elo is None else np.asarray(elo, float)
    p = e * np.exp(differences)
    assert np.all((p > 0) & (p < 1))
    w0, w1 = FROZEN['weights']
    form = (holdout.stack.logits(p) - w0 * holdout.stack.logits(e)) * FROZEN['form_difference_scale'] / w1
    start = pd.Timestamp('2026-10-15T07:00:01Z')
    return pd.DataFrame([dict(match_id=i + 1, completed_at=start + pd.Timedelta(seconds=i),
                              y=1, tier=1, event_id=i // 10, p_elo=e[i],
                              player_form_diff=form[i]) for i in range(len(differences))])


def test_null_calibration_and_decreasing_registered_boundaries():
    assert DESIGN['looks'] == [150, 300, 450, 600]
    assert DESIGN['boundaries'] == pytest.approx(power.boundaries(DESIGN['constant']))
    assert all(a > b for a, b in zip(DESIGN['boundaries'], DESIGN['boundaries'][1:]))
    # Exact synthetic paired differences, centered to a zero empirical effect.
    values = np.tile(np.array([-0.08, -0.03, 0.03, 0.08]), 50)
    false_win = np.mean(power.sequential_max(values, simulations=20_000,
                                            seed=power.SEED + 17) > DESIGN['constant'])
    assert false_win <= 0.025


def test_frozen_loss_differences_from_exact_rows():
    requested = np.array([0.01, -0.02, 0.03, -0.04])
    frame = rows(requested)
    frame['year'] = [2025, 2025, 2026, 2026]
    result = power.paired_differences(frame, FROZEN)
    assert result[2025] == pytest.approx(requested[:2])
    assert result[2026] == pytest.approx(requested[2:])
    assert power.summary(np.concatenate(list(result.values())))['mean'] == pytest.approx(requested.mean())


def test_sequential_decisions_and_preserved_first_150():
    strong = rows(np.tile([0.03, 0.05], 75))
    assert holdout.evaluate(strong.iloc[:149], FROZEN)['verdict'] == 'PENDING'
    winning = holdout.evaluate(strong, FROZEN)
    assert winning['look_reached'] == 150
    assert winning['verdict'] == 'WIN'
    assert winning['primary']['n'] == 150
    assert winning['primary']['t'] == pytest.approx(winning['look_stats']['t'])
    assert winning['primary']['loss'] == pytest.approx(winning['look_stats']['loss'])

    # A positive first look below its boundary stays pending between looks.
    weak = rows(np.tile([-0.049, 0.051], 300))
    first = holdout.evaluate(weak.iloc[:150], FROZEN)
    assert first['look_reached'] == 150 and first['verdict'] == 'PENDING'
    between = holdout.evaluate(weak.iloc[:299], FROZEN)
    assert between['look_reached'] == 150 and between['verdict'] == 'PENDING'
    assert between['primary']['loss'] == pytest.approx(first['primary']['loss'])
    final = holdout.evaluate(weak, FROZEN)
    assert final['look_reached'] == 600 and final['verdict'] == 'NOT PROVEN'
    assert final['primary']['n'] == 150 and final['later_rows']['n'] == 450

    losing = rows(np.r_[np.tile([-0.049, 0.051], 75), np.tile([-0.07, 0.03], 75)])
    rejected = holdout.evaluate(losing, FROZEN)
    assert rejected['look_reached'] == 300 and rejected['verdict'] == 'REJECTED'
    assert rejected['look_stats']['t'] <= 0


def test_crossing_t_without_ece_does_not_win():
    # Elo averages 0.5; candidate 0.45 improves mean log loss, worsens ECE.
    elo = np.tile([0.99, 0.01], 75)
    differences = np.log(0.45 / elo)
    result = holdout.evaluate(rows(differences, elo), FROZEN)
    assert result['look_stats']['t'] > DESIGN['boundaries'][0]
    assert result['look_stats']['ece'] > result['look_stats']['elo_ece']
    assert result['verdict'] == 'PENDING'


def test_missing_match_table_row_raises(monkeypatch):
    class Connection:
        def execute(self, _):
            return self
        def df(self):
            return pd.DataFrame({'match_id': [999], 'event_id': [1]})
        def close(self):
            pass
    monkeypatch.setattr(holdout.db, 'connect', lambda **_: Connection())
    with pytest.raises(ValueError, match='no event_id'):
        holdout.evaluate(rows([0.02]).drop(columns='event_id'), FROZEN)


def test_nan_later_t_is_json_null(monkeypatch):
    original = holdout.stack.metrics
    def metrics(y, p, elo):
        result = original(y, p, elo)
        if len(y) == 1:
            result['t'] = math.nan
        return result
    monkeypatch.setattr(holdout.stack, 'metrics', metrics)
    result = holdout.evaluate(rows(np.tile([0.03, 0.05], 75).tolist() + [0.02]), FROZEN)
    assert result['later_rows']['t'] is None
    assert '"t": null' in json.dumps(result, allow_nan=False)
