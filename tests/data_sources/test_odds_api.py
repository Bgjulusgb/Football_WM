"""Unit tests for the_odds_api connector — mock fallback + parser invariants."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest

from config.settings import settings
from data_sources.mock import odds_api_mock
from data_sources.odds_api import (
    OddsApiConnector,
    _matches_team,
    _median_btts,
    _median_h2h,
    _median_totals,
    _parse_event_list,
)


def _run(coro):
    return asyncio.run(coro)


# ── mock fallback ─────────────────────────────────────────────────────────────
def test_mock_odds_are_deterministic():
    """Same fixture → same odds on every call (test/CI reliance)."""
    a = odds_api_mock.odds_for("GER", "BRA")
    b = odds_api_mock.odds_for("GER", "BRA")
    assert a == b
    for key in ("1x2", "ou_2_5", "btts"):
        assert key in a
    # 1X2 has three entries, the others two
    assert len(a["1x2"]) == 3
    assert len(a["ou_2_5"]) == 2
    assert len(a["btts"]) == 2
    # All odds are valid decimals (> 1.0)
    for market in a.values():
        assert all(o > 1.0 for o in market)


def test_mock_odds_have_realistic_overround():
    """1X2 implied probabilities sum to a typical book overround (~1.05)."""
    odds = odds_api_mock.odds_for("GER", "BRA")
    implied = sum(1.0 / o for o in odds["1x2"])
    assert 1.02 < implied < 1.10


def test_connector_returns_mock_when_use_mock_flag_set(monkeypatch):
    monkeypatch.setattr(settings, "use_mock_odds_api", True)
    monkeypatch.setattr(settings, "odds_api_key", "irrelevant")
    res = _run(OddsApiConnector().get_odds("GER", "BRA", None))
    assert res.mode == "mock"
    assert res.data == odds_api_mock.odds_for("GER", "BRA")


def test_connector_returns_mock_when_no_key(monkeypatch):
    monkeypatch.setattr(settings, "use_mock_odds_api", False)
    monkeypatch.setattr(settings, "odds_api_key", "")
    res = _run(OddsApiConnector().get_odds("GER", "BRA", None))
    assert res.mode == "mock"


# ── parser ────────────────────────────────────────────────────────────────────
def test_matches_team_handles_code_name_and_substring():
    assert _matches_team("Germany", "GER", "Germany")
    assert _matches_team("GER", "GER", None)
    assert _matches_team("Korea Republic", "KOR", "South Korea")
    assert not _matches_team("Argentina", "BRA", "Brazil")
    assert not _matches_team(None, "BRA", "Brazil")


def test_median_h2h_picks_robust_centre():
    event = {
        "bookmakers": [
            {"markets": [{"key": "h2h", "outcomes": [
                {"name": "Germany", "price": 2.00},
                {"name": "Draw", "price": 3.40},
                {"name": "Brazil", "price": 3.80}]}]},
            {"markets": [{"key": "h2h", "outcomes": [
                {"name": "Germany", "price": 2.10},
                {"name": "Draw", "price": 3.30},
                {"name": "Brazil", "price": 3.70}]}]},
            {"markets": [{"key": "h2h", "outcomes": [
                # Outlier book; median should ignore it
                {"name": "Germany", "price": 1.50},
                {"name": "Draw", "price": 4.50},
                {"name": "Brazil", "price": 5.00}]}]},
        ],
    }
    odds = _median_h2h(event, home_code="GER", away_code="BRA",
                       home_name="Germany", away_name="Brazil")
    assert odds == [2.0, 3.4, 3.8]      # the middle book wins


def test_median_h2h_handles_reversed_orientation():
    """Bookies sometimes flip home/away vs. the FIFA pair."""
    event = {
        "_orientation_reversed": True,
        "bookmakers": [{"markets": [{"key": "h2h", "outcomes": [
            {"name": "Brazil", "price": 2.00},
            {"name": "Draw", "price": 3.30},
            {"name": "Germany", "price": 3.80},
        ]}]}],
    }
    odds = _median_h2h(event, home_code="GER", away_code="BRA",
                       home_name="Germany", away_name="Brazil")
    # Outcomes get swapped back to (home=GER, draw, away=BRA).
    assert odds == [3.8, 3.3, 2.0]


def test_median_totals_filters_by_point():
    event = {
        "bookmakers": [{"markets": [{"key": "totals", "outcomes": [
            {"name": "Over", "price": 1.85, "point": 2.5},
            {"name": "Under", "price": 1.95, "point": 2.5},
            {"name": "Over", "price": 1.45, "point": 3.5},      # different line
            {"name": "Under", "price": 2.60, "point": 3.5},
        ]}]}],
    }
    odds = _median_totals(event, line=2.5)
    assert odds == [1.85, 1.95]


def test_median_btts_accepts_both_key_aliases():
    """``btts`` vs ``both_teams_to_score`` both seen across bookies."""
    event = {
        "bookmakers": [
            {"markets": [{"key": "btts", "outcomes": [
                {"name": "Yes", "price": 1.80}, {"name": "No", "price": 2.00}]}]},
            {"markets": [{"key": "both_teams_to_score", "outcomes": [
                {"name": "Yes", "price": 1.85}, {"name": "No", "price": 1.95}]}]},
        ],
    }
    odds = _median_btts(event)
    assert odds == [1.825, 1.975]


def test_parse_event_list_picks_closest_kickoff():
    kickoff = datetime(2026, 6, 18, 18, 0, tzinfo=timezone.utc)
    far = odds_api_mock.envelope_for("GER", "BRA")
    far["commence_time"] = "2026-06-25T18:00:00Z"           # 7d off
    near = odds_api_mock.envelope_for("GER", "BRA")
    near["commence_time"] = "2026-06-18T18:30:00Z"          # 30 min off
    out = _parse_event_list(
        [far, near], home_code="GER", away_code="BRA",
        home_name="Germany", away_name="Brazil",
        kickoff_utc=kickoff,
    )
    assert out is not None
    assert {"1x2", "ou_2_5", "btts"} <= set(out)


def test_parse_event_list_returns_none_when_no_team_match():
    envelope = odds_api_mock.envelope_for("GER", "BRA")
    out = _parse_event_list(
        [envelope], home_code="ESP", away_code="ITA",
        home_name="Spain", away_name="Italy",
        kickoff_utc=None,
    )
    assert out is None


# ── pipeline integration ──────────────────────────────────────────────────────
def test_pipeline_uses_live_odds_when_cli_omits_them(monkeypatch):
    """Phase-4 wiring: orchestrator → ctx.live_odds → pipeline picks them up."""
    import asyncio as _asyncio

    from wm2026.context import synth_config
    from wm2026.pipeline import run_prediction

    cfg = synth_config(home_team="Germany", away_team="Brazil")
    result = _asyncio.run(run_prediction(cfg, mode="mock", bootstrap_n=32))
    # The edge table should contain rows with real decimal_odd values from
    # the mock connector — not just model-only rows.
    has_priced_rows = any(
        r.get("decimal_odd") is not None and r["market"] == "1X2"
        for r in result["edges"]
    )
    assert has_priced_rows, "live odds from connector should populate the edge table"
