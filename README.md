# RedditOrakel v3.7

FIFA World Cup 2026 match predictor. Live-Daten-first (openfootball, TheSportsDB, Open-Meteo, FBref, Understat, FotMob, SofaScore, Transfermarkt, RSS-News) ⇒ **14-Faktor-Ensemble** ⇒ λ-Multiplikatoren ⇒ **Drei-Modelle-Tor-Blend** (Dixon-Coles-Poisson · NegBin · GLM-Poisson) ⇒ **Bootstrap-Konfidenzintervalle** ⇒ **Isotonic + Platt-Kalibrierung**.

**Stack:** FastAPI · async SQLAlchemy · SQLite · React 18 · TypeScript · Vite · TailwindCSS · Recharts · scikit-learn · XGBoost · LightGBM (optional)

**Highlights v3.6 → v3.7:**
- 14 Faktoren (Elo, Form, H2H, Tor-Effizienz, Turnier-Kontext, Sentiment, Kader-Verfügbarkeit, FIFA-Ranking, Ruhe/Reise, Höhenlage, Markt-Quoten, Wetter, Verletzungs-News, Momentum-Drift) — pluggable in `factors/`, gewichtet in `analysis/factor_ensemble.py`.
- Pro Vorhersage werden **alle drei Tor-Modelle parallel** gerechnet (`models_ml/poisson_goals.build_all_goal_models`) und per `goal_model_combine` entweder geblendet (default 0.4/0.3/0.3) oder als „primär" gewählt.
- Bootstrap-CIs (n=500 Samples, σ=15 % · xG) liefern p5/p50/p95 pro Markt.
- **K1 (v3.7):** dieselben CIs werden auch durch Isotonic + Platt geschickt, sodass das kalibrierte Konfidenzband konsistent zum kalibrierten Punktwert liegt.
- Admin-Panel: Tab-basiert (Modelle / Faktor-Gewichte / Datenquellen / Pro-Modell / Training+Kalibrierung) — Toggles + Hot-Reload via `runtime_flags.yaml` & `runtime_weights.yaml` (**atomar geschrieben**).
- Soft-Delete: `MatchPrediction.is_latest` markiert die jeweils aktuelle Row pro Match.

---

## Quick Start

Doppelklick auf **`start.bat`** im Projekt-Root. Backend (FastAPI :8000) und Frontend Dashboard (Vite :5173) starten in zwei eigenen Konsolenfenstern. Beim ersten Start werden venv, pip, spaCy und npm automatisch eingerichtet.

```
http://localhost:5173       ← Frontend Dashboard
http://localhost:5173/admin ← Admin-Panel
http://localhost:8000       ← Backend API
http://localhost:8000/docs  ← Swagger UI
```

Alle Konsolenfenster müssen manuell geschlossen werden. Bei Fehlern bleibt das Fenster offen, damit die Meldung sichtbar bleibt.

### Trainieren & Verwalten (KI / ML)

`ki-run-and-train.bat` ist der dedizierte Launcher für ML-Training und Daten-Verwaltung — installiert zusätzlich den Scientific Stack (LightGBM, Optuna, PyMC, ArviZ) und – falls möglich – g++ via MSYS2 für das PyTensor C-Backend.

| Modus | Argument | Was passiert |
|---|---|---|
| **TRAIN** | `--mode=train` | Volle Pipeline 1→10 headless (Daten-Sync + ML-Training: xG, LightGBM, Optuna, PyMC, PageRank) |
| **MENU** | `--mode=menu` | Klassisches interaktives 12-Punkte-Menü für Einzeloperationen |
| **AUTO** | _(default)_ | TUI fragt nach Modus (Train oder Menu) |

Beispiel: `ki-run-and-train.bat --mode=train` für eine komplette Re-Training-Runde mit Default-Parametern.

### Migration

- **v3.3 → v3.4:** `menu.bat` → `ki-run-and-train.bat` (Modus `menu`); `start.bat` zwischenzeitlich als `ki-app-start.bat`.
- **v3.4 → v3.5:** `start.bat` / `start.ps1` sind zurück und starten Backend + Frontend in eigenen Fenstern. `ki-app-start.*` entfernt. `--mode=run` aus `ki-run-and-train` entfernt (gibt nur noch Hinweis auf `start.bat` aus).

---

## Prerequisites

- Python 3.11+
- Node.js 18+

---

## Manual Installation

### Backend

```bash
cd backend
python -m venv .venv

# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate

pip install -r requirements.txt
python -m spacy download en_core_web_sm
```

### Frontend

```bash
cd frontend
npm install
```

---

## Configuration

