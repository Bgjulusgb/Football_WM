"""Conservative (bootstrap-p5) staking + Asian-handicap edge rows."""
from __future__ import annotations

from wm2026.edge import compute_edges, evaluate_asian_handicap, evaluate_line


def test_conservative_edge_is_below_point_estimate():
    row = evaluate_line("1X2", "Home", 0.55, 2.10, 0.44, model_p_lower=0.48)
    # p50 edge = 0.55*2.10-1 = 0.155; p5 edge = 0.48*2.10-1 = 0.008
    assert row.edge_pct is not None and row.edge_pct_cons is not None
    assert row.edge_pct_cons < row.edge_pct
    assert row.half_kelly_cons is not None and row.half_kelly_cons <= row.half_kelly_pct


def test_conservative_fields_none_without_ci():
    row = evaluate_line("1X2", "Home", 0.55, 2.10, 0.44)
    assert row.model_p_lower is None
    assert row.edge_pct_cons is None
    assert row.half_kelly_cons is None


def test_compute_edges_threads_ci_including_complements():
    ci = {
        "home_win": [0.48, 0.55, 0.62],
        "draw": [0.18, 0.22, 0.26],
        "away_win": [0.18, 0.23, 0.28],
        "over_25": [0.42, 0.50, 0.58],
        "btts": [0.44, 0.50, 0.56],
    }
    rows = compute_edges(
        {"home_win": 0.55, "draw": 0.22, "away_win": 0.23,
         "over_25": 0.50, "btts": 0.50},
        odds_1x2=[2.10, 3.40, 3.20], odds_ou25=[1.95, 1.95],
        odds_btts=[1.90, 1.90], ci=ci,
    )
    home = next(r for r in rows if r["selection"] == "Home")
    assert home["model_p_lower"] == 0.48
    # Under 2.5 uses the complement lower bound: 1 - p95(over) = 1 - 0.58 = 0.42.
    under = next(r for r in rows if r["selection"] == "Under 2.5")
    assert abs(under["model_p_lower"] - 0.42) < 1e-9


def test_double_chance_rows_emitted_with_odds():
    rows = compute_edges(
        {"home_win": 0.55, "draw": 0.22, "away_win": 0.23,
         "over_25": 0.5, "btts": 0.5},
        odds_dc=[1.25, 1.30, 1.55],
    )
    dc = [r for r in rows if r["market"] == "Double Chance"]
    assert {r["selection"] for r in dc} == {"1X", "12", "X2"}
    one_x = next(r for r in dc if r["selection"] == "1X")
    assert abs(one_x["model_p"] - 0.77) < 1e-9     # 0.55 + 0.22


def test_asian_handicap_edge_rows():
    ah = {"line": -0.5, "home_win": 0.60, "push": 0.0, "away_win": 0.40,
          "home_prob_nopush": 0.60, "away_prob_nopush": 0.40}
    rows = evaluate_asian_handicap(ah, home_odd=1.80, away_odd=2.10)
    assert len(rows) == 2
    home = next(r for r in rows if r["selection"] == "Home")
    # EV = 0.60*1.80 + 0 - 1 = 0.08 → 8%
    assert abs(home["edge_pct"] - 8.0) < 1e-6
    assert home["market"] == "AH -0.5"
    # model-only when no odds
    none_rows = evaluate_asian_handicap(ah)
    assert all(r["decimal_odd"] is None for r in none_rows)
