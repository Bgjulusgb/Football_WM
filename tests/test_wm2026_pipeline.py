"""Smoke + invariant tests for the wm2026 workflow (mock mode, no network).

Deliberately self-contained: uses ``asyncio.run`` instead of pytest-asyncio so
the suite runs with a bare ``pytest`` + the core requirements.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

from wm2026.context import synth_config
from wm2026.edge import compute_edges, devig, kelly_fraction, parse_odds
from wm2026.pipeline import run_prediction
from wm2026.report import build_report

REPO = Path(__file__).resolve().parents[1]
SAMPLE = REPO / "config" / "matches" / "group_a" / "cze_vs_rsa.yaml"


def _run(cfg, **kw):
    return asyncio.run(run_prediction(cfg, mode="mock", bootstrap_n=64, **kw))


# ── edge math (pure) ──────────────────────────────────────────────────────────
def test_parse_odds_variants():
    assert parse_odds("2.10/3.40/3.20") == [2.10, 3.40, 3.20]
    assert parse_odds("1.85, 1.95") == [1.85, 1.95]
    assert parse_odds("") is None
    assert parse_odds(None) is None


def test_devig_normalises_to_one():
    fair, overround = devig([2.10, 3.40, 3.20])
    assert overround > 1.0                      # book always has a margin
    assert abs(sum(fair) - 1.0) < 1e-9          # fair probs sum to 1


def test_kelly_zero_when_no_edge():
    # p * odd = 1 → no edge → no stake
    assert kelly_fraction(0.5, 2.0) == 0.0
    assert kelly_fraction(0.6, 2.0) > 0.0       # genuine edge → positive stake


def test_compute_edges_flags_value():
    rows = compute_edges({"home_win": 0.55, "draw": 0.22, "away_win": 0.23,
                          "over_25": 0.5, "btts": 0.5},
                         odds_1x2=[2.10, 3.40, 3.20])
    home = next(r for r in rows if r["selection"] == "Home")
    assert home["edge_pct"] is not None and home["edge_pct"] > 10.0
    assert home["action"] == "sanity-check"


# ── full pipeline (mock) ──────────────────────────────────────────────────────
def test_pipeline_runs_on_sample_config():
    cfg = __import__("yaml").safe_load(SAMPLE.read_text(encoding="utf-8"))
    result = _run(cfg, odds_1x2=[2.10, 3.40, 3.20])
    out = result["prediction"]
    s = out.home_win_prob + out.draw_prob + out.away_win_prob
    assert abs(s - 1.0) < 0.01                  # 1X2 is a proper distribution
    assert 0.3 <= out.home_xg <= 4.0            # λ stays physical
    assert 0.3 <= out.away_xg <= 4.0
    assert result["best_value"] is not None     # +EV home line with these odds


def test_pipeline_synth_config_no_odds():
    cfg = synth_config(home_team="Germany", away_team="Brazil",
                       home_xg=1.7, away_xg=1.6)
    result = _run(cfg)
    assert result["best_value"] is None         # no odds → no value pick
    assert result["prediction"].over_25 >= 0.0


def test_report_json_schema_and_markdown():
    cfg = synth_config(home_team="France", away_team="Senegal",
                       odds_1x2="1.70/3.60/4.50")
    result = _run(cfg, odds_1x2=[1.70, 3.60, 4.50])
    report = build_report(result)
    js = report["json"]
    # JSON is serialisable and carries the required top-level keys.
    json.dumps(js)
    for key in ("match_id", "model_version", "markets", "per_model",
                "confidence_intervals", "ensemble_confidence",
                "factors_used", "factors_total", "edge_table"):
        assert key in js, f"missing {key}"
    assert set(js["per_model"]) == {"poisson", "negbin", "glm_poisson"}
    assert "# 🏆 WM 2026" in report["markdown"]
    assert "Edge Table" in report["markdown"]


def test_factor_unavailability_renormalises():
    # No external data + no sentiment → some factors go unavailable, but the
    # ensemble must still return a proper distribution (re-normalisation).
    cfg = synth_config(home_team="Japan", away_team="Croatia")
    result = _run(cfg)
    used = result["prediction"].features["active_factors"]
    skipped = result["prediction"].features["skipped_factors"]
    assert len(used) >= 5                        # core factors always fire
    assert len(skipped) >= 1                     # sentiment/weather neutralise
