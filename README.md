# 🏆 WM 2026 — Match-Analyse & Prediction Workflow

[![CI](https://github.com/bgjulusgb/football_wm/actions/workflows/ci.yml/badge.svg)](https://github.com/bgjulusgb/football_wm/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.11%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)

Kalibrierter **Quant-Workflow** für WM-2026-Spiele: modulare Datenschicht →
**20-Faktor-Ensemble** → **3-Modell-Tor-Stack** (Dixon-Coles · Negative-Binomial ·
GLM-Poisson) → Prediction mit Konfidenzintervallen, vollem Markt-Board und
Markt-Edge. Läuft **out-of-the-box offline** (Mock-Daten, keine API-Keys).

## ⚡ Quickstart (offline, 60 s)
```bash
pip install -r requirements.txt
python -m wm2026.cli predict --home Germany --away Brazil --stage QF \
  --odds "2.40/3.20/2.90" --out reports/
```
`--match config/matches/<gruppe>/<spiel>.yaml` nutzt eine fertige Config
(104 Spiele vorhanden); `--mode live` + `.env` zieht echte Daten.

## 🔁 8-Phasen-Pipeline (`wm2026/pipeline.py → run_prediction`)
| Phase | Inhalt | Code |
|---|---|---|
| 1 Data | paralleler Fan-out zu ~13 Konnektoren | `data_sources/orchestrator.py` |
| 2 Faktoren | 20 Faktoren → `FactorSignal` | `factors/registry.py` |
| 3 Sentiment | Reddit/X → `sentiment_payload` | `factors/sentiment_factor.py` |
| 4 Tor-Modelle | Ensemble → λ, 3 Modelle + Bootstrap-CIs | `models_ml/poisson_goals.py` |
| 5 Kalibrierung | Isotonic + Platt (graceful) | `analysis/calibration.py` |
| 6 Markt-Edge | De-Vig, Edge, Kelly (+ **Conservative p5-Kelly**) | `wm2026/edge.py` |
| 7 Validierung | Sanity-Checklist | `wm2026/pipeline.py` |
| 8 Output | JSON + Markdown + Charts | `wm2026/report.py` |

## 🎯 Markt-Board
1X2 · O/U 0.5–4.5 · BTTS · Correct Score · **Double Chance · Draw-No-Bet ·
Asian Handicap (inkl. Viertellinien) · Team-Totals · Clean Sheet · Win-to-Nil ·
Odd/Even** — alle aus einer **blend-konsistenten Score-Matrix** abgeleitet
(`wm2026/markets.py`). Edge-Tabelle zeigt zusätzlich die konservative `(p5)`-Edge:
Value, der die Modellunsicherheit überlebt.

## 🖥️ CLI (wichtigste Optionen)
```bash
python -m wm2026.cli predict --match <yaml> [OPTIONS]
python -m wm2026.cli list
```
`--mode mock|live` · `--odds "H/D/A"` · `--odds-ou "O/U"` · `--odds-btts "Y/N"` ·
`--odds-dc "1X/12/X2"` · `--odds-ah=-0.5:1.95/1.95` · `--bootstrap N` ·
`--out DIR` · `--charts` · `--json-only`. Nach `pip install .` auch als `wm2026 …`.

## 📚 Mehr
- **[`prompt.md`](prompt.md)** — Ein-Prompt-Einstieg für Claude Cowork.
- **[`prompts/WM2026_MASTER_PROMPT.md`](prompts/WM2026_MASTER_PROMPT.md)** — volle Methodik.
- **[`verbesserungsplan.md`](verbesserungsplan.md)** — Mathematik-Roadmap (Phase 1 erledigt).
- **[`CLAUDE.md`](CLAUDE.md)** — Entwickler-/Agenten-Guide (Architektur, Konventionen).
- Optionale Features: `pip install ".[viz]" ".[stats]" ".[sentiment]" ".[full]"` —
  fehlt eins, degradiert der Workflow sauber.

## ✅ Tests & CI
```bash
pip install pytest
pytest tests/test_wm2026_pipeline.py tests/test_markets.py \
       tests/test_edge_conservative.py tests/test_backtesting_rps.py -q
```
CI baut auf Python 3.11/3.12 nur den Core, fährt diese Suites und erzeugt eine
Mock-Prediction als Artefakt.

## 🔒 Sicherheit & Disclaimer
Nie eine echte `.env` committen (Template: `.env.example`); geleakte Keys sofort
rotieren. Forschungs-/Bildungsprojekt — **keine** Wett-Empfehlung, Mock-Vorhersagen
sind illustrativ. Lizenz: [MIT](LICENSE).
