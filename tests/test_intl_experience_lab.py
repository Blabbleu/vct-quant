import numpy as np
import pandas as pd

from scripts.intl_experience_lab import adjust, experience_gap, is_international, paired_t


def test_international_event_names():
    assert is_international("Valorant Champions 2026")
    assert is_international("Valorant Champions Tour Stage 2: Masters Reykjavík")
    assert is_international("Champions Tour 2024: Masters Madrid")
    assert is_international("Valorant Masters Toronto 2025")
    assert is_international("Champions Tour 2023: LOCK//IN São Paulo")
    assert not is_international("Champions Tour North America Stage 1: Masters")
    assert not is_international("Champions Tour 2024: EMEA Stage 1")
    assert not is_international("Champions Tour 2023: Champions China Qualifier")
    assert not is_international(None)


def test_experience_is_point_in_time():
    matches = pd.DataFrame({"match_id": [1, 2, 3]})
    stats = pd.DataFrame([
        # match 1 (international): p1,p2 for side 1; p3 for side 2; 2 maps each
        {"match_id": 1, "team_number": 1, "player_key": "p1", "maps": 2},
        {"match_id": 1, "team_number": 1, "player_key": "p2", "maps": 2},
        {"match_id": 1, "team_number": 2, "player_key": "p3", "maps": 2},
        # match 2 (domestic): p1 vs p4
        {"match_id": 2, "team_number": 1, "player_key": "p1", "maps": 3},
        {"match_id": 2, "team_number": 2, "player_key": "p4", "maps": 3},
        # match 3: p4 vs p3
        {"match_id": 3, "team_number": 1, "player_key": "p4", "maps": 1},
        {"match_id": 3, "team_number": 2, "player_key": "p3", "maps": 1},
    ])
    out = experience_gap(matches, stats, intl_ids={1}).set_index("match_id")
    # Match 1 sees no prior experience: its own maps never count for itself.
    assert out.loc[1, "gap"] == 0.0
    # Match 2: p1 has 2 intl maps from match 1; p4 has none. Domestic maps never add.
    assert np.isclose(out.loc[2, "gap"], np.log1p(2))
    # Match 3: p4 has 0 (match 2 was domestic), p3 has 2.
    assert np.isclose(out.loc[3, "gap"], -np.log1p(2))


def test_beta_zero_reproduces_elo_and_mask_limits_scope():
    p = np.array([0.6, 0.3, 0.8])
    gap = np.array([1.0, -1.0, 2.0])
    assert np.allclose(adjust(p, gap, 0.0, np.ones(3)), p)
    moved = adjust(p, gap, 0.5, np.array([1.0, 0.0, 0.0]))
    assert moved[0] > p[0] and np.isclose(moved[1], p[1]) and np.isclose(moved[2], p[2])


def test_paired_t_sign():
    base = np.array([0.7, 0.6, 0.8, 0.65])
    better = base - np.array([0.05, 0.04, 0.06, 0.05])
    assert paired_t(base, better) > 0