Copy `backend/.env.example` to `backend/.env` and adjust as needed:

| Variable | Default | Description |
|---|---|---|
| `USE_MOCK_CRAWLER` | `true` | `true` = synthetic data, `false` = real Reddit |
| `USE_ARCTIC_SHIFT` | `false` | `true` = Reddit JSON + Arctic Shift in parallel |
| `DATABASE_URL` | `sqlite+aiosqlite:///./redditorakel.db` | SQLite path (dev) |
| `USE_ROBERTA` | `false` | RoBERTa scorer — Phase 2, requires extra deps |
| `LOG_LEVEL` | `INFO` | structlog level |
| `REDDIT_CLIENT_ID` | _(empty)_ | Optional — only needed for PRAW/OAuth |
| `REDDIT_CLIENT_SECRET` | _(empty)_ | Optional |
| `REDDIT_USER_AGENT` | `RedditOrakel/2.0` | HTTP User-Agent |

---

## Manual Start

```bash
# Terminal 1 — Backend
cd backend
.venv\Scripts\activate       # Windows
# source .venv/bin/activate  # macOS/Linux
uvicorn main:app --reload --port 8000

# Terminal 2 — Frontend
cd frontend
npm run dev
```

The backend auto-discovers all 72 match YAML configs on startup and upserts them into the DB. The SQLite database is created automatically — no migration needed.

---

## Scraper Modes

| `USE_MOCK_CRAWLER` | `USE_ARCTIC_SHIFT` | Crawler | Notes |
|---|---|---|---|
| `true` | — | `MockRedditCrawler` | Synthetic posts, fully offline |
| `false` | `false` | `HttpRedditCrawler` | Reddit public JSON API, no auth, parallel requests |
| `false` | `true` | `ParallelRedditCrawler` | Reddit JSON + Arctic Shift simultaneously |

**Arctic Shift** (`arctic-shift.photon-reddit.com/api`) is the community Pushshift successor — free, no registration, historical data up to 21 days back. Both sources run via `asyncio.gather` and are merged with cross-source deduplication.

Reddit's public JSON API requires no credentials but returns 403 more frequently since 2024. Arctic Shift is the reliable fallback.

---

## API Endpoints

Base URL: `http://localhost:8000`

### Match / Vorhersage

| Method | Path | Description |
|---|---|---|
| `GET`  | `/health` | Liveness check |
| `GET`  | `/api/matches` | Alle Spiele (`?group=A`, `?status=scheduled`) |
| `GET`  | `/api/matches/{id}` | Match-Details |
| `POST` | `/api/matches/{id}/crawl` | Crawl + Predict triggern (BackgroundTask) |
| `GET`  | `/api/matches/{id}/prediction` | Aktuelle Vorhersage (404 wenn keine) |
| `GET`  | `/api/matches/{id}/prediction/full` | Volle JSON-Antwort: Pro-Modell-Markets + Bootstrap-CIs (raw / isotonic / platt) + Pro-Faktor-Detail |
| `GET`  | `/api/matches/{id}/prediction/export` | CSV-Export |
| `GET`  | `/api/matches/{id}/sentiment` | Aktueller Sentiment-Snapshot |
| `GET`  | `/api/matches/{id}/sentiment/timeline` | Zeitreihe (`?hours=72&bucket_hours=6`) |
| `GET`  | `/api/matches/{id}/reddit` | Gecrawlte Posts (`?limit=50`) |

### Admin / Statistik (X-Admin-Key Header für Schreib-Endpoints)

| Method | Path | Description |
|---|---|---|
| `GET`   | `/api/admin/weights` | Aktuelle Faktor-Gewichte + aktive Flags |
| `PATCH` | `/api/admin/weights` | Gewichte ändern → atomarer Write in `runtime_weights.yaml` + Hot-Reload |
| `POST`  | `/api/admin/calibrate` | Isotonic + Platt-Kurven aus DB-History fitten |
| `POST`  | `/api/admin/train/xgboost` | xG-Predictor neu trainieren (BackgroundTask) |
| `POST`  | `/api/admin/train/lgbm` | LightGBM-Head neu trainieren (BackgroundTask) |
| `GET`   | `/api/admin/train/status` | Trainings-Status |
| `GET`   | `/api/admin/per_model_summary` | Pro-Modell-Übersicht über die letzten N Spiele |
| `GET`   | `/api/datasources/status` | Connector-Status + Mock/Live-Flag |
| `POST`  | `/api/datasources/{name}/toggle` | Live ↔ Mock pro Connector → atomarer Write in `runtime_flags.yaml` |
| `GET`   | `/api/stats/backtesting` | Brier / Log-Loss / Reliability-Kurve |
| `GET`   | `/api/stats/accuracy` | Trefferquote über alle finalisierten Matches |

