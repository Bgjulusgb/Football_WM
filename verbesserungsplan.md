# 📈 Verbesserungsplan — Mathematik & Cowork

Priorisierte Roadmap für die Vorhersage-Qualität. **Phase 1 ist umgesetzt**
(siehe „erledigt"); Phase 2/3 sind auf Wiederverwendung der bestehenden
Module ausgelegt — jede Position nennt Formel, Begründung und Ziel-Datei.

> Leitprinzip: jede Verbesserung bleibt **pure & getestet**, degradiert sauber
> ohne optionale Deps und ändert das JSON-Schema nur additiv.

---

## ✅ Phase 1 — erledigt (diese Iteration)

| # | Verbesserung | Mathematik | Datei |
|---|---|---|---|
| 1 | **Abgeleitete Märkte** aus der Score-Matrix | lineare Funktionale von `M[i][j]` | `wm2026/markets.py` |
| 2 | **Asian Handicap** inkl. Viertellinien | Half-Win/Half-Push-Settlement (`adj = (i−j)+line`) | `wm2026/markets.py` |
| 3 | **Double Chance · DNB · Team-Totals · Clean Sheet · Win-to-Nil · Odd/Even** | Teilsummen der Matrix | `wm2026/markets.py` |
| 4 | **Blended Score-Matrix** (alle 3 Modelle) für Heatmap + Derived Markets | `M̄ = Σ wₘ·Mₘ` — Märkte bleiben exakt blend-konsistent | `models_ml/poisson_goals.py` |
| 5 | **RPS** (Ranked Probability Score) im Backtesting | `RPS = 1/(r−1)·Σ(CPₖ−CYₖ)²`, geordnet Home>Draw>Away | `analysis/backtesting.py` |
| 6 | **Conservative Kelly** (p5-Edge) | Edge/Kelly auf der Bootstrap-Untergrenze statt p50 | `wm2026/edge.py` |

**Wirkung:** Das Markt-Board deckt jetzt die wichtigsten Wett-Märkte ab; die
`(p5)`-Spalten zeigen ehrlich, welche „Value"-Picks die eigene Modellunsicherheit
**nicht** überleben (z.B. eine 1X2-Home-Edge von +13.5 % fällt auf −12.8 % @ p5).

---

## 🔜 Phase 2 — Modell-Tiefe (größter erwarteter Brier/RPS-Gewinn)

### 2.1 Dixon-Coles-Zeitdecay ξ auf die Tor-Raten-Schätzung
**Problem:** `avg_xg_season` ist ungewichtet; ein 0:5 von vor 18 Monaten zählt
wie letzte Woche. **Formel:** Gewicht je historischem Spiel
`φ(t) = exp(−ξ·Δt_days)`, Halbwertszeit `ln2/ξ` (Lit.: ξ≈0.0065/Tag ⇒ ~9 Mon.).
Dann gewichtete Attack/Defence-Raten statt Saison-Mittel.
**Wo:** neues `models_ml/time_decay.py` (pure, `dc_weights(dates, ref, xi)`),
eingehängt in `factors/_history.py` (ersetzt `0.9^index`) hinter einem
`settings.dc_time_decay_xi`-Flag (Default = altes Verhalten).

### 2.2 Echtes bivariates Poisson als 4. Modell — ✅ Klasse implementiert (opt-in)
**Status:** `BivariatePoisson` (Karlis-Ntzoufras, `λ₃`-Kovarianz) ist in
`models_ml/poisson_goals.py` umgesetzt + getestet (`tests/test_bivariate_poisson.py`):
`X=Y₁+Y₃, Y=Y₂+Y₃`, `Yᵢ~Poisson(λᵢ)`, `Cov=λ₃`. `λ₃` wird aus dem xG
herausgelöst (`λ₁=home−λ₃`, `λ₂=away−λ₃`) → **Marginal-Means bleiben exakt**,
nur die Korrelation (mehr Unentschieden) steigt; `λ₃→0` ⇒ unabhängiges Poisson.
Über `build_goal_model("bivariate")` wählbar. **Offen (bewusst defensiv):** in
`MODEL_NAMES` + `DEFAULT_BLEND_WEIGHTS` aufnehmen, sobald die Blend-Gewichte
(2.4) auf einem Backtest-Set neu getunt sind — das ändert sonst alle Default-Outputs.

### 2.3 Kalibrierung aktiviert — ✅ erledigt (zwei Wege, beide ohne sklearn)
**Problem war:** `analysis/calibration.py` fittete nur aus der DB *und* brauchte
sklearn; ein frischer Clone hatte nie ein Artefakt → Phase 5 lief leer.
**Jetzt:**
1. **Pure-Python-Fit (kern-deps):** PAV-Isotonic (`_pav`/`_isotonic_pav_curve`)
   + Newton/IRLS-Platt (`_platt_newton`) als sklearn-freie Fallbacks →
   `fit_calibrators` liefert echte Kurven mit nur numpy/scipy.
2. **Offline-Fit-Script:** `scripts/fit_calibration_offline.py` liest eine CSV
   `(home_win_prob,draw_prob,away_win_prob,home_score,away_score)` aus einem
   *berühmten Prior-Set* (WC2022 + EURO2024 + Copa2024), fittet, schreibt die
   Artefakte und zeigt den Brier-vorher/nachher. Danach greift `--calibrate auto`.
3. **Markt-Anker (pro Spiel, ohne Historie):** `calibration.market_anchor` zieht
   die 1X2 zur vig-freien Markt-Konsens-Quote — dem kanonisch *gut kalibrierten*
   Fußball-Forecaster (Constantinou & Fenton 2013). `--calibrate market`. Das ist
   der „pro Spiel im Claude-Workflow"-Pfad: Claude recherchiert die Quoten, das
   Modell kalibriert dagegen. Kompoundet mit dem Markt-Faktor (Doku-Hinweis).

**Famous-Referenzwerte (verankert):** Markt = bester kalibrierter Forecaster
(Constantinou & Fenton 2013); Dixon-Coles-Zeitdecay `ξ=0.0065` (Original, in
Halb-Wochen) ≈ 107-Tage-Halbwertszeit für 2.1.

### 2.4 Blend-Gewichte + ρ via Optuna tunen
**Problem:** `DEFAULT_BLEND_WEIGHTS` (0.4/0.3/0.3) und ρ=0.1 sind gesetzt, nicht
optimiert (Optuna tunt heute nur Faktor-Gewichte). **Lösung:** Zielmetrik
**RPS** (2.+Phase-1-#5) über das Backtest-Set; `analysis/weight_optimizer.py`
um einen `tune_goal_model_params()`-Pfad erweitern → `runtime_*`-Artefakt.

### 2.5 Geometrische λ-Aggregation
**Problem:** Faktor-Multiplikatoren werden arithmetisch gemittelt; log-lineare
(geometrische) Mittelung ist für multiplikative Tilts konsistenter und
symmetrisch in `home/away`. **Formel:** `λ_mult = exp(Σ wᵢ·ln sᵢ)`. **Wo:**
`analysis/factor_ensemble.py` hinter `settings.lambda_aggregation = "geom"`.

---

## 🌍 Phase 3 — Reichweite & Cowork

- **Turnier-Monte-Carlo** (Gruppen→KO): `scripts/tournament_mc.py` simuliert die
  104 Spiele über die Pipeline-λ → Gruppen-/Titel-Wahrscheinlichkeiten je Team.
- **HT/FT & First-Goal:** Halbzeit-λ = `λ_full · 0.45` (empirischer Split),
  eigene Score-Matrix → HT/FT-9-Felder; in `wm2026/markets.py` ergänzen.
- **Karten/Ecken:** eigenes (Negbin-)Zählmodell mit Referee-/Derby-Faktor —
  neuer Faktor + Markt; braucht eine Datenquelle (sofascore-Stats).
- **Per-Quelle-Live-Toggle:** `--live openfootball,weather` statt globalem
  `--mode`, damit Cowork einzelne Quellen scharf schalten kann (`wm2026/cli.py`
  + `apply_runtime_profile`).

---

## Verifikation jeder Position
```bash
pytest tests/test_markets.py tests/test_edge_conservative.py \
       tests/test_backtesting_rps.py tests/test_wm2026_pipeline.py -q
python -m wm2026.cli predict --match config/matches/group_a/cze_vs_rsa.yaml \
  --odds "2.10/3.40/3.20" --odds-dc "1.28/1.30/1.55" --odds-ah=-0.5:1.95/1.95
```
Neue Mathematik kommt immer **mit Test** (Invariante oder Referenzwert) und hält
das bestehende Schema additiv.
