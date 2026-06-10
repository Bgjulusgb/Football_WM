"""The 8-phase prediction pipeline (master prompt → runnable code).

``run_prediction`` ties the existing modules together into one async call:

    Phase 1  Data Collection      data_sources.DataSourceOrchestrator.populate
    Phase 2  Factor Decomposition factors.registry.get_active_factors → compute
    Phase 3  Sentiment Layer       optional sentiment_payload (best-effort)
    Phase 4  Goal-Model Stack      analysis.MatchPredictor.predict_from_signals
             + Bootstrap CIs        models_ml.poisson_goals.bootstrap_markets
    Phase 5  Calibration          analysis.calibration (graceful, prior-based)
    Phase 6  Market Edge          wm2026.edge.compute_edges
    Phase 7  Validation           sanity checks → list of warnings
    Phase 8  Output               handled by wm2026.report.build_report

The function returns a single ``result`` dict carrying every raw piece the
report needs. Nothing here imports FastAPI / SQLAlchemy / Prefect, so a fresh
clone runs the whole thing offline with only the core requirements.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

import structlog

from analysis.factor_ensemble import EnsembleResult
from analysis.match_predictor import MatchPredictor
from config.settings import settings
from data_sources.orchestrator import DataSourceOrchestrator
from factors.base import FactorContext
from factors.registry import get_active_factors
from wm2026 import edge as edge_mod
from wm2026.context import apply_runtime_profile, build_context

log = structlog.get_logger("wm2026.pipeline")


def _team(cfg: dict[str, Any], side: str) -> dict[str, Any]:
    return (cfg.get("teams", {}) or {}).get(side, {}) or {}


def _base_xg(cfg: dict[str, Any]) -> tuple[float, float]:
    """Base attack/defence xG blend — identical to services.match_service.

        base_home = (home.avg_xg_season + away.avg_xg_conceded) / 2
        base_away = (away.avg_xg_season + home.avg_xg_conceded) / 2
    """
    h, a = _team(cfg, "home"), _team(cfg, "away")
    h_xg = float(h.get("avg_xg_season", 1.40) or 1.40)
    a_xg = float(a.get("avg_xg_season", 1.30) or 1.30)
    h_xga = float(h.get("avg_xg_conceded", 1.30) or 1.30)
    a_xga = float(a.get("avg_xg_conceded", 1.40) or 1.40)
    return (h_xg + a_xga) / 2.0, (a_xg + h_xga) / 2.0


async def _populate(ctx: FactorContext) -> dict[str, Any]:
    """Phase 1 — fan-out external data. Never raises into the caller."""
    orch = DataSourceOrchestrator()
    try:
        await orch.populate(ctx)
    except Exception as exc:  # pragma: no cover - defensive
        log.warning("orchestrator_failed", error=str(exc))
    finally:
        await orch.aclose()
    return dict(ctx.provenance)


async def _signals(ctx: FactorContext) -> list:
    """Phase 2/3 — run every active factor concurrently → FactorSignals."""
    factors = get_active_factors(settings)
    signals = await asyncio.gather(
        *(f.compute(ctx) for f in factors), return_exceptions=True
    )
    out = []
    for f, s in zip(factors, signals):
        if isinstance(s, Exception):
            log.warning("factor_failed", name=getattr(f, "name", "?"), error=str(s))
            continue
        out.append(s)
    return out


def _lambda_ci(xg: float, sigma: float) -> dict[str, float]:
    """Normal-approx 90 % interval for λ from the bootstrap σ (relative).

    The bootstrap samples λ ~ N(xg, sigma·xg); its 5/50/95 percentiles are
    ``xg·(1 ± 1.645·sigma)``. Cheaper than a second bootstrap and identical in
    distribution. Floored at 0.05 so a CI never goes non-physical.
    """
    z = 1.645
    return {
        "p5": round(max(0.05, xg * (1.0 - z * sigma)), 3),
        "p50": round(xg, 3),
        "p95": round(max(0.05, xg * (1.0 + z * sigma)), 3),
    }


def _maybe_calibrate(out: Any) -> dict[str, Any]:
    """Phase 5 — best-effort isotonic/Platt calibration of the 1X2 line.

    Returns ``{"applied": bool, "note": str, "calibrated": {...}|None}``. When
    no fitted artifact exists (the default for a fresh clone), ``applied`` is
    False and the report falls back to the raw, bootstrap-bounded probabilities.
    """
    raw = {
        "home_win": out.home_win_prob,
        "draw": out.draw_prob,
        "away_win": out.away_win_prob,
    }
    try:
        from analysis import calibration as calib

        iso = calib.load_isotonic()
        platt = calib.load_platt()
        artifact = iso or platt
        calibrated = calib.apply(
            artifact, raw["home_win"], raw["draw"], raw["away_win"]
        )
        if calibrated is None:
            raise FileNotFoundError("no usable calibration artifact")
        return {
            "applied": True,
            "method": "isotonic" if iso is not None else "platt",
            "note": "Calibrated against the fitted historical artifact.",
            "calibrated": {
                "home_win": round(calibrated["home"], 4),
                "draw": round(calibrated["draw"], 4),
                "away_win": round(calibrated["away"], 4),
            },
        }
    except Exception:
        return {
            "applied": False,
            "method": None,
            "note": (
                "No fitted calibration artifact (no WC-2026 history yet). "
                "Raw model probabilities are reported; fit isotonic/Platt on "
                "WC 2022 + EURO 2024 + Copa 2024 as a prior set, noting the "
                "transfer. See analysis/calibration.py."
            ),
            "calibrated": None,
        }


def _validate(
    out: Any, ensemble: EnsembleResult, signals: list, provenance: dict[str, Any]
) -> list[str]:
    """Phase 7 — sanity self-check. Returns human-readable warnings (never
    raises). Mirrors the master prompt's ``/data:validate-data`` checklist."""
    warnings: list[str] = []
    lam_h, lam_a = out.home_xg, out.away_xg
    if not (0.3 <= lam_h <= 4.0) or not (0.3 <= lam_a <= 4.0):
        warnings.append(
            f"λ out of sane range [0.3, 4.0]: home={lam_h:.2f} away={lam_a:.2f}"
        )
    p_sum = out.home_win_prob + out.draw_prob + out.away_win_prob
    if abs(p_sum - 1.0) > 0.005:
        warnings.append(f"1X2 probabilities sum to {p_sum:.4f} (expected 1.000 ± 0.005)")
    n_avail = sum(1 for s in signals if s.available)
    if n_avail < 5:
        warnings.append(f"only {n_avail} factors available (low coverage)")
    modes = {p.get("mode") for p in provenance.values() if isinstance(p, dict)}
    live_or_cache = {"live", "cache"} & modes
    if not live_or_cache:
        warnings.append("all data sources are mock — predictions are illustrative, not live")
    if ensemble.confidence < 0.5:
        warnings.append(
            f"ensemble confidence {ensemble.confidence:.2f} < 0.50 — treat the pick as low-conviction"
        )
    return warnings