**Prediction-Response enthält:** `home_win_prob`, `draw_prob`, `away_win_prob`, `confidence`, `home_xg`, `away_xg`, `over_15/25/35_prob`, `btts_prob`, `top_scores`, `recommended_bet`, `calibrated_*` (Isotonic), `platt_*`, `per_model_markets`, `confidence_intervals` (raw / isotonic / platt), `is_latest`.

---

## Architecture

```
POST /api/matches/{id}/crawl
        │
        ▼
RedditCrawler                ← Mock / Reddit-JSON / Arctic Shift (parallel)
        │
        ▼ list[FetchedPost]
PreprocessingPipeline        ← spaCy (NER), slang expansion, team attribution
        │
        ▼ ProcessedText
SentimentEnsemble            ← VADER + TextBlob (+ RoBERTa optional + NVIDIA LLM optional)
        │
DataSourceOrchestrator       ← parallel fan-out: openfootball, TheSportsDB, OpenLigaDB,
                                Wikidata, Weather (Open-Meteo), RSS-News (spaCy-NER batched
                                via asyncio.to_thread), FBref, Understat, FotMob, SofaScore,
                                Transfermarkt, football-data.org
        │
        ▼ FactorContext (live + cache + mock; per-match cached)
14 Factors (asyncio.gather)  ← FactorSignal(home_strength, away_strength, weight, kind=tilt|global)
        │
        ▼
FactorEnsemble               ← reno auf verfuegbare Faktoren, global × tilt (Floor 0.82)
        │
        ▼ λ_home_mult, λ_away_mult, ensemble_confidence
MatchPredictor               ← base_xg × Multiplier  →  build_all_goal_models →
                                  ├── DixonColes-Poisson
                                  ├── NegativeBinomial-DC
                                  └── GLM-Poisson (statsmodels)
                                ↓ blend (0.4 / 0.3 / 0.3) oder primary
                                ↓ bootstrap_markets (n=500, σ=0.15·xg)  →  p5/p50/p95
        │
analysis.calibration         ← Isotonic + Platt auf Punktwert UND auf p5/p50/p95 (K1)
        │
        ▼
DB: WM2026Match, RedditPost, SentimentScore, SentimentSnapshot,
    MatchPrediction (is_latest, calibrated_*, platt_*, per_model_markets,
                     confidence_intervals = {raw, isotonic, platt}),
    FactorSnapshot, DataSourceCache, TranslationCache
```

Sentiment ist engagement-gewichtet (`log(1+score) × log(1+comments) × upvote_ratio`) und temporal-decay-gewichtet (Posts näher am Kickoff zählen mehr).

---

## Project Structure

```
start.bat / start.ps1        ← One-click startup + first-time setup

backend/
├── main.py                  # FastAPI app + DB lifespan init
├── requirements.txt
├── .env.example
├── config/
│   ├── settings.py          # Pydantic settings (reads .env)
│   └── matches/             # 72 YAML match configs (group_a/ … group_l/)
├── crawler/
│   ├── mock_reddit.py       # FetchedPost dataclass + MockRedditCrawler
│   ├── http_reddit.py       # Reddit public JSON API (parallel via Semaphore)
│   ├── arctic_shift.py      # Arctic Shift historical API
│   └── parallel_reddit.py   # Orchestrates both crawlers in parallel
├── preprocessing/
│   ├── pipeline.py          # Main NLP pipeline
│   ├── text_cleaner.py      # URL/markup removal, Unicode normalization
│   └── sport_slang.py       # Football slang expansion dict
├── analysis/
│   ├── ensemble_scorer.py   # VADER + TextBlob ensemble (variance-based confidence)
│   ├── match_predictor.py   # Dixon-Coles Poisson
│   └── social_momentum.py   # Temporal-weighted sentiment + post velocity
├── db/
│   ├── models.py            # SQLAlchemy ORM (5 tables)
│   ├── database.py          # Async engine + session factory
│   └── schemas.py           # Pydantic response schemas
├── api/
│   ├── matches.py
│   ├── predictions.py
│   ├── reddit.py
│   ├── sentiment.py
│   └── health.py
└── services/
    └── match_service.py     # Orchestrates crawl → preprocess → score → predict

frontend/
├── src/
│   ├── pages/
│   │   ├── Dashboard.tsx    # Match grid with group filters
│   │   └── MatchDetail.tsx  # Full match analysis
│   ├── components/          # MatchCard, SentimentGauge, GoalDistChart, …
│   └── api/                 # Axios client + TanStack Query hooks
├── package.json
└── vite.config.ts
```

