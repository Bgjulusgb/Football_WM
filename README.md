<div align="center">

# 🏆 WM 2026 — Match-Analyse & Prediction Workflow

**Kalibrierter Quant-Workflow für FIFA-WM-2026-Spiele — von Live-Daten zur Value-Wette, reproduzierbar in einem Befehl.**

[![CI](https://github.com/bgjulusgb/football_wm/actions/workflows/ci.yml/badge.svg)](https://github.com/bgjulusgb/football_wm/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.11%2B-blue)
![deps](https://img.shields.io/badge/core%20deps-numpy%20%C2%B7%20scipy-orange)
![markets](https://img.shields.io/badge/märkte-15%2B-success)
![schema](https://img.shields.io/badge/schema-1.2-informational)
![License](https://img.shields.io/badge/license-MIT-green)

</div>

Modulare Datenschicht → **20-Faktor-Ensemble** → **4-Modell-Tor-Stack** (Dixon-Coles ·
Negative-Binomial · GLM-Poisson · bivariates Poisson) → Prediction mit
Konfidenzintervallen, vollem **Markt-Board** und **Markt-Edge**. **Default = Live-Daten**
aus dem Internet; was die Konnektoren nicht holen, recherchiert **Claude im
Cowork-Auftrag**. `--mode mock` läuft komplett offline (Tests/CI/Reproduzierbarkeit).

## ⚡ Quickstart
```bash
pip install -r requirements.txt
# Live (Default): echte Internet-Daten; Lücken → Cowork-Auftrag für Claude
python -m wm2026.cli predict --home Germany --away Brazil --stage QF \
  --odds "2.40/3.20/2.90" --calibrate market --out reports/
# Komplett offline & reproduzierbar:
python -m wm2026.cli predict --mode mock --match config/matches/group_a/cze_vs_rsa.yaml
python debug.py        # jede Funktion einmal auf Mock-Daten (✅/❌ + Summary)
```

## 🗺️ Architektur (Datenfluss)
```mermaid
flowchart LR
    IN["Match-YAML / CLI"] --> CTX["build_context"]
    CTX --> P1["① Data-Fan-out<br/>~13 Konnektoren"]
    P1 --> P2["②③ 20 Faktoren<br/>+ Sentiment"]
    P2 --> ENS["Faktor-Ensemble → λ"]
    ENS --> P4["④ 4 Tor-Modelle<br/>DC · NegBin · GLM · BiPois"]
    P4 --> MAT["blend_score_matrix"]
    MAT --> MK["markets.py<br/>15+ Märkte"]
    MAT --> P5["⑤ Kalibrierung<br/>isotonic · Platt · Markt"]
    MK --> P6["⑥ Edge / Kelly<br/>+ Conservative p5"]
    P5 --> P6
    P6 --> OUT["⑧ JSON · Markdown · Charts"]
    P1 -. "mock / error" .-> CW["🤝 Cowork-Auftrag"]
    CW -. "recherchieren + einspeisen" .-> CTX
```

| Phase | Inhalt | Code |
|---|---|---|
| ① Data | paralleler Fan-out zu ~13 Konnektoren | `data_sources/orchestrator.py` |
| ②③ Faktoren + Sentiment | 20 Faktoren → `FactorSignal` | `factors/registry.py` |
| ④ Tor-Modelle | Ensemble → λ, 4 Modelle + Bootstrap-CIs | `models_ml/poisson_goals.py` |
| ⑤ Kalibrierung | isotonic + Platt + Markt-Anker (sklearn-frei) | `analysis/calibration.py` |
| ⑥ Markt-Edge | De-Vig, Edge, Kelly + **Conservative p5-Kelly** | `wm2026/edge.py` |
| ⑦ Validierung | Sanity-Checklist + Cowork-Gaps | `wm2026/pipeline.py` |
| ⑧ Output | JSON + Markdown + Charts | `wm2026/report.py` |

## 🎯 Markt-Board
Alle Märkte sind **lineare Funktionale derselben blend-konsistenten Score-Matrix**
(`wm2026/markets.py`) — konsistent mit der Headline-1X2/O-U.

| Markt | Funktion |
|---|---|
| 1X2 · Double Chance · Draw-No-Bet | `one_x_two` · `double_chance` · `draw_no_bet` |
| Over/Under (beliebige + Viertellinien) | `total_over_under` |
| Asian Handicap (inkl. Viertellinien) | `asian_handicap` |
| Team-Totals · Clean Sheet · Win-to-Nil · Odd/Even | `team_total` · `clean_sheet` · `win_to_nil` · `odd_even_goals` |
| **Winning Margin · Multi-Goal-Bands** 🆕 | `winning_margin` · `multi_goal_bands` |
| **Exact-Total-Goals-Verteilung** 🆕 | `exact_total_goals` |
| **First Goal · Halftime/Fulltime** 🆕 | `first_goal` · `ht_ft` |

Die Edge-Tabelle zeigt zusätzlich die konservative `(p5)`-Edge: Value, der die
Bootstrap-Modellunsicherheit überlebt.

## 🧮 Tiefere Mathematik (optional, hinter Flags)
- **Dixon-Coles-MLE-λ-Schätzer** (`analysis/xg_estimator.py`): schätzt Attack/Defence
  + Heimvorteil aus **zeit-gewichteter** Historie (`exp(−ξ·Δt)`) statt naivem
  xG-Mittel — `settings.use_mle_xg` (Default aus → Output unverändert).
- **Turnier-Monte-Carlo** (`wm2026/tournament.py`): sampelt Gruppenphase → KO über
  die blend-konsistente Score-Matrix; **10 000 Sims des 48-Team-Felds in ~1,5 s**
  (gebackene CDFs + vektorisierte pmf). Liefert Titel-/Finale-/Achtelfinal-%.

## 📸 Beispiel-Report
Ein kompletter Mock-Report (Czech Republic vs South Africa) liegt unter
[`docs/examples/`](docs/examples/) — als
[Markdown](docs/examples/example_report.md) ·
[HTML](docs/examples/example_report.html) (self-contained, mit eingebetteten Charts) ·
[JSON](docs/examples/example.json), plus ein
[10 000-Sim-Turnierlauf](docs/examples/tournament.md).

| Faktor-Tornado | Score-Heatmap |
|---|---|
| ![Tornado](docs/examples/example_tornado.png) | ![Heatmap](docs/examples/example_heatmap.png) |

## 🤝 Der Cowork-Loop (Claude als Recherche-Instanz)
```mermaid
flowchart LR
    R["wm2026 predict --mode live"] --> G{"Quellen<br/>live?"}
    G -- "ja" --> OK["Prediction"]
    G -- "mock/error" --> T["🤝 Cowork-Auftrag<br/>(priorisierte Gaps)"]
    T --> C["Claude: Web Search<br/>(value, source, fetched_at)"]
    C --> F["einspeisen via YAML /<br/>--odds* / --sentiment-json"]
    F --> R
```

## 🖥️ CLI
```bash
python -m wm2026.cli predict     --match <yaml> [OPTIONS]   # volle Pipeline
python -m wm2026.cli tournament  --sims 10000               # Turnier-Monte-Carlo (Titel-%)
python -m wm2026.cli research     --home A --away B          # Cowork-Auftrag + Overrides-Template
python -m wm2026.cli list                                   # Match-Configs auflisten
```
`--mode live|mock` (Default **live**) · `--odds "H/D/A"` · `--odds-ou "O/U"` ·
`--odds-btts "Y/N"` · `--odds-dc "1X/12/X2"` · `--odds-ah=-0.5:1.95/1.95` ·
`--calibrate auto|market|none` · **`--format markdown|json|html`** ·
**`--overrides-json FILE`** (Claude-recherchierte Werte) · `--bootstrap N` ·
`--out DIR` · `--charts`. Nach `pip install .` auch als `wm2026 …`.

**Cowork-Loop:** `wm2026 research …` → Template ausfüllen (Web Search) →
`wm2026 predict … --overrides-json filled.json --format html`.

## 📚 Mehr
- **[`prompt.md`](prompt.md)** — Ein-Prompt-Einstieg für Claude Cowork.
- **[`prompts/WM2026_MASTER_PROMPT.md`](prompts/WM2026_MASTER_PROMPT.md)** — volle Methodik.
- **[`verbesserungsplan.md`](verbesserungsplan.md)** — Mathematik-Roadmap.
- **[`CLAUDE.md`](CLAUDE.md)** — Entwickler-/Agenten-Guide (Architektur, Konventionen).
- Optionale Features: `pip install ".[viz]" ".[stats]" ".[sentiment]" ".[full]"` —
  fehlt eins, degradiert der Workflow sauber.

## ✅ Tests & Debug
```bash
pip install pytest
pytest tests/test_wm2026_pipeline.py tests/test_markets.py tests/test_markets_extended.py \
       tests/test_edge_conservative.py tests/test_backtesting_rps.py \
       tests/test_bivariate_poisson.py tests/test_calibration_offline.py -q
python debug.py
```
CI baut auf Python 3.11/3.12 nur den Core, fährt diese Suites + `debug.py` und
erzeugt eine Mock-Prediction als Artefakt.

## 🔒 Sicherheit & Disclaimer
Nie eine echte `.env` committen (Template: `.env.example`); geleakte Keys sofort
rotieren. Forschungs-/Bildungsprojekt — **keine** Wett-Empfehlung, Mock-Vorhersagen
sind illustrativ. Lizenz: [MIT](LICENSE).
