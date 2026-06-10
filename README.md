# 🏆 WM 2026 — Match-Analyse & Prediction Workflow

[![CI](https://github.com/bgjulusgb/football_wm/actions/workflows/ci.yml/badge.svg)](https://github.com/bgjulusgb/football_wm/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.11%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)

Ein kalibrierter **Quant-Workflow** für Spiele der FIFA WM 2026: holt Daten über
eine modulare **Abfrage-/Datenschicht**, schickt sie durch ein **20-Faktor-Ensemble**
und einen **3-Modell-Tor-Stack** (Dixon-Coles · Negative-Binomial · GLM-Poisson)
und liefert eine **Prediction mit Konfidenzintervallen, Faktor-Breakdown und
Markt-Edge** — als JSON, Markdown-Report und optionalen Charts.

> 🎯 **Out-of-the-box lauffähig:** Dank durchgängiger Mock-Datenschicht läuft der
> komplette Workflow **offline, ohne API-Keys**. Klonen, `pip install`, fertig.

---

## ⚡ Quickstart (60 Sekunden, komplett offline)

```bash
git clone https://github.com/bgjulusgb/football_wm.git
cd football_wm
pip install -r requirements.txt

# Eine Vorhersage für ein Beispielspiel (Mock-Daten, keine Keys nötig):
python -m wm2026.cli predict \
  --match config/matches/group_a/cze_vs_rsa.yaml \
  --odds "2.10/3.40/3.20" --odds-ou "1.85/1.95"
```

Ad-hoc (ohne YAML-Datei):

```bash
python -m wm2026.cli predict --home Germany --away Brazil --stage QF \
  --odds "2.40/3.20/2.90" --out reports/ --charts
```

`--out reports/` schreibt `<match_id>.json` + `<match_id>.md`; mit `--charts`
zusätzlich `*_tornado.png` und `*_heatmap.png` (benötigt `matplotlib`).

---

## 🧪 Beispiel-Output (gekürzt)

```text
# 🏆 WM 2026 — Czech Republic vs South Africa
## Executive Summary
- Most likely 1X2: Czech Republic (54.0%)  ·  CZE 54.0% / Draw 22.1% / RSA 23.8%
- Expected goals (λ): CZE 1.69 — RSA 1.00  ·  O2.5 49.9% · BTTS 49.6%
- Top-3 driving factors: goal_efficiency → home; elo_strength → home; form → home
- Value pick: 1X2 — Home @ 2.10 → edge 13.5%, half-Kelly 6.1% (sanity-check)
- Confidence: 🟡 (mock data — illustrative) (ensemble 0.59, 11/20 factors live)

## Edge Table (Phase 6)
| Market | Selection | Model P | Fair P | Odd  | Edge % | ½-Kelly % | Action       |
|--------|-----------|---------|--------|------|--------|-----------|--------------|
| 1X2    | Home      | 54.0%   | 44.0%  | 2.10 | 13.5   | 6.13      | sanity-check |
```

---

## 🔁 Der 8-Phasen-Workflow

Der dünne Orchestrierungs-Layer **`wm2026/`** steckt die bestehenden Module zu
einer reproduzierbaren Pipeline zusammen (`wm2026/pipeline.py → run_prediction`):

| Phase | Was passiert | Code |
|---|---|---|
| **1 · Data Collection** | paralleler Fan-out zu ~13 Konnektoren → `FactorContext` | `data_sources/orchestrator.py` |
| **2 · Faktoren** | 20 Faktoren → je ein `FactorSignal` | `factors/registry.py`, `factors/*.py` |
| **3 · Sentiment** | Reddit/X-Stimmung → `sentiment_payload` | `factors/sentiment_factor.py` |
| **4 · Tor-Modelle** | Ensemble → λ; 3 Modelle + Bootstrap-CIs | `models_ml/poisson_goals.py`, `analysis/match_predictor.py` |
| **5 · Kalibrierung** | Isotonic + Platt (graceful) | `analysis/calibration.py` |
| **6 · Markt-Edge** | De-Vigging, Edge, Kelly | `wm2026/edge.py` |
| **7 · Validierung** | Sanity-Checklist | `wm2026/pipeline.py` |
| **8 · Output** | JSON + Markdown + Charts | `wm2026/report.py`, `wm2026/viz.py` |

Die vollständige Methodik steht im **[Master-Prompt](prompts/WM2026_MASTER_PROMPT.md)**.

---

## 🛰️ Die Abfrage-/Datenschicht (`data_sources/`)

Das Herz des Workflows. Jeder Konnektor erbt von `BaseConnector` (gemeinsamer
HTTP-Client, zweistufiger TTL-Cache, Exponential-Backoff) und liefert ein
`FetchResult{data, mode, fetched_at, source}` mit `mode ∈ {live, cache, mock, error}`.
**Eine ausgefallene Quelle wirft nie in den Faktor-Layer** — sie liefert `error`,
der Faktor neutralisiert sich, das Ensemble re-normalisiert.

| Konnektor | Quelle | Liefert | Mock-Toggle |
|---|---|---|---|
| `openfootball` | openfootball | Historie, H2H, Fixtures | `USE_MOCK_OPENFOOTBALL` |
| `football_data_org` | football-data.org | Fixtures (Cross-Check) | `USE_MOCK_FOOTBALL_DATA` |
| `openligadb` | OpenLigaDB | Historie (Lücken-Füller) | `USE_MOCK_OPENLIGADB` |
| `fbref` / `understat` | FBref / Understat | xG for/against | `USE_MOCK_FBREF` / `_UNDERSTAT` |
| `fotmob` / `sofascore` | FotMob / SofaScore | Lineups, Verletzungen | `USE_MOCK_FOTMOB` / `_SOFASCORE` |
| `transfermarkt` | Transfermarkt | Kader-Marktwert | `USE_MOCK_TRANSFERMARKT` |
| `wikidata` | Wikidata | Kader-Infos | `USE_MOCK_WIKIDATA` |
| `weather` | open-meteo | Temp/Regen/Wind am Venue | `USE_MOCK_WEATHER` |
| `rss_news` | RSS-Feeds | Verletzungs-News | `USE_MOCK_RSS` |
| `thesportsdb` | TheSportsDB | Team-Meta | `USE_MOCK_THESPORTSDB` |

`DataSourceOrchestrator.populate(ctx)` fächert all das **parallel** auf
(`asyncio.gather`), schreibt die Felder in den `FactorContext` und hinterlegt pro
Slice die Provenance (für das „live/cache/mock"-Badge im Report).

**Mock vs. Live:** Standardmäßig (`--mode mock`) liefert jeder Konnektor seine
deterministische Offline-Payload aus `data_sources/mock/` → reproduzierbar, kein
Netzwerk, keine Keys. Mit `--mode live` (+ `.env`) werden die echten Endpunkte
abgefragt; jeder Konnektor degradiert bei Netzwerkfehlern weiterhin auf seinen Mock.

---

## 🖥️ CLI

```bash
python -m wm2026.cli predict [OPTIONS]     # vollständige Pipeline
python -m wm2026.cli list                  # alle Match-Configs auflisten
```

Wichtige Optionen:

| Option | Bedeutung |
|---|---|
| `--match PATH` | Match-Config-YAML (oder `--home/--away` für ad-hoc) |
| `--mode mock\|live` | offline/mock (Default) vs. echte Daten |
| `--odds "H/D/A"` | 1X2-Dezimalquoten → Edge-Tabelle (Phase 6) |
| `--odds-ou "O/U"` · `--odds-btts "Y/N"` | Quoten für O/U 2.5 bzw. BTTS |
| `--bootstrap N` | Bootstrap-Samples für CIs (Default 500) |
| `--out DIR` | JSON/MD (und mit `--charts` PNGs) schreiben |
| `--json-only` | JSON statt Markdown ausgeben |
| `--sentiment-json FILE` | vorab berechnetes `sentiment_payload` injizieren |

Nach `pip install .` steht der Befehl auch als `wm2026 predict ...` zur Verfügung.

---

## 📝 Match-Konfiguration

Eine Config braucht mindestens die Blöcke `match:` und `teams:`
(siehe `config/matches/**/*.yaml`):

```yaml
match:
  id: wm2026_groupa_cze_vs_rsa
  stage: group_stage
  kickoff_utc: '2026-06-18T18:00:00Z'
  venue: BMO Field, Toronto
  bookmaker_odds_1x2: "2.10 / 3.40 / 3.20"   # optional, für Phase 6
teams:
  home: {name: Czech Republic, code: CZE, elo_rating: 1780, avg_xg_season: 1.38, avg_xg_conceded: 1.18}
  away: {name: South Africa,   code: RSA, elo_rating: 1640, avg_xg_season: 1.05, avg_xg_conceded: 1.60}
```

`avg_xg_season` / `avg_xg_conceded` bilden die Basis-λ; alle weiteren Felder
(Reddit-Quellen, Sentiment-Config etc.) sind optional und steuern die Live-Faktoren.

---

## 🔌 Live-Modus & `.env`

```bash
cp .env.example .env
# In .env: gewünschte USE_MOCK_*=false setzen + passende API-Keys eintragen
python -m wm2026.cli predict --match <yaml> --mode live
```

`.env.example` ist **offline-first** (alle `USE_MOCK_*=true`) — eine frische Kopie
läuft ohne Keys. Optionale Keys: `ODDS_API_KEY` (Quoten), `FOOTBALL_DATA_API_KEY`
(Fixtures), `NVIDIA_API_KEY` (LLM-Sentiment), Reddit-Credentials (Sentiment).

---

## 📦 Optionale Features

```bash
pip install -r requirements-optional.txt   # oder gezielt via Extras:
pip install ".[viz]"        # PNG-Charts (--charts)
pip install ".[stats]"      # exaktes GLM-Poisson + Isotonic/Platt-Kalibrierung
pip install ".[sentiment]"  # VADER + TextBlob (Phase 3)
pip install ".[cache]"      # persistenter Cache-Backstop (SQLite)
pip install ".[full]"       # alles Obige
```

Der **Core** (`requirements.txt`) reicht für eine vollständige Mock-Prediction.
Fehlt ein optionales Paket, degradiert der Workflow sauber (GLM → Poisson,
Kalibrierung → roher Output, Charts → übersprungen).

---

## 🗂️ Projektstruktur

```text
wm2026/            ← Workflow-Layer (CLI, Pipeline, Edge, Report, Viz)  ← NEU
data_sources/      ← Abfrage-/Datenschicht (Konnektoren + Mocks + Orchestrator)
factors/           ← 20 Faktoren + Registry
analysis/          ← Ensemble, Predictor, Kalibrierung, Metriken
models_ml/         ← Tor-Modelle (Dixon-Coles / NegBin / GLM) + Bootstrap
config/matches/    ← 104 WM-2026-Match-Configs (Gruppen → Finale)
prompts/           ← Master-Prompt (Methodik)                          ← NEU
tests/             ← u.a. tests/test_wm2026_pipeline.py                ← NEU
crawler/ · api/ · db/ · services/   ← optionaler Reddit-/FastAPI-/DB-Stack
```

---

## ✅ Tests & CI

```bash
pip install pytest
pytest tests/test_wm2026_pipeline.py -q
```

Die [GitHub-Actions-CI](.github/workflows/ci.yml) installiert auf Python 3.11/3.12
nur den Core, läuft die Workflow-Tests, erzeugt eine Mock-Prediction und lädt den
Report als Artefakt hoch — so ist garantiert, dass das Repo bei jedem Download baut.

---

## 🔒 Sicherheit

- **Niemals** eine echte `.env` committen — sie ist in `.gitignore`, Template ist
  `.env.example`.
- Wurden jemals echte Keys committet (auch in der History), **sofort rotieren**:
  Reddit-Secret, `ODDS_API_KEY`, `FOOTBALL_DATA_API_KEY`, `NVIDIA_API_KEY`,
  `ADMIN_API_KEY`.

---

## ⚠️ Disclaimer

Forschungs- und Bildungsprojekt — **keine** Wett-Empfehlung. Vorhersagen im
Mock-Modus sind illustrativ. Lizenz: [MIT](LICENSE).
