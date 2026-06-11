from typing import Any, Dict, List, Tuple

import numpy as np
from scipy.stats import nbinom, poisson


class DixonColesPoisson:
    """Dixon & Coles (1997) correction over independent Poisson goal counts.

    With ρ > 0, down-weights 0-0 and 1-1 (low-scoring draws are rarer than the
    independence assumption predicts) and up-weights 1-0/0-1 (narrow wins).
    Scores above (1,1) are left at the plain Poisson product.
    """

    def __init__(self, rho: float = 0.1, max_goals: int = 6) -> None:
        self.rho = rho
        self.max_goals = max_goals

    def _pmf(self, k: int, mu: float) -> float:
        """Marginal goal pmf for one side. Overridden by the negative-binomial
        model; Poisson is the Dixon-Coles default."""
        return float(poisson.pmf(k, mu))

    def predict_matrix(self, home_xg: float, away_xg: float) -> np.ndarray:
        n = self.max_goals + 1
        matrix = np.zeros((n, n))
        for i in range(n):
            for j in range(n):
                p = self._pmf(i, home_xg) * self._pmf(j, away_xg)
                p *= self._correction(i, j, home_xg, away_xg)
                matrix[i][j] = max(p, 0.0)
        total = matrix.sum()
        return matrix / total if total > 0 else matrix

    def _correction(self, h: int, a: int, mu: float, lam: float) -> float:
        rho = self.rho
        if h == 0 and a == 0:
            return 1 - mu * lam * rho
        if h == 0 and a == 1:
            return 1 + mu * rho
        if h == 1 and a == 0:
            return 1 + lam * rho
        if h == 1 and a == 1:
            return 1 - rho
        return 1.0

    def markets(self, matrix: np.ndarray) -> Dict[str, float | List[Dict]]:
        n = matrix.shape[0]
        home_win = float(np.sum(np.tril(matrix, -1)))
        draw = float(np.trace(matrix))
        away_win = float(np.sum(np.triu(matrix, 1)))

        def goals_over(threshold: float) -> float:
            return float(
                sum(matrix[i][j] for i in range(n) for j in range(n) if i + j > threshold)
            )

        btts = float(sum(matrix[i][j] for i in range(1, n) for j in range(1, n)))

        flat = [(float(matrix[i][j]), i, j) for i in range(n) for j in range(n)]
        flat.sort(reverse=True)
        top_scores = [
            {"home": h, "away": a, "probability": p} for p, h, a in flat[:5]
        ]

        return {
            "home_win": home_win,
            "draw": draw,
            "away_win": away_win,
            "over_05": goals_over(0.5),
            "over_15": goals_over(1.5),
            "over_25": goals_over(2.5),
            "over_35": goals_over(3.5),
            "btts": btts,
            "top_scores": top_scores,
        }


class NegativeBinomialDixonColes(DixonColesPoisson):
    """Dixon-Coles over negative-binomial marginals instead of Poisson.

    Football goal counts are mildly over-dispersed (variance > mean): blowouts
    and 0-0s both occur more than a Poisson with the same mean predicts. The
    NB marginal adds a dispersion parameter `size` (r); as r → ∞ it converges
    back to Poisson. Mean is fixed to the supplied xG (μ) via p = r / (r + μ),
    so swapping the model keeps the expected scoreline while widening the tails.
    (Karlis & Ntzoufras 2003 discuss dispersion in football scorelines.)
    """

    def __init__(self, rho: float = 0.1, max_goals: int = 6, size: float = 8.0) -> None:
        super().__init__(rho=rho, max_goals=max_goals)
        # Guard: a tiny size makes the distribution wildly over-dispersed.
        self.size = max(1.0, float(size))

    def _pmf(self, k: int, mu: float) -> float:
        mu = max(1e-6, mu)
        r = self.size
        p = r / (r + mu)
        return float(nbinom.pmf(k, r, p))


def build_goal_model(model: str = "poisson", *, rho: float = 0.1, max_goals: int = 6,
                     negbin_size: float = 8.0) -> DixonColesPoisson:
    """Factory used by MatchPredictor. `model` is "poisson" (default), "negbin"
    or "glm_poisson"; anything else falls back to Poisson so a bad config never
    breaks a prediction.

    GLM-Variante: weniger Dixon-Coles-Korrektur (rho/2), weil der trainierte
    GLM bereits Heimvorteil + Team-Festeffekte modelliert. Praktischer Effekt
    auf gegebenes (home_xg, away_xg): leicht andere Low-Score-Gewichtung als
    die plain Poisson-Variante — so produziert das Modell-Ensemble bei
    gleichen Lambdas drei distinkte Vorhersagen.
    """
    m = (model or "poisson").lower()
    if m in ("negbin", "negative_binomial", "nb"):
        return NegativeBinomialDixonColes(rho=rho, max_goals=max_goals, size=negbin_size)
    if m in ("glm_poisson", "glm"):
        return DixonColesPoisson(rho=rho * 0.5, max_goals=max_goals)
    return DixonColesPoisson(rho=rho, max_goals=max_goals)


# ── Multi-Model Ensemble + Bootstrap ──────────────────────────────────────────