---

## Match Data

72 group-stage matches are pre-configured in `backend/config/matches/`. Each YAML includes team ELO ratings, season xG averages, form strings, Reddit sources (3 tiers), preprocessing rules, and custom VADER lexicon entries.

Re-generate from source data:
```bash
cd backend
python scripts/generate_match_configs.py
```

---

## v3.7 Verbesserungen (dieser Patch)

| Tag | Bereich | Was |
|-----|---------|-----|
| K1  | `services/match_service.py` + `analysis/calibration.transform_intervals` | Bootstrap-CIs werden mit derselben Isotonic/Platt-Kurve transformiert; persistiert als `{raw, isotonic, platt}` |
| K2  | `tests/analysis/test_calibration.py`, `test_bootstrap_ci.py`, `tests/test_service_v36.py` | Coverage für Calibration, Bootstrap, per-Model-Markets, End-to-End-Service |
| K3  | `utils/io.atomic_write_yaml` | Atomare YAML-Schreibvorgänge (tmp + os.replace, Windows-Retry) für `runtime_flags.yaml` + `runtime_weights.yaml` |
| K4  | `data_sources/rss_news._entities_batch` | spaCy `nlp.pipe(...)` in `asyncio.to_thread` — Event-Loop bleibt responsive |
| M1  | `analysis/factor_ensemble` | NaN/ε-Schutz in Strength-Division + Filter aus available-Set |
| M2  | `db/models.MatchPrediction.is_latest` | Soft-Delete: alte Vorhersagen werden bei jedem Re-Crawl auf `is_latest=False` demoted |
| M3  | `api/admin._run_training` | `finally`-Block setzt Status garantiert auf `error`, auch bei SystemExit/KeyboardInterrupt |
| M4  | `frontend/src/api/hooks.ts` | React-Query-`signal` an axios, `useTrainStatus` Polling stoppt automatisch |
| M5  | `frontend/src/components/CalibrationWidget` | NaN/leere-Reliability-Daten → Empty-State statt Recharts-Crash |
| M6  | `start.bat` / `start.ps1` | Symmetrische Soft-Fehler-Behandlung mit Setup-Warn-Banner |
| N1  | `frontend/src/i18n.tsx` | en/es/fr `factor.*` Keys vollständig |
| N2  | `.gitignore` (neu) | Secrets / DB / Logs / runtime artifacts aus VCS |
| N3  | `README.md` | dieses Doku-Update |
| N4  | `frontend/src/api/client.ts` + `vite-env.d.ts` | typsichere `import.meta.env`-Nutzung |

### v3.7.1 — K1 nachgeschärft

Live-Verifikation der v3.7-Patches hat gezeigt, dass die ursprüngliche K1-Entscheidung ("kein Σ=1-Renorm in `transform_intervals`") bei steilen Isotonic-Kurven die zentrale Invariante **bricht**: `apply()` renormalisiert den Punktwert, `transform_intervals` ohne Renorm lieferte ein CI-Band, das den Punkt nicht umschließt (Beispiel: `cal_home=0.4066` lag unter `p5=0.6083`).

**Fix in v3.7.1:** `transform_intervals` macht für 1X2-Triples jetzt eine per-Quantil-Σ=1-Renormalisierung. Das anschließende Sort pro Outcome fängt die seltene Quantil-Monotonie-Brechung ab, die ein per-Quantil-Renorm bei steilen Kurven verursachen kann. Bernoulli-Markets (`over_*`/`btts`) bleiben renorm-frei. Zero-Σ-Sonderfall fällt auf uniform (1/3 je) statt Division-by-Zero zurück.

Ergebnis (End-to-End live verifiziert auf Mock-Backend mit synthetischen Calibration-Artifacts): **`p5 ≤ cal_point ≤ p95` hält für alle 6 Kombinationen** ({isotonic, platt} × {home, draw, away}).

**Tests v3.7.1:**
- Neu: `test_transform_intervals_brackets_calibrated_point_property_K1` (sqrt-Kurve als adversariales Beispiel)
- Umformuliert: `*_renormalises_each_quantile`, `*_halving_curve_pulls_home_down`, `*_handles_zero_collapse_gracefully` (jetzt uniform-fallback)
- **Gesamt: 145 alt + 36 v3.7 + 1 v3.7.1 = 182 grün.**

## Phase 2 (nicht aktiv)

- **RoBERTa scorer** — `USE_ROBERTA=true` + `pip install transformers torch`
- **PostgreSQL + Alembic** — Produktions-DB-Migration
