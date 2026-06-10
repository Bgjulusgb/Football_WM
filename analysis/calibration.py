"""Probability-Kalibrierung — Isotonic + Platt-Scaling.

Fittet pro 1X2-Outcome (home/draw/away) eine eigene Kurve und persistiert die
Parameter in ``models_ml/artifacts/calibration_{isotonic,platt}.json``.

Der :func:`fit_calibrators` Endpoint nutzt die History in der DB
(``MatchPrediction`` mit ``actual_home_score`` gesetzt). :func:`apply` belegt
roh -> kalibriert und renormalisiert auf Summe 1.

Pragmatische Implementation:
* IsotonicRegression aus sklearn (monotonic, parameter-frei).
* Platt-Scaling als Logistic-Regression auf dem logit der Rohwahrscheinlichkeit.

Beide werden klein serialisiert (Isotonic: x_thresholds + y_thresholds; Platt:
a/b Koeffizienten), sodass kein sklearn-Modell-Pickle noetig ist.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

import structlog

from config.settings import settings

log = structlog.get_logger("analysis.calibration")

OUTCOMES = ("home", "draw", "away")

_ARTIFACT_DIR = settings.base_dir / "models_ml" / "artifacts"
_ISOTONIC_PATH = _ARTIFACT_DIR / "calibration_isotonic.json"
_PLATT_PATH = _ARTIFACT_DIR / "calibration_platt.json"


# ── Serialisierbare Kurven ────────────────────────────────────────────────────


@dataclass
class IsotonicCurve:
    x: list[float] = field(default_factory=list)
    y: list[float] = field(default_factory=list)

    def transform(self, p: float) -> float:
        if not self.x:
            return p
        if p <= self.x[0]:
            return self.y[0]
        if p >= self.x[-1]:
            return self.y[-1]
        # binary search
        lo, hi = 0, len(self.x) - 1
        while hi - lo > 1:
            mid = (lo + hi) // 2
            if self.x[mid] <= p:
                lo = mid
            else:
                hi = mid
        # linear interp
        x0, x1 = self.x[lo], self.x[hi]
        y0, y1 = self.y[lo], self.y[hi]
        if x1 == x0:
            return y0
        return y0 + (y1 - y0) * (p - x0) / (x1 - x0)


@dataclass
class PlattCurve:
    """Sigmoid(a * logit(p) + b) -> kalibrierte Wahrscheinlichkeit."""
    a: float = 1.0
    b: float = 0.0

    def transform(self, p: float) -> float:
        eps = 1e-6
        p = max(eps, min(1 - eps, p))
        z = math.log(p / (1 - p))
        return 1.0 / (1.0 + math.exp(-(self.a * z + self.b)))


@dataclass
class CalibrationArtifact:
    method: str                                  # "isotonic" | "platt"
    curves: dict[str, IsotonicCurve | PlattCurve]
    n_trained_on: int = 0

    def to_dict(self) -> dict[str, Any]:
        if self.method == "isotonic":
            cdict = {k: {"x": c.x, "y": c.y} for k, c in self.curves.items()}  # type: ignore[union-attr]
        else:
            cdict = {k: {"a": c.a, "b": c.b} for k, c in self.curves.items()}  # type: ignore[union-attr]
        return {"method": self.method, "curves": cdict, "n_trained_on": self.n_trained_on}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CalibrationArtifact":
        method = data.get("method") or "isotonic"
        raw = data.get("curves") or {}
        curves: dict[str, IsotonicCurve | PlattCurve] = {}
        for outcome in OUTCOMES:
            c = raw.get(outcome)
            if not c:
                continue
            if method == "isotonic":
                curves[outcome] = IsotonicCurve(x=list(c.get("x", [])), y=list(c.get("y", [])))
            else:
                curves[outcome] = PlattCurve(a=float(c.get("a", 1.0)), b=float(c.get("b", 0.0)))
        return cls(method=method, curves=curves, n_trained_on=int(data.get("n_trained_on", 0)))


# ── Fit ───────────────────────────────────────────────────────────────────────


def _outcome_label(home_score: int, away_score: int) -> str:
    if home_score > away_score:
        return "home"
    if away_score > home_score:
        return "away"
    return "draw"


def _collect_pairs(rows: Iterable) -> dict[str, list[tuple[float, float]]]:
    """Pro Outcome (p_predicted, y_actual_binary) aus DB-Rows."""
    out: dict[str, list[tuple[float, float]]] = {o: [] for o in OUTCOMES}
    for r in rows:
        if r.actual_home_score is None or r.actual_away_score is None:
            continue
        actual = _outcome_label(int(r.actual_home_score), int(r.actual_away_score))
        probs = {
            "home": float(r.home_win_prob or 0.0),
            "draw": float(r.draw_prob or 0.0),
            "away": float(r.away_win_prob or 0.0),
        }
        for o in OUTCOMES:
            out[o].append((probs[o], 1.0 if o == actual else 0.0))
    return out


def _fit_isotonic(pairs: list[tuple[float, float]]) -> IsotonicCurve:
    if not pairs:
        return IsotonicCurve()
    try:
        import numpy as np
        from sklearn.isotonic import IsotonicRegression
    except Exception as exc:
        log.warning("isotonic_sklearn_missing", error=str(exc))
        return IsotonicCurve()
    xs = np.asarray([p for p, _ in pairs], dtype=float)
    ys = np.asarray([y for _, y in pairs], dtype=float)
    if len(xs) < 5:
        return IsotonicCurve()
    iso = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
    iso.fit(xs, ys)
    # Eine kompakte Repraesentation: 50 Knoten gleichmaessig im Wertebereich.
    grid = np.linspace(xs.min(), xs.max(), 50)
    return IsotonicCurve(x=[float(v) for v in grid], y=[float(v) for v in iso.predict(grid)])


def _fit_platt(pairs: list[tuple[float, float]]) -> PlattCurve:
    if len(pairs) < 5:
        return PlattCurve()
    try:
        import numpy as np
        from sklearn.linear_model import LogisticRegression
    except Exception as exc:
        log.warning("platt_sklearn_missing", error=str(exc))
        return PlattCurve()
    eps = 1e-6
    ps = np.clip(np.asarray([p for p, _ in pairs], dtype=float), eps, 1 - eps)
    ys = np.asarray([y for _, y in pairs], dtype=float)
    z = np.log(ps / (1 - ps)).reshape(-1, 1)
    if ys.min() == ys.max():
        return PlattCurve()  # entartet, keine 0+1 mix
    lr = LogisticRegression(C=1e6, solver="lbfgs", max_iter=200).fit(z, ys.astype(int))
    a = float(lr.coef_[0][0])
    b = float(lr.intercept_[0])
    return PlattCurve(a=a, b=b)


def fit_calibrators(rows: Iterable) -> tuple[CalibrationArtifact, CalibrationArtifact]:
    pairs = _collect_pairs(rows)
    n = max(len(v) for v in pairs.values()) if pairs else 0

    iso = CalibrationArtifact(
        method="isotonic",
        curves={o: _fit_isotonic(pairs[o]) for o in OUTCOMES},
        n_trained_on=n,
    )
    platt = CalibrationArtifact(
        method="platt",
        curves={o: _fit_platt(pairs[o]) for o in OUTCOMES},
        n_trained_on=n,
    )
    _ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    _ISOTONIC_PATH.write_text(json.dumps(iso.to_dict(), indent=2), encoding="utf-8")
    _PLATT_PATH.write_text(json.dumps(platt.to_dict(), indent=2), encoding="utf-8")
    return iso, platt


# ── Apply (Hot-Path) ──────────────────────────────────────────────────────────


def _load(path: Path) -> CalibrationArtifact | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return CalibrationArtifact.from_dict(data)
    except Exception as exc:
        log.warning("calibration_load_failed", path=str(path), error=str(exc))
        return None


def load_isotonic() -> CalibrationArtifact | None:
    return _load(_ISOTONIC_PATH)


def load_platt() -> CalibrationArtifact | None:
    return _load(_PLATT_PATH)


def apply(
    artifact: CalibrationArtifact | None,
    home_p: float,
    draw_p: float,
    away_p: float,
) -> dict[str, float] | None:
    """Wendet die Kurven an und renormalisiert auf Summe 1. Liefert None wenn
    der Artifact fehlt oder leere Kurven hat."""
    if artifact is None or not artifact.curves:
        return None
    raw = {"home": home_p, "draw": draw_p, "away": away_p}
    transformed = {}
    for o in OUTCOMES:
        curve = artifact.curves.get(o)
        if curve is None:
            transformed[o] = raw[o]
        else:
            transformed[o] = float(curve.transform(raw[o]))
    total = sum(transformed.values())
    if total <= 0:
        return None
    return {k: v / total for k, v in transformed.items()}


# ── transform_intervals (K1 — kalibrierte Bootstrap-CIs) ──────────────────────

# Mapping zwischen den Market-Keys in confidence_intervals (`home_win/draw/away_win`)
# und den 1X2-Curve-Keys (`home/draw/away`). Andere Markets (over_*/btts) sind
# unabhaengige Bernoulli — sie werden zwar durch die home-Kurve transformiert
# (als beste verfuegbare Approximation), aber NICHT in das 1X2-Triple-Renorm
# eingerechnet.
_TRIPLE_KEYS: tuple[tuple[str, str], ...] = (
    ("home_win", "home"),
    ("draw", "draw"),
    ("away_win", "away"),
)
_BERNOULLI_KEYS: tuple[str, ...] = ("over_05", "over_15", "over_25", "over_35", "btts")


def _clip01(v: float) -> float:
    if not math.isfinite(v):
        return 0.0
    return max(0.0, min(1.0, v))


def _curve_for(artifact: CalibrationArtifact, outcome: str):
    return artifact.curves.get(outcome)


def _xform(artifact: CalibrationArtifact, outcome: str, p: float) -> float:
    curve = _curve_for(artifact, outcome)
    if curve is None:
        return _clip01(p)
    return _clip01(float(curve.transform(p)))


def transform_intervals(
    ci_dict: dict[str, dict[str, list[float] | tuple[float, float, float]]] | None,
    artifact: CalibrationArtifact | None,
) -> dict[str, dict[str, list[float]]] | None:
    """Transformiert Bootstrap-CIs (pro Modell, pro Market jeweils ein [p5,p50,p95]-Triple)
    durch die Kalibrierungskurven aus *artifact*.

    Designentscheidung (K1, v3.7.1):
    * 1X2-Triples (home_win, draw, away_win): jedes Quantil wird durch die
      jeweilige Outcome-Kurve transformiert UND quantil-weise auf Summe 1
      renormalisiert. Damit umschliesst das kalibrierte CI-Band garantiert
      den kalibrierten Punktwert (Eigenschaft: p5 <= cal_home <= p95) — das
      ist die zentrale Konsistenz-Eigenschaft, die der UI Sinn gibt.
    * Renorm kann bei steilen Kurven die Quantil-Reihenfolge eines einzelnen
      Outcomes brechen (wenn ein Outcome im Numerator schneller waechst als
      die anderen). Wir sortieren das resultierende Triple aufsteigend, damit
      die UI ein konsistentes Konfidenzband zeichnen kann. Sort ist neutral,
      wenn die Reihenfolge ohnehin erhalten bleibt.
    * Bernoulli-Markets (over_*/btts): durch die home-Curve transformiert
      (beste verfuegbare Approximation, da wir keine market-spezifische Kurve
      fitten), nur clip + sort — kein Renorm (das waeren unabhaengige
      Bernoulli-Wahrscheinlichkeiten, ein Renorm waere semantisch falsch).
    * Sonderfall Σ=0 nach Transform: das Triple faellt auf uniform (1/3, 1/3, 1/3)
      zurueck, keine Division-by-Zero.

    Liefert None, wenn entweder ci_dict oder artifact (samt Kurven) fehlt.
    """
    if ci_dict is None or artifact is None or not artifact.curves:
        return None

    out: dict[str, dict[str, list[float]]] = {}
    triple_market_keys = {mk for mk, _ in _TRIPLE_KEYS}
    for model_name, markets in ci_dict.items():
        new_markets: dict[str, list[float]] = {}

        # 1X2-Triples: per-quantile transform → renorm Σ=1 → sort.
        triple_present = all(mk in markets for mk, _ in _TRIPLE_KEYS)
        if triple_present:
            n_q = min(len(markets[mk]) for mk, _ in _TRIPLE_KEYS)
            transformed: dict[str, list[float]] = {ck: [] for _, ck in _TRIPLE_KEYS}
            for q in range(n_q):
                vals_q = {
                    ck: _xform(artifact, ck, float(markets[mk][q]))
                    for mk, ck in _TRIPLE_KEYS
                }
                total = sum(vals_q.values())
                if total <= 0.0 or not math.isfinite(total):
                    vals_q = {ck: 1.0 / 3.0 for ck in vals_q}
                else:
                    vals_q = {ck: v / total for ck, v in vals_q.items()}
                for ck, v in vals_q.items():
                    transformed[ck].append(v)
            new_markets["home_win"] = sorted(transformed["home"])
            new_markets["draw"]     = sorted(transformed["draw"])
            new_markets["away_win"] = sorted(transformed["away"])

        # Bernoulli-Markets: clip + sort, kein Renorm.
        for mk in _BERNOULLI_KEYS:
            if mk in markets:
                new_markets[mk] = sorted(_xform(artifact, "home", float(v)) for v in markets[mk])

        # Unbekannte Keys 1:1 uebernehmen (Forward-Compat).
        for mk, vals in markets.items():
            if mk in new_markets or mk in triple_market_keys or mk in _BERNOULLI_KEYS:
                continue
            try:
                new_markets[mk] = [float(v) for v in vals]
            except Exception:
                new_markets[mk] = list(vals)  # type: ignore[arg-type]
        out[model_name] = new_markets
    return out


__all__ = [
    "OUTCOMES",
    "IsotonicCurve",
    "PlattCurve",
    "CalibrationArtifact",
    "fit_calibrators",
    "load_isotonic",
    "load_platt",
    "apply",
    "transform_intervals",
]