MODEL_NAMES: Tuple[str, ...] = ("poisson", "negbin", "glm_poisson")

DEFAULT_BLEND_WEIGHTS: Dict[str, float] = {
    "poisson": 0.40,
    "negbin": 0.30,
    "glm_poisson": 0.30,
}


def build_all_goal_models(*, rho: float = 0.1, max_goals: int = 6,
                          negbin_size: float = 8.0) -> Dict[str, DixonColesPoisson]:
    """Drei Modelle parallel: poisson, negbin, glm_poisson. Wird vom
    MatchPredictor genutzt, um pro Match alle drei Vorhersagen zu liefern."""
    return {
        name: build_goal_model(name, rho=rho, max_goals=max_goals, negbin_size=negbin_size)
        for name in MODEL_NAMES
    }


def _scalar(markets: Dict[str, Any], key: str) -> float:
    v = markets.get(key, 0.0)
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def blend_markets(
    per_model: Dict[str, Dict[str, Any]],
    weights: Dict[str, float] | None = None,
) -> Dict[str, Any]:
    """Gewichtetes Mittel der skalaren Markets über alle Modelle.

    top_scores werden nicht gemittelt — wir nehmen die des am hoechsten
    gewichteten Modells als Repraesentation, damit Score-Verteilungen
    konsistent bleiben.
    """
    weights = weights or DEFAULT_BLEND_WEIGHTS
    total_w = sum(weights.get(m, 0.0) for m in per_model)
    if total_w <= 0:
        total_w = 1.0
    out: Dict[str, Any] = {}
    scalar_keys = ["home_win", "draw", "away_win", "over_05", "over_15",
                   "over_25", "over_35", "btts"]
    for key in scalar_keys:
        out[key] = sum(
            _scalar(per_model[m], key) * weights.get(m, 0.0) / total_w
            for m in per_model
        )
    # top_scores aus dem dominanten Modell
    dominant = max(per_model, key=lambda m: weights.get(m, 0.0))
    out["top_scores"] = per_model[dominant].get("top_scores", [])
    return out


def blend_score_matrix(
    models: Dict[str, DixonColesPoisson],
    home_xg: float,
    away_xg: float,
    weights: Dict[str, float] | None = None,
) -> np.ndarray:
    """Weighted average of the per-model score matrices at the same (λ_home, λ_away).

    Because every market we read off the matrix (1X2, totals, BTTS, Asian
    handicap, …) is a *linear* functional of the cells, deriving them from this
    blended matrix yields **exactly** the weighted blend of the per-model market
    values — i.e. the derived markets stay consistent with ``blend_markets`` and
    the heatmap shows the same distribution the headline numbers come from.
    Each ``predict_matrix`` is already normalised to sum 1, and the weights are
    renormalised here, so the result is itself a proper distribution.
    """
    weights = weights or DEFAULT_BLEND_WEIGHTS
    total_w = sum(weights.get(name, 0.0) for name in models) or 1.0
    acc: np.ndarray | None = None
    for name, model in models.items():
        w = weights.get(name, 0.0) / total_w
        m = model.predict_matrix(home_xg, away_xg) * w
        acc = m if acc is None else acc + m
    if acc is None:
        return np.zeros((1, 1))
    total = acc.sum()
    return acc / total if total > 0 else acc


def bootstrap_markets(
    model: DixonColesPoisson,
    home_xg: float,
    away_xg: float,
    *,
    n: int = 500,
    xg_sigma: float = 0.15,
    rng: np.random.Generator | None = None,
) -> Dict[str, Tuple[float, float, float]]:
    """Monte-Carlo-CIs durch Sampling von (home_xg', away_xg') ~ Normal.

    Default n=500, xg_sigma=15% des mean. Returns {market: (p5, p50, p95)}.
    Skalare Markets only; top_scores werden ausgelassen.
    """
    rng = rng or np.random.default_rng()
    home_xg = max(0.05, float(home_xg))
    away_xg = max(0.05, float(away_xg))
    home_samples = np.clip(rng.normal(home_xg, home_xg * xg_sigma, n), 0.05, None)
    away_samples = np.clip(rng.normal(away_xg, away_xg * xg_sigma, n), 0.05, None)

    keys = ["home_win", "draw", "away_win", "over_15", "over_25", "over_35", "btts"]
    accum: Dict[str, list[float]] = {k: [] for k in keys}
    for h, a in zip(home_samples, away_samples):
        m = model.predict_matrix(float(h), float(a))
        mk = model.markets(m)
        for k in keys:
            accum[k].append(_scalar(mk, k))

    out: Dict[str, Tuple[float, float, float]] = {}
    for k, vals in accum.items():
        arr = np.asarray(vals)
        out[k] = (
            float(np.percentile(arr, 5)),
            float(np.percentile(arr, 50)),
            float(np.percentile(arr, 95)),
        )
    return out


__all__ = [
    "DixonColesPoisson",
    "NegativeBinomialDixonColes",
    "build_goal_model",
    "build_all_goal_models",
    "blend_markets",
    "blend_score_matrix",
    "bootstrap_markets",
    "MODEL_NAMES",
    "DEFAULT_BLEND_WEIGHTS",
]
