  # 🔮 REDDITORAKEL — MASTER PROMPT v2.0
  ## WM 2026 Edition · Vollständige System-Spezifikation

  > **Verwendung:** Diesen Prompt vollständig in Cursor, Cline, Windsurf oder direkt an Claude/GPT übergeben.
  > **Ziel:** Ein produktionsreifes Python + React System das Reddit analysiert und für jedes WM 2026 Spiel Vorhersagen (Sieg/Niederlage/Unentschieden + Toranzahl) generiert.

  ---

  ## ═══ WISSENSCHAFTLICHE GRUNDLAGEN & QUELLEN ═══

  Du baust dieses System auf folgenden validierten Methoden auf — halte dich strikt daran:

  ### Sentiment-Analyse
  - **VADER** (Valence Aware Dictionary and sEntiment Reasoner): Optimiert für Social-Media-Slang, Abkürzungen, Emojis. Liefert compound score [-1, +1]. Quelle: Hutto & Gilbert (2014) ICWSM.
  - **GoEmotions / RoBERTa** (Google, 2020): Feinkörnige Emotions-Klassifikation auf 27 Reddit-spezifischen Kategorien. F1=0.64 (Ekman-Gruppen). Quelle: Demszky et al. 2020, ACL.
  - **TextBlob**: Sekundär-Validierung. Polarity [-1,+1] + Subjectivity [0,1].
  - **Ensemble**: `score = 0.5 * VADER + 0.3 * RoBERTa_positiv + 0.2 * TextBlob_polarity`
  - WICHTIG: Sentiment für Fußball-Kontext muss Sport-spezifische Negations-Behandlung haben ("not bad" = positiv, "could have scored" = negativ)

  ### Vorhersage-Modelle
  - **Poisson-Regression + Dixon-Coles-Korrektur**: Wissenschaftlich validierter Standard für Torvorhersage. Karlis & Ntzoufras (2003). Besonderheit: Dixon-Coles korrigiert Unter-Repräsentation von 0-0 und 1-0 Spielen.
  - **ML-Hybrid-Ansatz**: Zuerst XGBoost/Random Forest für Expected Goals (xG) vorhersagen, dann diese xG-Werte in zwei unabhängige Poisson-Verteilungen einspeisen. Quelle: Beat the Bookie Blog (2022), validiert durch Soccer Prediction Challenge 2017 (RPS=0.2063).
  - **Features für ML**: Reddit-Sentiment + Momentum + Engagement-Velocity + historische xG-Daten + Elo-Rating-Delta
  - **Benchmark**: R² = 0.99 bei VADER+TextBlob+Engagement-Features. Quelle: Trotter (2024), UT Austin, arXiv:2412.10298

  ### Reddit-Datenextraktion
  - **PRAW** (Python Reddit API Wrapper): Offiziell, OAuth-basiert, Rate-Limit-konform (60 req/min).
  - **Streaming-Mode** für Live-Spiele: `subreddit.stream.comments()` für Echtzeit-Analyse
  - **Limit**: PRAW kann maximal 1000 neueste Posts pro Subreddit abrufen
  - **Preprocessing-Pipeline** (spaCy + NLTK, Quelle: Brenndoerfer 2025):
    1. Lowercasing + Unicode-Normalisierung
    2. URL/Reddit-Formatting-Entfernung (`r/`, `u/`, `>`, Markdown)
    3. Tokenisierung via spaCy `en_core_web_sm`
    4. Sport-spezifische Sto
  ──── (1205 lines hidden) ────
  test_language_filter():
      result = pipeline.process("L'Angleterre est formidable aujourd'hui")
      assert result is None  # Französisch → überspringen

  # tests/test_prediction.py
  def test_poisson_probabilities_sum_to_one():
      matrix = dixoncoles.predict_goals_distribution(1.5, 1.0)
      assert abs(matrix.sum() - 1.0) < 0.001

  def test_btts_calculation():
      markets = dixoncoles.calculate_markets(matrix)
      assert 0 <= markets["btts"] <= 1
  ```

  ---

  ## ═══ SETUP & DEPLOYMENT ═══

  ```bash
  # .env.example — NIEMALS echte Werte committen!
  REDDIT_CLIENT_ID=your_client_id_here
  REDDIT_CLIENT_SECRET=your_client_secret_here
  REDDIT_USER_AGENT="RedditOrakel/2.0 by /u/YourUsername"
  REDDIT_USERNAME=your_reddit_username
  REDDIT_PASSWORD=your_reddit_password

  DATABASE_URL=postgresql+asyncpg://user:pass@localhost/redditorakel
  REDIS_URL=redis://localhost:6379

  # Für Entwicklung (SQLite Fallback)
  DATABASE_URL=sqlite+aiosqlite:///./redditorakel.db

  # Starten (3 Befehle):
  # 1. docker compose up -d postgres redis
  # 2. cd backend && pip install -r requirements.txt && python -m alembic upgrade head
  # 3. uvicorn main:app --reload
  # 4. cd frontend && npm install && npm run dev
  ```

  ---

  ## ═══ QUELLEN & REFERENZEN ═══

  | Bereich | Quelle | Methode | Link |
  |---------|--------|---------|------|
  | Reddit Sentiment | Trotter (2024), UT Austin | VADER+TextBlob+Regression, R²=0.99 | arXiv:2412.10298 |
  | GoEmotions | Demszky et al. (2020), ACL | RoBERTa, 58k Reddit-Comments, F1=0.69 | ACL Anthology 2020 |
  | Sports Reddit NLP | AnveshakR (2023), GitHub | GoEmotions + Decision-Tree | github.com/AnveshakR |
  | Poisson Modell | Karlis & Ntzoufras (2003) | Bivariate Poisson Distribution | JSR 2003 |
  | Dixon-Coles | Dixon & Coles (1997) | Inflated Poisson Correction | Applied Statistics |
  | ML-Hybrid xG | Beat the Bookie (2022) | XGBoost → Poisson Pipeline | beatthebookie.blog |
  | Soccer Prediction | Soccer Challenge 2017 | XGBoost + Pi-Ratings, RPS=0.2063 | xgfootball.substack.com |
  | xG Modell | Hewitt & Karakuş (2023) | Logistic Regression + Gradient Boosting | arXiv:2301.13052 |
  | Text Preprocessing | Brenndoerfer (2025) | spaCy Lemmatization Best Practices | mbrenndoerfer.com |
  | PRAW Reddit API | Reddit Developers | Official OAuth Wrapper | praw.readthedocs.io |
  | WM 2026 Daten | FIFA / ESPN | Alle 48 Teams, 12 Gruppen | espn.com / fifa.com |

  ---

  *RedditOrakel v2.0 — WM 2026 Edition*
  *Erstellt mit validierten wissenschaftlichen Methoden*
  *Alle 104 WM-Spiele mit eigener Config-Datei*

  Listed 1 directory

Das Verzeichnis ist leer. Der Spec ist enorm — grob geschätzt 120+ Dateien (Backend mit Crawler/Preprocessing/Sentiment/ML/DB/API + Frontend mit ~25 React-Komponenten + 72 Match-YAMLs für alle WM-Spiele + Docker/Nginx/Tests). Das ist mehrere Tage Arbeit, nicht ein Turn.

Bevor ich anfange, muss ich wissen, welcher Teil zuerst gebaut werden soll — sonst baue ich stundenlang am falschen Ende.

● User answered Claude's questions:
· Der Spec ist riesig (120+ Dateien). Womit soll ich starten? → Vertikaler MVP (ein Spiel end-to-end)
· Hast du schon Reddit-API-Credentials (Client ID/Secret), oder fange ich mit Mock-Daten an? → Noch keine Credentials
· Postgres/Redis lokal verfügbar, oder erstmal SQLite-Fallback? → SQLite-Fallback (Entwicklung)

Klar — vertikaler MVP für ENG vs CRO, SQLite-Fallback, Mock-Crawler. Ich baue jetzt:

Backend: FastAPI + async SQLAlchemy + Mock-Crawler + Preprocessing (spaCy/Slang/Negationen) + VADER+TextBlob-Ensemble + Dixon-Coles-Poisson → API
Frontend: Vite/React/TS + TanStack Query + MatchCard + SentimentGauge + GoalDistChart
Skip im MVP: RoBERTa (Modell-Download, kommt in Phase 2), XGBoost (Daten fehlen — Heuristik aus Elo+xG), Redis, Docker, Alembic

Lege los mit Backend-Konfig und DB.

● Write(requirements.txt)
Wrote 16 lines to requirements.txt
fastapi==0.115.0
]==0.30.6
pydantic==2.9.2
s==2.5.2
io]==2.0.35
aiosqlite==0.20.
PyYAML==6.0.2
python-dotenv==1
vaderSentiment==
textblob==0.18.0
… +10 lines

● Write(.env.example)
Wrote 19 lines to .env.example
# Reddit API (lea
 mock crawler is
used)
REDDIT_CLIENT_SEC
REDDIT_USER_AGENT
=RedditOrakel/2.0
me
REDDIT_USERNAME=

te for
… +22 lines

● Write(config\__init__.py)
Wrote 1 lines to config\__init__.py
(No content)

● Write(config\settings.py)
Wrote 37 lines to config\settings.py
from pathlib impo
from typing impor
from pydantic imp
ort Field
tings import Base
sConfigDict
"react-router-do

import {
  usePrediction,
,
  useSentimentTi
meline,
l,
ooks";
… +316 lines

● Write(~\Desktop\Reddit wmanalyserv2\frontend\src\App.tsx)
Wrote 25 lines to ..\frontend\src\App.tsx
import { Route, R
m "react-router-d
om";
import { Dashboar
/Dashboard";
import { MatchDet
es/MatchDetail";

nction App() {
    <div cl
… +43 lines
You've hit your session limit · resets 1:10am (Europe/Berlin)
/upgrade to increase your usage limit.

✻ Brewed for 15m 14s · 1 shell still running

────────────────