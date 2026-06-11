"""Phase-1 math upgrade — derived betting markets from a score-probability matrix.

Every function here is a **pure** function over the score matrix ``M`` where
``M[i][j] = P(home scores i, away scores j)``. That matrix is exactly what
:meth:`models_ml.poisson_goals.DixonColesPoisson.predict_matrix` returns (already
normalised to sum 1) and what :mod:`wm2026.pipeline` surfaces as
``result["score_matrix"]``. No new dependencies — ``numpy`` is already core, and
every entry point also accepts a plain nested list.

Markets implemented
--------------------
* **Double Chance**     ``1X`` / ``12`` / ``X2``
* **Draw No Bet**       home / away, the draw voids (stake back → renormalised)
* **Asian Handicap**    any line incl. **quarter lines** (±0.25, ±0.75 …) with the
                        standard half-win / half-push settlement
* **Total Over/Under**  any line incl. quarter lines (e.g. 2.75)
* **Team Totals**       home / away over-under a line
* **Clean Sheet**       home / away keeps a clean sheet (opponent scores 0)
* **Win To Nil**        home / away wins *and* concedes 0
* **Odd/Even**          parity of the total goals

Asian-handicap / quarter-line settlement
-----------------------------------------
Backing the *favoured* side (home for AH, "over" for totals) at a line, with a
unit stake, the adjusted margin ``adj`` decides which fraction of the stake
**wins** (returns the decimal odd), **pushes** (returns the stake) or **loses**::

    adj >=  0.5   -> win  1.0
    adj ==  0.25  -> win  0.5, push 0.5     (quarter line: half on the win leg,
    adj ==  0.0   -> push 1.0                half on the integer push leg)
    adj == -0.25  -> push 0.5, loss 0.5
    adj <= -0.5   -> loss 1.0

For Asian handicap ``adj = (home - away) + line``; for totals ``adj = total - line``.
``home_win`` below is the *expected win share* (so quarter lines contribute half
their mass) — that keeps the EV identity exact::

    EV(back @ odd o) = home_win * o + push - 1

while ``*_prob_nopush`` rescales the win share onto the same [0, 1] axis as 1X2
(``win / (win + loss)``) for a probability-style display column.
"""
from __future__ import annotations

from typing import Any, Sequence

import numpy as np

_EPS = 1e-9


def _as_array(matrix: Any) -> np.ndarray:
    """Coerce a numpy array / nested list into a square ``float`` matrix."""
    arr = np.asarray(matrix, dtype=float)
    if arr.ndim != 2 or arr.shape[0] != arr.shape[1]:
        raise ValueError(f"score matrix must be square 2-D, got shape {arr.shape}")
    return arr


