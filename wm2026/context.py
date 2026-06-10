"""Build a :class:`FactorContext` from a match config and toggle the mock/live
data profile — the two glue pieces between a YAML file and the factor fan-out.

The heavy lifting (fetching, factor maths) lives in the existing modules; this
module only adapts their inputs so the workflow stays a thin orchestration layer.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from config.settings import settings
from factors.base import FactorContext

# Every ``use_mock_*`` flag the connectors honour. Forced True in mock mode so a
# clone runs fully offline with no API keys and no network round-trips.
_MOCK_FLAGS = (
    "use_mock_crawler",
    "use_mock_openfootball",
    "use_mock_thesportsdb",
    "use_mock_openligadb",
    "use_mock_wikidata",
    "use_mock_weather",
    "use_mock_rss",
    "use_mock_clubelo",
    "use_mock_football_data",
    "use_mock_fbref",
    "use_mock_understat",
    "use_mock_fotmob",
    "use_mock_sofascore",
    "use_mock_transfermarkt",
)


def apply_runtime_profile(mode: str) -> None:
    """Flip the global ``settings`` singleton into ``mock`` or ``live`` mode.

    ``mock`` forces every connector to its deterministic offline payload — the
    default for ``wm2026 predict`` so the repo is runnable out of the box.
    ``live`` leaves the ``.env`` toggles untouched (each connector still
    degrades to its mock on a network error, per the connector contract).
    """
    mode = (mode or "mock").lower()
    if mode == "mock":
        for flag in _MOCK_FLAGS:
            if hasattr(settings, flag):
                # BaseSettings guards plain assignment; mirror settings.py's own
                # object.__setattr__ escape hatch used by reload_runtime_flags().
                object.__setattr__(settings, flag, True)
        # The NVIDIA LLM scorer needs a paid key — never call it in mock mode.
        object.__setattr__(settings, "use_nvidia_llm", False)
    elif mode != "live":
        raise ValueError(f"unknown mode {mode!r} (expected 'mock' or 'live')")


def load_match_config(path: str | Path) -> dict[str, Any]:
    """Load + lightly validate a match YAML into a plain dict."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"match config not found: {p}")
    cfg = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    if "match" not in cfg or "teams" not in cfg:
        raise ValueError(
            f"{p} is missing the required 'match:' and/or 'teams:' blocks"
        )
    return cfg


def _parse_kickoff(raw: Any) -> datetime:
    if isinstance(raw, datetime):
        ko = raw
    else:
        text = str(raw or "").strip().replace("Z", "+00:00")
        try:
            ko = datetime.fromisoformat(text)
        except ValueError:
            ko = datetime.now(timezone.utc)
    if ko.tzinfo is None:
        ko = ko.replace(tzinfo=timezone.utc)
    return ko


def build_context(cfg: dict[str, Any]) -> FactorContext:
    """Map a parsed match config onto a fresh :class:`FactorContext`.

    Only the always-present YAML fields are wired here; everything external
    (history, xG, weather, squads …) is filled afterwards by the
    :class:`DataSourceOrchestrator` in :mod:`wm2026.pipeline`.
    """
    match = cfg.get("match", {})
    teams = cfg.get("teams", {})
    home = teams.get("home", {})
    away = teams.get("away", {})

    ctx = FactorContext(
        match_id=match.get("id") or "wm2026_match",
        config=cfg,
        home_code=str(home.get("code") or home.get("fifa_code") or "HOM").upper(),
        away_code=str(away.get("code") or away.get("fifa_code") or "AWY").upper(),
        kickoff_utc=_parse_kickoff(match.get("kickoff_utc")),
        venue=match.get("venue"),
        sentiment_payload=None,   # filled by the optional sentiment step
    )

    # Bookmaker-implied 1X2 (Phase 6 input). When the config carries odds we
    # pre-fill ctx.market_implied so the MarketOddsFactor tilts λ — exactly the
    # path match_service uses. The vig-free edge table is computed separately.
    odds = (match.get("bookmaker_odds_1x2") or cfg.get("odds_1x2"))
    implied = _implied_from_odds(odds)
    if implied is not None:
        ctx.market_implied = implied

    return ctx


def _implied_from_odds(odds: Any) -> tuple[float, float, float] | None:
    """Vig-free (home, draw, away) implied probabilities, or None."""
    from wm2026.edge import devig, parse_odds

    values = parse_odds(odds) if isinstance(odds, str) else odds
    if not values or len(values) < 3:
        return None
    fair, _ = devig(list(values)[:3])
    if len(fair) < 3:
        return None
    return (fair[0], fair[1], fair[2])


def synth_config(
    *,
    home_team: str,
    away_team: str,
    home_code: str | None = None,
    away_code: str | None = None,
    stage: str = "Group",
    kickoff: str | None = None,
    venue: str | None = None,
    home_xg: float = 1.40,
    away_xg: float = 1.30,
    home_xga: float = 1.30,
    away_xga: float = 1.40,
    home_elo: int = 1700,
    away_elo: int = 1700,
    odds_1x2: str | None = None,
) -> dict[str, Any]:
    """Build a minimal in-memory match config from CLI flags.

    Lets ``wm2026 predict --home Germany --away Brazil`` work without writing a
    YAML file first. Sensible WC-neutral defaults fill anything not provided.
    """
    code_h = (home_code or home_team[:3]).upper()
    code_a = (away_code or away_team[:3]).upper()
    slug = f"{code_h.lower()}_vs_{code_a.lower()}"
    cfg: dict[str, Any] = {
        "match": {
            "id": f"wm2026_{slug}",
            "tournament": "FIFA World Cup 2026",
            "phase": stage,
            "kickoff_utc": kickoff or datetime.now(timezone.utc).isoformat(),
            "venue": venue,
        },
        "teams": {
            "home": {
                "name": home_team, "code": code_h, "fifa_code": code_h,
                "elo_rating": home_elo, "avg_xg_season": home_xg,
                "avg_xg_conceded": home_xga, "form_last5": [],
            },
            "away": {
                "name": away_team, "code": code_a, "fifa_code": code_a,
                "elo_rating": away_elo, "avg_xg_season": away_xg,
                "avg_xg_conceded": away_xga, "form_last5": [],
            },
        },
    }
    if odds_1x2:
        cfg["match"]["bookmaker_odds_1x2"] = odds_1x2
    return cfg


__all__ = [
    "apply_runtime_profile",
    "load_match_config",
    "build_context",
    "synth_config",
]
