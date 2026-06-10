"""Phase 8 — Output. Turn the raw ``result`` dict into a structured JSON object
and a human-readable Markdown report.

``build_report(result)`` returns ``{"json": <dict>, "markdown": <str>}``:

* **json**     — copy-paste-able, DB-ready, follows the master prompt's schema.
* **markdown** — executive summary, factor tornado, score heatmap, edge table.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from wm2026 import MODEL_VERSION


# ── small formatting helpers ──────────────────────────────────────────────────
def _pct(p: float | None) -> str:
    return "—" if p is None else f"{100.0 * p:5.1f}%"


def _iso(dt: Any) -> str:
    if isinstance(dt, datetime):
        return dt.isoformat()
    return str(dt)


def _score_label(item: dict[str, Any]) -> str:
    return f"{int(item.get('home', 0))}-{int(item.get('away', 0))}"


def _confidence_gauge(conf: float, warnings: list[str]) -> str:
    if any("mock" in w for w in warnings):
        return "🟡 (mock data — illustrative)"
    if conf >= 0.66:
        return "🟢 high"
    if conf >= 0.5:
        return "🟡 medium"
    return "🔴 low"


# ── JSON assembly (Phase 8A) ──────────────────────────────────────────────────
def build_json(result: dict[str, Any]) -> dict[str, Any]:
    out = result["prediction"]
    ensemble = result["ensemble"]
    cfg = result.get("config", {})
    match = cfg.get("match", {})
    teams = cfg.get("teams", {})
    feats = out.features or {}

    signals_payload = []
    eff = {
        s["name"]: s.get("effective_weight", 0.0)
        for s in ensemble.breakdown_payload.get("signals", [])
    }
    for s in result["signals"]:
        signals_payload.append({
            "name": s.name,
            "home_strength": round(s.home_strength, 4),
            "away_strength": round(s.away_strength, 4),
            "weight": round(s.weight, 4),
            "effective_weight": round(eff.get(s.name, 0.0), 4),
            "confidence": round(s.confidence, 3),
            "available": s.available,
            "kind": s.kind,
            "source": s.source,
        })

    n_used = sum(1 for s in result["signals"] if s.available)

    over = {
        "over_05": round(out.features.get("per_model", {})
                   .get(feats.get("goal_model_primary", "poisson"), {})
                   .get("over_05", 0.0), 4) if feats.get("per_model") else None,
        "over_15": round(out.over_15, 4),
        "over_25": round(out.over_25, 4),
        "over_35": round(out.over_35, 4),
    }

    top5 = [
        {"score": _score_label(t), "p": round(float(t.get("probability", 0.0)), 4)}
        for t in (out.top_scores or [])
    ]

    return {
        "schema_version": "1.0",
        "match_id": match.get("id") or out.__dict__.get("match_id", "wm2026_match"),
        "model_version": MODEL_VERSION,
        "predicted_at": _iso(result.get("started_at")),
        "mode": result.get("mode", "mock"),
        "fixture": {
            "home": (teams.get("home", {}) or {}).get("name"),
            "away": (teams.get("away", {}) or {}).get("name"),
            "stage": match.get("phase") or match.get("stage"),
            "kickoff_utc": match.get("kickoff_utc"),
            "venue": match.get("venue"),
        },
        "lambda_home": result["lambda_home_ci"],
        "lambda_away": result["lambda_away_ci"],
        "xg": {"home": round(out.home_xg, 3), "away": round(out.away_xg, 3)},
        "markets": {
            "1x2": {
                "home": round(out.home_win_prob, 4),
                "draw": round(out.draw_prob, 4),
                "away": round(out.away_win_prob, 4),
            },
            "over_under": over,
            "btts": {"yes": round(out.btts, 4), "no": round(1.0 - out.btts, 4)},
            "correct_score_top5": top5,
            "recommended_bet": out.recommended_bet,
            "bet_probability": (round(out.bet_probability, 4)
                                if out.bet_probability is not None else None),
        },
        "per_model": _round_per_model(feats.get("per_model", {})),
        "confidence_intervals": feats.get("confidence_intervals", {}),
        "ensemble_confidence": round(ensemble.confidence, 4),
        "factors_used": n_used,
        "factors_total": len(result["signals"]),
        "factors": signals_payload,
        "calibration": result.get("calibration", {}),
        "edge_table": result.get("edges", []),
        "best_value": result.get("best_value"),
        "warnings": result.get("warnings", []),
        "data_sources": result.get("provenance", {}),
    }


def _round_per_model(per_model: dict[str, Any]) -> dict[str, Any]:
    """Drop the bulky top_scores arrays; keep the scalar markets per model."""
    out: dict[str, Any] = {}
    for name, mk in (per_model or {}).items():
        out[name] = {
            k: round(v, 4) for k, v in mk.items()
            if isinstance(v, (int, float))
        }
    return out


# ── Markdown assembly (Phase 8B-E) ────────────────────────────────────────────
def build_markdown(result: dict[str, Any], js: dict[str, Any]) -> str:
    out = result["prediction"]
    ensemble = result["ensemble"]
    fx = js["fixture"]
    L: list[str] = []

    home = fx.get("home") or "Home"
    away = fx.get("away") or "Away"
    L.append(f"# 🏆 WM 2026 — {home} vs {away}")
    L.append("")
    meta = " · ".join(
        str(x) for x in [fx.get("stage"), fx.get("kickoff_utc"), fx.get("venue")] if x
    )
    if meta:
        L.append(f"*{meta}*")
    L.append(f"*Mode: `{js['mode']}` · model `{js['model_version']}` · "
             f"predicted {js['predicted_at']}*")
    L.append("")

    # B) Executive summary -----------------------------------------------------
    L.append("## Executive Summary")
    p1x2 = js["markets"]["1x2"]
    fav = max([("home", p1x2["home"]), ("draw", p1x2["draw"]), ("away", p1x2["away"])],
              key=lambda t: t[1])
    fav_label = {"home": home, "draw": "Draw", "away": away}[fav[0]]
    L.append(f"- **Most likely 1X2:** {fav_label} ({_pct(fav[1])})  ·  "
             f"{home} {_pct(p1x2['home'])} / Draw {_pct(p1x2['draw'])} / {away} {_pct(p1x2['away'])}")
    L.append(f"- **Expected goals (λ):** {home} {out.home_xg:.2f} — {away} {out.away_xg:.2f}  ·  "
             f"O2.5 {_pct(out.over_25)} · BTTS {_pct(out.btts)}")
    top3 = _top_factors(result["signals"], ensemble, 3)
    if top3:
        L.append("- **Top-3 driving factors:** " + "; ".join(top3))
    bv = js.get("best_value")
    if bv:
        L.append(f"- **Value pick:** {bv['market']} — {bv['selection']} "
                 f"@ {bv['decimal_odd']} → edge **{bv['edge_pct']}%**, "
                 f"half-Kelly {bv['half_kelly_pct']}% ({bv['action']})")
    else:
        L.append("- **Value pick:** none (no odds supplied or edge < 2%)")
    L.append(f"- **Confidence:** {_confidence_gauge(ensemble.confidence, result['warnings'])} "
             f"(ensemble {ensemble.confidence:.2f}, {js['factors_used']}/{js['factors_total']} factors live)")
    if not js["calibration"].get("applied"):
        L.append("- **Calibration:** raw probabilities (no historical artifact — see note in JSON)")
    L.append("")

    if result["warnings"]:
        L.append("## ⚠️ Validation warnings")
        for w in result["warnings"]:
            L.append(f"- {w}")
        L.append("")

    # C) Factor tornado --------------------------------------------------------
    L.append("## Factor Tornado (home ◀ favour ▶ away)")
    L.append("```")
    L.extend(_tornado(result["signals"], ensemble))
    L.append("```")
    L.append("")

    # D) Score heatmap ---------------------------------------------------------
    matrix = result.get("score_matrix") or []
    if matrix:
        L.append(f"## Score Probability Matrix (rows = {home}, cols = {away})")
        L.append("```")
        L.extend(_heatmap(matrix, home, away))
        L.append("```")
        L.append("")
    if js["markets"]["correct_score_top5"]:
        tops = "  ".join(f"{t['score']} ({_pct(t['p'])})"
                         for t in js["markets"]["correct_score_top5"])
        L.append(f"**Top-5 correct scores:** {tops}")
        L.append("")

    # E) Edge table ------------------------------------------------------------
    L.append("## Edge Table (Phase 6)")
    L.append("| Market | Selection | Model P | Fair P | Odd | Edge % | ½-Kelly % | Action |")
    L.append("|---|---|---|---|---|---|---|---|")
    for r in js["edge_table"]:
        L.append(
            f"| {r['market']} | {r['selection']} | {_pct(r['model_p'])} | "
            f"{_pct(r['fair_p'])} | {r['decimal_odd'] if r['decimal_odd'] is not None else '—'} | "
            f"{r['edge_pct'] if r['edge_pct'] is not None else '—'} | "
            f"{r['half_kelly_pct'] if r['half_kelly_pct'] is not None else '—'} | {r['action']} |"
        )
    L.append("")

    # Per-model + data provenance ---------------------------------------------
    L.append("## Goal-model blend")
    pm = js.get("per_model", {})
    if pm:
        L.append("| Model | Home | Draw | Away | O2.5 | BTTS |")
        L.append("|---|---|---|---|---|---|")
        for name, mk in pm.items():
            L.append(f"| {name} | {_pct(mk.get('home_win'))} | {_pct(mk.get('draw'))} | "
                     f"{_pct(mk.get('away_win'))} | {_pct(mk.get('over_25'))} | {_pct(mk.get('btts'))} |")
        L.append("")
    L.append("## Data sources (provenance)")
    prov = js.get("data_sources", {})
    if prov:
        modes: dict[str, int] = {}
        for p in prov.values():
            if isinstance(p, dict):
                modes[p.get("mode", "?")] = modes.get(p.get("mode", "?"), 0) + 1
        L.append("- Mode counts: " + ", ".join(f"`{m}`×{n}" for m, n in sorted(modes.items())))
    L.append("")
    L.append("---")
    L.append("*Generated by the WM 2026 workflow — not betting advice. "
             "Mock mode is illustrative; use `--mode live` with API keys for real data.*")
    return "\n".join(L)


def _top_factors(signals: list, ensemble: Any, k: int) -> list[str]:
    """The k factors with the largest weighted home/away divergence."""
    eff = {s["name"]: s.get("effective_weight", 0.0)
           for s in ensemble.breakdown_payload.get("signals", [])}
    scored = []
    for s in signals:
        if not s.available or s.kind == "global":
            continue
        impact = eff.get(s.name, 0.0) * abs(s.home_strength - s.away_strength)
        if impact <= 1e-9:
            continue
        lean = "home" if s.home_strength >= s.away_strength else "away"
        scored.append((impact, f"{s.name} → {lean}"))
    scored.sort(reverse=True)
    return [label for _, label in scored[:k]]


def _tornado(signals: list, ensemble: Any) -> list[str]:
    eff = {s["name"]: s.get("effective_weight", 0.0)
           for s in ensemble.breakdown_payload.get("signals", [])}
    rows = []
    for s in signals:
        impact = eff.get(s.name, 0.0) * (s.home_strength - s.away_strength)
        rows.append((abs(impact), impact, s))
    rows.sort(key=lambda r: r[0], reverse=True)
    lines = []
    width = 18
    for _, impact, s in rows:
        if not s.available:
            bar = "·" * width + "|" + "·" * width
            lines.append(f"{s.name:18} {bar}  (n/a)")
            continue
        mag = max(-1.0, min(1.0, impact * 8.0))   # scale for visibility
        n = int(round(abs(mag) * width))
        if impact >= 0:                            # home favour → left
            bar = " " * (width - n) + "█" * n + "|" + " " * width
        else:                                      # away favour → right
            bar = " " * width + "|" + "█" * n + " " * (width - n)
        lines.append(f"{s.name:18} {bar}  {impact:+.3f}")
    lines.append(f"{'':18} {'home ':>18}<┘└>{' away':<18}")
    return lines


def _heatmap(matrix: list[list[float]], home: str, away: str) -> list[str]:
    n = min(7, len(matrix))
    blocks = " ░▒▓█"
    hi = max((matrix[i][j] for i in range(n) for j in range(n)), default=0.0) or 1.0
    lines = ["      " + "".join(f"{j:>5}" for j in range(n)) + f"   ({away} →)"]
    for i in range(n):
        cells = []
        for j in range(n):
            v = matrix[i][j]
            idx = min(len(blocks) - 1, int(v / hi * (len(blocks) - 1)))
            cells.append(f"{blocks[idx]}{100*v:4.1f}")
        lines.append(f"  {i:>2}  " + "".join(cells))
    lines.append(f"({home} ↓)")
    return lines


# ── public entry ──────────────────────────────────────────────────────────────
def build_report(result: dict[str, Any]) -> dict[str, Any]:
    js = build_json(result)
    md = build_markdown(result, js)
    return {"json": js, "markdown": md}


__all__ = ["build_report", "build_json", "build_markdown"]