def _settle(adj: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Vectorised win/push fractions for the *favoured* side at adjusted margin
    ``adj`` (see the module docstring for the settlement table)."""
    win = np.where(adj >= 0.5 - _EPS, 1.0, 0.0)
    win = win + np.where(np.abs(adj - 0.25) < _EPS, 0.5, 0.0)
    push = np.where(np.abs(adj) < _EPS, 1.0, 0.0)
    push = push + np.where(np.abs(adj - 0.25) < _EPS, 0.5, 0.0)
    push = push + np.where(np.abs(adj + 0.25) < _EPS, 0.5, 0.0)
    return win, push


def _margins(n: int) -> np.ndarray:
    """``margins[i, j] = i - j`` for an ``n × n`` matrix."""
    rows, cols = np.indices((n, n))
    return rows - cols


def _totals(n: int) -> np.ndarray:
    """``totals[i, j] = i + j`` for an ``n × n`` matrix."""
    rows, cols = np.indices((n, n))
    return rows + cols


# ── 1X2 + simple combinations ─────────────────────────────────────────────────
def one_x_two(matrix: Any) -> dict[str, float]:
    """Recover ``(home, draw, away)`` straight from the matrix (lower-triangle =
    home win, diagonal = draw, upper-triangle = away win)."""
    M = _as_array(matrix)
    home = float(np.tril(M, -1).sum())
    draw = float(np.trace(M))
    away = float(np.triu(M, 1).sum())
    return {"home": home, "draw": draw, "away": away}


def double_chance(home: float, draw: float, away: float) -> dict[str, float]:
    """Double-chance probabilities: ``1X`` (home or draw), ``12`` (no draw),
    ``X2`` (draw or away)."""
    return {
        "1X": float(home + draw),
        "12": float(home + away),
        "X2": float(draw + away),
    }


def draw_no_bet(home: float, draw: float, away: float) -> dict[str, float]:
    """Draw-No-Bet: the draw voids (stake returned), so the home/away win
    probabilities are renormalised over the no-draw mass."""
    denom = home + away
    if denom <= _EPS:
        return {"home": 0.0, "away": 0.0}
    return {"home": float(home / denom), "away": float(away / denom)}


# ── Asian handicap + totals (quarter-line aware) ──────────────────────────────
def asian_handicap(matrix: Any, line: float) -> dict[str, float]:
    """Asian handicap on the **home** side at ``line`` (e.g. ``-0.5``, ``-0.75``,
    ``+1.0``). Quarter lines split into half-win/half-push per the settlement
    table. Returns expected win/push/loss shares plus the no-push display probs.
    """
    M = _as_array(matrix)
    adj = _margins(M.shape[0]).astype(float) + float(line)
    win, push = _settle(adj)
    p_win = float((M * win).sum())
    p_push = float((M * push).sum())
    p_loss = max(0.0, 1.0 - p_win - p_push)
    denom = p_win + p_loss
    home_np = p_win / denom if denom > _EPS else 0.0
    return {
        "line": float(line),
        "home_win": p_win,
        "push": p_push,
        "away_win": p_loss,
        "home_prob_nopush": float(home_np),
        "away_prob_nopush": float(1.0 - home_np) if denom > _EPS else 0.0,
    }


def total_over_under(matrix: Any, line: float) -> dict[str, float]:
    """Over/Under on total goals at ``line`` (quarter lines supported). The
    "over" side is the favoured side in the settlement table."""
    M = _as_array(matrix)
    adj = _totals(M.shape[0]).astype(float) - float(line)
    over, push = _settle(adj)
    p_over = float((M * over).sum())
    p_push = float((M * push).sum())
    p_under = max(0.0, 1.0 - p_over - p_push)
    denom = p_over + p_under
    over_np = p_over / denom if denom > _EPS else 0.0
    return {
        "line": float(line),
        "over": p_over,
        "push": p_push,
        "under": p_under,
        "over_prob_nopush": float(over_np),
        "under_prob_nopush": float(1.0 - over_np) if denom > _EPS else 0.0,
    }


def team_total(matrix: Any, side: str, line: float) -> dict[str, float]:
    """Over/Under on a single team's goals. ``side ∈ {"home", "away"}``."""
    M = _as_array(matrix)
    if side == "home":
        marginal = M.sum(axis=1)            # sum over the away axis
    elif side == "away":
        marginal = M.sum(axis=0)            # sum over the home axis
    else:
        raise ValueError("side must be 'home' or 'away'")
    counts = np.arange(M.shape[0], dtype=float)
    adj = counts - float(line)
    over, push = _settle(adj)
    p_over = float((marginal * over).sum())
    p_push = float((marginal * push).sum())
    p_under = max(0.0, 1.0 - p_over - p_push)
    return {"side": side, "line": float(line), "over": p_over,
            "push": p_push, "under": p_under}


# ── Clean sheet / win-to-nil / parity ─────────────────────────────────────────
def clean_sheet(matrix: Any) -> dict[str, float]:
    """Probability each side keeps a clean sheet (the opponent scores 0)."""
    M = _as_array(matrix)
    return {
        "home": float(M[:, 0].sum()),       # away scores 0
        "away": float(M[0, :].sum()),       # home scores 0
    }


def win_to_nil(matrix: Any) -> dict[str, float]:
    """Probability each side wins *and* concedes zero."""
    M = _as_array(matrix)
    return {
        "home": float(M[1:, 0].sum()),      # home ≥ 1, away 0
        "away": float(M[0, 1:].sum()),      # away ≥ 1, home 0
    }


def odd_even_goals(matrix: Any) -> dict[str, float]:
    """Parity of the total goals (0 counts as even)."""
    M = _as_array(matrix)
    parity = _totals(M.shape[0]) % 2
    odd = float((M * (parity == 1)).sum())
    even = float((M * (parity == 0)).sum())
    return {"odd": odd, "even": even}


# ── convenience aggregator (used by the pipeline / report) ────────────────────
def derive_all(
    matrix: Any,
    p1x2: tuple[float, float, float] | dict[str, float] | None = None,
    *,
    ah_lines: Sequence[float] | None = None,
    total_lines: Sequence[float] | None = None,
) -> dict[str, Any]:
    """Compute every derived market in one pass.

    ``p1x2`` (the possibly market-blended 1X2 triple) seeds Double Chance / DNB
    so they stay consistent with the headline 1X2 line; when omitted it's read
    off the matrix. ``ah_lines`` / ``total_lines`` default to a sensible spread
    of main + quarter lines.
    """
    M = _as_array(matrix)
    if p1x2 is None:
        base = one_x_two(M)
        home, draw, away = base["home"], base["draw"], base["away"]
    elif isinstance(p1x2, dict):
        home = float(p1x2.get("home", 0.0))
        draw = float(p1x2.get("draw", 0.0))
        away = float(p1x2.get("away", 0.0))
    else:
        home, draw, away = (float(x) for x in p1x2)

    if ah_lines is None:
        ah_lines = (-2.0, -1.5, -1.0, -0.75, -0.5, -0.25, 0.0,
                    0.25, 0.5, 0.75, 1.0, 1.5, 2.0)
    if total_lines is None:
        total_lines = (0.5, 1.5, 2.5, 3.5, 4.5)

    return {
        "double_chance": double_chance(home, draw, away),
        "draw_no_bet": draw_no_bet(home, draw, away),
        "asian_handicap": [asian_handicap(M, ln) for ln in ah_lines],
        "totals": [total_over_under(M, ln) for ln in total_lines],
        "team_total_home": [team_total(M, "home", ln) for ln in (0.5, 1.5, 2.5)],
        "team_total_away": [team_total(M, "away", ln) for ln in (0.5, 1.5, 2.5)],
        "clean_sheet": clean_sheet(M),
        "win_to_nil": win_to_nil(M),
        "odd_even": odd_even_goals(M),
    }


__all__ = [
    "one_x_two",
    "double_chance",
    "draw_no_bet",
    "asian_handicap",
    "total_over_under",
    "team_total",
    "clean_sheet",
    "win_to_nil",
    "odd_even_goals",
    "derive_all",
]
