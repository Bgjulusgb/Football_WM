"""Phase 6 — Markt-Edge & Value-Detection (de-vigging, edge, Kelly).

Pure functions, zero heavy dependencies. Given a model probability and the
bookmaker's decimal odds, we compute:

* the bookmaker's *fair* (vig-free) probability,
* the model's value **edge** = ``p_model * odd - 1``,
* the **Kelly** stake fraction and the recommended ``half-Kelly`` stake band.

Nothing here touches the network — bookmaker odds come from the match config or
the ``--odds`` CLI flag, exactly the inputs the master prompt's ``match:`` block
provides.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any


# ── value bands (master prompt, Phase 6) ──────────────────────────────────────
#   edge < 2%      → no-bet
#   2% .. 5%       → small     (0.25 .. 0.5 % bankroll)
#   5% .. 10%      → standard  (0.5 .. 1.5 % bankroll)
#   > 10%          → flag for a sanity check first, then max 2 % bankroll
def stake_band(edge: float) -> str:
    if edge < 0.02:
        return "no-bet"
    if edge < 0.05:
        return "small"
    if edge < 0.10:
        return "standard"
    return "sanity-check"


@dataclass
class EdgeRow:
    """One market line evaluated against the book."""
    market: str
    selection: str
    model_p: float
    fair_p: float | None          # vig-free book probability (None if no odds)
    decimal_odd: float | None
    edge_pct: float | None        # (model_p * odd - 1) * 100
    kelly_pct: float | None       # full-Kelly stake as % of bankroll
    half_kelly_pct: float | None  # recommended (half-Kelly)
    action: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def parse_odds(spec: str | None) -> list[float] | None:
    """Parse a ``"2.10 / 3.40 / 3.20"`` style string into ``[2.10, 3.40, 3.20]``.

    Accepts ``/``, ``,`` or whitespace as separators. Returns ``None`` for an
    empty/placeholder spec so callers can treat "no odds given" uniformly.
    """
    if not spec:
        return None
    cleaned = spec.replace("/", " ").replace(",", " ")
    out: list[float] = []
    for tok in cleaned.split():
        try:
            val = float(tok)
        except ValueError:
            continue
        if val > 1.0:                       # decimal odds are always > 1.0
            out.append(val)
    return out or None


def devig(decimal_odds: list[float]) -> tuple[list[float], float]:
    """Remove the bookmaker's overround → (fair_probabilities, overround).

    ``overround`` (a.k.a. vig/juice) is ``sum(1/odd)`` and is > 1.0 for any
    book that makes money. Dividing the raw implied probabilities by it yields
    the vig-free estimate of the book's true probabilities.
    """
    implied = [1.0 / o for o in decimal_odds if o and o > 1.0]
    overround = sum(implied)
    if overround <= 0:
        return [], 0.0
    fair = [p / overround for p in implied]
    return fair, overround


def kelly_fraction(model_p: float, decimal_odd: float) -> float:
    """Full-Kelly stake fraction for a single bet. Clamped at 0 (no negative
    stakes — a negative Kelly just means "don't bet")."""
    b = decimal_odd - 1.0
    if b <= 0:
        return 0.0
    f = (model_p * decimal_odd - 1.0) / b
    return max(0.0, f)


def evaluate_line(
    market: str,
    selection: str,
    model_p: float,
    decimal_odd: float | None,
    fair_p: float | None = None,
) -> EdgeRow:
    """Build one :class:`EdgeRow`. ``decimal_odd=None`` ⇒ model-only row."""
    if decimal_odd is None or decimal_odd <= 1.0:
        return EdgeRow(
            market=market, selection=selection, model_p=round(model_p, 4),
            fair_p=round(fair_p, 4) if fair_p is not None else None,
            decimal_odd=None, edge_pct=None, kelly_pct=None,
            half_kelly_pct=None, action="—",
        )
    edge = model_p * decimal_odd - 1.0
    full_kelly = kelly_fraction(model_p, decimal_odd)
    band = stake_band(edge)
    return EdgeRow(
        market=market,
        selection=selection,
        model_p=round(model_p, 4),
        fair_p=round(fair_p, 4) if fair_p is not None else None,
        decimal_odd=round(decimal_odd, 3),
        edge_pct=round(edge * 100.0, 2),
        kelly_pct=round(full_kelly * 100.0, 2),
        half_kelly_pct=round(0.5 * full_kelly * 100.0, 2),
        action=band,
    )


def compute_edges(
    markets: dict[str, float],
    *,
    odds_1x2: list[float] | None = None,
    odds_ou25: list[float] | None = None,   # [over, under]
    odds_btts: list[float] | None = None,   # [yes, no]
) -> list[dict[str, Any]]:
    """Phase 6 — evaluate every market for which odds were supplied.

    ``markets`` is the blended model output (``home_win``/``draw``/``away_win``/
    ``over_25``/``btts`` …). Only lines with supplied odds yield an edge; the
    rest are still listed (model-only) so the report shows the full picture.
    """
    rows: list[EdgeRow] = []

    # 1X2 ---------------------------------------------------------------------
    fair_1x2: list[float] | None = None
    if odds_1x2 and len(odds_1x2) >= 3:
        fair_1x2, _ = devig(odds_1x2[:3])
    for i, (sel, key) in enumerate(
        [("Home", "home_win"), ("Draw", "draw"), ("Away", "away_win")]
    ):
        rows.append(evaluate_line(
            "1X2", sel, markets.get(key, 0.0),
            odds_1x2[i] if odds_1x2 and len(odds_1x2) > i else None,
            fair_1x2[i] if fair_1x2 and len(fair_1x2) > i else None,
        ))

    # Over/Under 2.5 ----------------------------------------------------------
    over = markets.get("over_25", 0.0)
    fair_ou: list[float] | None = None
    if odds_ou25 and len(odds_ou25) >= 2:
        fair_ou, _ = devig(odds_ou25[:2])
    rows.append(evaluate_line(
        "O/U 2.5", "Over 2.5", over,
        odds_ou25[0] if odds_ou25 else None,
        fair_ou[0] if fair_ou else None,
    ))
    rows.append(evaluate_line(
        "O/U 2.5", "Under 2.5", 1.0 - over,
        odds_ou25[1] if odds_ou25 and len(odds_ou25) > 1 else None,
        fair_ou[1] if fair_ou and len(fair_ou) > 1 else None,
    ))

    # BTTS --------------------------------------------------------------------
    btts = markets.get("btts", 0.0)
    fair_btts: list[float] | None = None
    if odds_btts and len(odds_btts) >= 2:
        fair_btts, _ = devig(odds_btts[:2])
    rows.append(evaluate_line(
        "BTTS", "Yes", btts,
        odds_btts[0] if odds_btts else None,
        fair_btts[0] if fair_btts else None,
    ))
    rows.append(evaluate_line(
        "BTTS", "No", 1.0 - btts,
        odds_btts[1] if odds_btts and len(odds_btts) > 1 else None,
        fair_btts[1] if fair_btts and len(fair_btts) > 1 else None,
    ))

    return [r.as_dict() for r in rows]


def best_value_pick(edge_rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Return the highest-edge actionable row (edge ≥ 2 %), or ``None``."""
    actionable = [
        r for r in edge_rows
        if r.get("edge_pct") is not None and r["edge_pct"] >= 2.0
    ]
    if not actionable:
        return None
    return max(actionable, key=lambda r: r["edge_pct"])


__all__ = [
    "EdgeRow", "parse_odds", "devig", "kelly_fraction",
    "evaluate_line", "compute_edges", "best_value_pick", "stake_band",
]