async def run_prediction(
    cfg: dict[str, Any],
    *,
    mode: str = "mock",
    bootstrap_n: int | None = None,
    sentiment_payload: dict[str, Any] | None = None,
    odds_1x2: list[float] | None = None,
    odds_ou25: list[float] | None = None,
    odds_btts: list[float] | None = None,
) -> dict[str, Any]:
    """Run all phases for one match config and return the raw ``result`` dict.

    Parameters
    ----------
    cfg
        A parsed match config (see ``wm2026.context.load_match_config`` /
        ``synth_config``).
    mode
        ``"mock"`` (offline, default) or ``"live"`` (uses ``.env`` toggles).
    bootstrap_n
        Override the bootstrap sample count (default: ``settings.bootstrap_n``).
    sentiment_payload
        Optional pre-computed sentiment dict (keys: ``sample_size``,
        ``home_sentiment``, ``away_sentiment``, ``home_momentum`` …). When None
        the sentiment + momentum factors neutralise and the ensemble
        re-normalises.
    odds_1x2 / odds_ou25 / odds_btts
        Decimal odds for the Phase-6 edge table. ``odds_1x2`` also seeds the
        market factor when the config didn't already carry odds.
    """
    started = datetime.now(timezone.utc)
    apply_runtime_profile(mode)

    ctx = build_context(cfg)
    if sentiment_payload:
        ctx.sentiment_payload = sentiment_payload
    if odds_1x2 and ctx.market_implied is None:
        fair, _ = edge_mod.devig(odds_1x2[:3])
        if len(fair) >= 3:
            ctx.market_implied = (fair[0], fair[1], fair[2])

    # Phase 1 — data collection.
    provenance = await _populate(ctx)

    # Phase 2/3 — factor decomposition (+ injected sentiment).
    signals = await _signals(ctx)

    # Phase 4 — goal-model stack + bootstrap CIs.
    boot = settings.bootstrap_n if bootstrap_n is None else int(bootstrap_n)
    base_home_xg, base_away_xg = _base_xg(cfg)
    predictor = MatchPredictor(
        rho=0.1,
        goal_model=settings.goal_model,
        negbin_size=settings.negbin_size,
        combine=settings.goal_model_combine,
        bootstrap_n=boot,
        bootstrap_xg_sigma=settings.bootstrap_xg_sigma,
    )
    # market_prior stays None: when odds are present the MarketOddsFactor
    # already tilts λ, so a second 1X2 blend would double-count (match_service
    # drops it for exactly this reason).
    out, ensemble = predictor.predict_from_signals(
        signals, base_home_xg=base_home_xg, base_away_xg=base_away_xg,
        market_prior=None,
    )

    # Score-probability matrix (primary model at the final λ) for the heatmap.
    try:
        matrix = predictor.poisson.predict_matrix(out.home_xg, out.away_xg)
        score_matrix = [[float(matrix[i][j]) for j in range(matrix.shape[1])]
                        for i in range(matrix.shape[0])]
    except Exception:  # pragma: no cover - defensive
        score_matrix = []

    # Phase 5 — calibration. Graceful: only transforms when a historical artifact
    # has been fitted (scripts/… → models_ml/artifacts/calibration_*.json). With
    # no WC-2026 history yet we report raw probabilities + a transfer caveat.
    calibration = _maybe_calibrate(out)

    # Phase 6 — market edge / value detection.
    blended = {
        "home_win": out.home_win_prob,
        "draw": out.draw_prob,
        "away_win": out.away_win_prob,
        "over_25": out.over_25,
        "btts": out.btts,
    }
    edge_rows = edge_mod.compute_edges(
        blended, odds_1x2=odds_1x2, odds_ou25=odds_ou25, odds_btts=odds_btts,
    )
    best_value = edge_mod.best_value_pick(edge_rows)

    # Phase 7 — validation.
    warnings = _validate(out, ensemble, signals, provenance)

    return {
        "config": cfg,
        "started_at": started,
        "mode": mode,
        "base_home_xg": base_home_xg,
        "base_away_xg": base_away_xg,
        "lambda_home_ci": _lambda_ci(out.home_xg, settings.bootstrap_xg_sigma),
        "lambda_away_ci": _lambda_ci(out.away_xg, settings.bootstrap_xg_sigma),
        "prediction": out,
        "ensemble": ensemble,
        "signals": signals,
        "score_matrix": score_matrix,
        "calibration": calibration,
        "provenance": provenance,
        "edges": edge_rows,
        "best_value": best_value,
        "warnings": warnings,
        "bootstrap_n": boot,
    }


__all__ = ["run_prediction"]
