# RedditOrakel v2.1 - Vollstaendige Fehleranalyse & Verbesserungsplan

> Stand: 2026-05-31 | Basis: MVP v2.1 (104 Match-Configs inkl. KO-Runden, Mock+HTTP+ArcticShift Crawler, VADER+TextBlob+RoBERTa, Dixon-Coles, React-Dashboard mit Advanced Analytics, Scheduler, WC-API-Sync)

---

## 1. FEHLER (Bugs & Korrekturbedarf)

### 1.1 Kritisch

#### BUG-01: N+1 Query-Problem beim Post-Import
**Datei:** `backend/services/match_service.py:135-137`
**Problem:** Fuer jeden gecrawlten Post wird ein separater DB-Query (`await session.get(RedditPost, post_pk)`) ausgefuehrt, um zu pruefen ob er schon existiert. Bei 200+ Posts pro Crawl entstehen 200+ einzelne DB-Roundtrips.
**Fix:** Alle existierenden `post_id`s fuer diesen Match vorab in einem einzigen Query laden und gegen ein Set pruefen:
```python
existing_ids = {r[0] for r in (await session.execute(
    select(RedditPost.id).where(RedditPost.match_id == match.id)
)).all()}
# Dann: if post_pk in existing_ids: continue
```

#### BUG-02: RoBERTa-Werte semantisch falsch gespeichert
**Datei:** `backend/analysis/ensemble_scorer.py:92-94`
**Problem:** `roberta_positive = max(0.0, roberta_scalar)` und `roberta_negative = min(0.0, roberta_scalar)` — aber `roberta_scalar` ist ein Polarity-Mapping (-1..+1) aus der Emotion-Zuordnung, keine echte Klassen-Wahrscheinlichkeit (0..1). Die DB-Spalten `roberta_positive/neutral/negative` suggerieren Klassen-Wahrscheinlichkeiten. `roberta_neutral` ist immer `None`.
**Fix:** RoBERTa-Pipeline mit `top_k=None` aufrufen, um alle 7 Emotions-Wahrscheinlichkeiten zu erhalten. Dann `roberta_positive` = Summe(joy, surprise), `roberta_neutral` = neutral-Score, `roberta_negative` = Summe(anger, sadness, fear, disgust).

#### BUG-03: Elo-Nudge doppelt angewendet
**Datei:** `backend/analysis/match_predictor.py:63-64`
**Problem:** `elo_nudge_home = 1.0 + 0.0008 * elo_delta` UND `elo_nudge_away = 1.0 - 0.0008 * elo_delta`. Bei 200 Elo-Differenz erhaelt Home +16% xG UND Away -16% xG. Multiplikativ ergibt das ~35% Verzerrung statt der beabsichtigten ~16%. Der Elo-Effekt ist doppelt so stark wie gewollt.
**Fix:** Faktor halbieren (0.0004 pro Seite) oder nur eine Seite nudgen.

#### BUG-04: Sprach-Gewichtung veraendert RoBERTa-Einfluss falsch
**Datei:** `backend/analysis/ensemble_scorer.py:67-69`
**Problem:** Bei nicht-englischen Texten wird VADER-Gewicht * 0.6, TextBlob-Gewicht * 1.4, aber RoBERTa-Gewicht bleibt unveraendert. Das englisch-trainierte RoBERTa-Modell ist bei nicht-englischen Texten (auch wenn uebersetzt) weniger zuverlaessig, erhaelt aber durch die Renormalisierung relativ MEHR Einfluss.
**Fix:** RoBERTa-Gewicht bei `source_language != "en"` ebenfalls reduzieren (z.B. * 0.5).

### 1.2 Mittel

#### BUG-05: Platzhalter-Daten in allen Match-Configs
**Datei:** `backend/config/matches/*//*.yaml` (alle 104 Dateien)
**Problem:** `form_last5: [D, D, D, D, D]` und `world_ranking: 50` fuer ALLE Teams. Das bedeutet: Form-Nudge und Ranking haben NULL Einfluss auf die Vorhersage — alle Teams starten mit identischen Werten.
**Auswirkung:** Die Vorhersage basiert nur auf Elo + xG + Sentiment. Form-Faktor ist komplett wirkungslos.
**Fix:** Echte Daten pro Team einpflegen (z.B. via FIFA API, ESPN, Transfermarkt) oder ein Update-Script das die YAMLs automatisch aktualisiert.

#### BUG-06: Fire-and-forget asyncio Task ohne Referenz
**Datei:** `backend/api/predictions.py:84`
**Problem:** `asyncio.create_task(_background_crawl(match_id))` — der Task-Handle wird nicht gespeichert. Bei `CancelledError` (Server-Shutdown waehrend laufendem Crawl) wird der Exception-Handler nicht erreicht und `_CRAWL_STATUS` bleibt auf "running" haengen.
**Fix:** Task-Referenz in einem Dict speichern, im Lifespan-Shutdown graceful abwarten:
```python
_CRAWL_TASKS: Dict[str, asyncio.Task] = {}
_CRAWL_TASKS[match_id] = asyncio.create_task(_background_crawl(match_id))
```

#### BUG-07: Bot-Filter Regex zu breit
**Datei:** `backend/preprocessing/bot_filter.py:23`
**Problem:** Pattern `^auto[_\-]?` matched Usernamen wie "autograph_fan", "autonomous_driver", "autobahn_enjoyer". Legitime User werden faelschlicherweise als Bots gefiltert.
**Fix:** Pattern praezisieren: `^auto[_\-]?(mod|moderator|tldr|reply|bot|remove|post)`.

#### BUG-08: O(n*m) Match-Lookup beim WC-API-Sync
**Datei:** `backend/services/wc_sync_service.py:68-96`
**Problem:** Fuer jedes API-Spiel wird ueber ALLE DB-Matches iteriert (innere Schleife). Bei 104 Matches: O(n*m) = ~10.800 Vergleiche.
**Fix:** Lookup-Dict vorab erstellen:
```python
by_teams = {(m.home_team, m.away_team): m for m in db_matches.values()}
match = by_teams.get((home_code, away_code))
```

#### BUG-09: httpx Client wird pro Retry neu erstellt
**Datei:** `backend/crawler/wc2026_api.py:33-45`
**Problem:** In der Retry-Schleife wird bei jedem Versuch ein neuer `httpx.AsyncClient` erstellt und zerstoert (`async with`). Das verhindert Connection-Pooling und verschwendet TLS-Handshakes.
**Fix:** Client als Modul-Singleton oder als Klassen-Attribut vorhalten:
```python
_CLIENT = httpx.AsyncClient(timeout=_TIMEOUT, verify=_ssl_context())
```

#### BUG-10: Slang-Regex werden bei jedem Aufruf neu kompiliert
**Datei:** `backend/preprocessing/sport_slang.py:9`
**Problem:** `expand_slang()` kompiliert fuer JEDEN Slang-Term bei JEDEM Aufruf ein neues Regex-Pattern via `re.compile` (implizit durch `re.sub`). Bei 20 Slang-Terms und 200 Posts pro Crawl = 4.000 Regex-Kompilierungen.
**Fix:** Patterns bei Pipeline-Init kompilieren und als Dict `{compiled_pattern: replacement}` cachen.

#### BUG-11: Geloeschte Autoren nicht gefiltert
**Datei:** `backend/preprocessing/bot_filter.py:48-52`
**Problem:** `is_bot_author("[deleted]")` gibt `False` zurueck. Posts von geloeschten Accounts haben keinen nachvollziehbaren Kontext und koennten Spam sein.
**Fix:** `[deleted]` und `[removed]` zu den gefilterten Autoren hinzufuegen.

### 1.3 Gering

#### BUG-12: Log-Meldung "crawl_begin" steht nach dem Crawl
**Datei:** `backend/services/match_service.py:125`
**Problem:** `log.info("crawl_begin", match_id=match.id, posts_fetched=len(fetched))` wird NACH dem Crawl-Aufruf ausgegeben. Missleitend in den Logs.
**Fix:** Vor den Crawler-Aufruf verschieben und in zwei Log-Zeilen trennen (begin + done).

#### BUG-13: Redundante DB-Spalten goals_expected
**Datei:** `backend/services/match_service.py:359-360`
**Problem:** `home_goals_expected = pred.home_xg` und `away_goals_expected = pred.away_xg` — exakte Kopien, kein eigenstaendiger Wert.
**Fix:** Spalten entfernen oder mit einem separaten Modell (z.B. Poisson-Mean vs. adjusted xG) befuellen.

#### BUG-14: MD5 fuer Post-ID-Generierung mit nur 10-12 Chars
**Datei:** `backend/crawler/mock_reddit.py:99`, `backend/crawler/http_reddit.py:33`
**Problem:** MD5-Hash abgeschnitten auf 10-12 Hex-Chars = 40-48 Bit Entropie. Bei grossen Datenmengen erhoehte Kollisionsgefahr.
**Fix:** Volle Reddit-Base36-ID als Key nutzen: `f"{subreddit}:{reddit_id}"`.

---

## 2. VERBESSERUNGEN (Bestehende Funktionen optimieren)

### 2.1 Models & Analyse

#### IMPROVE-01: Sentiment-Ensemble dynamisch gewichten
**Aktuell:** Feste Gewichte (VADER 0.55, TextBlob 0.25, RoBERTa 0.20).
**Verbesserung:**
- Text-Laenge-basiert: Kurze Texte (< 20 Woerter) → VADER staerker; lange Texte → RoBERTa staerker
- Konfidenz-gewichtete Fusion: Scorer mit hoher Varianz in ihrem Output bekommen weniger Gewicht
- Kalibrierung gegen ein manuell annotiertes Test-Set (~200 gelabelte Sport-Reddit-Posts)
**Aufwand:** Mittel

#### IMPROVE-02: Sarkasmus-Erkennung
**Aktuell:** Sarkasmus wird als aufrichtige Meinung gewertet ("oh ja, BESTIMMT gewinnen die" → positiv).
**Verbesserung:**
- Basis-Heuristik: ALL-CAPS + positive Woerter, Reddit `/s`-Tag, Anfuehrungszeichen
- Fortgeschritten: `cardiffnlp/twitter-roberta-base-irony` als optionaler Classifier (aehnlich wie RoBERTa: lazy-loaded, Feature-Flag)
**Aufwand:** Gering (Heuristik) bis Mittel (ML-Modell)

#### IMPROVE-03: Sport-spezifisches Sentiment-Modell
**Aktuell:** Generisches Emotion-Modell (`j-hartmann/emotion-english-distilroberta-base`).
**Verbesserung:**
- Drop-in Wechsel zu `cardiffnlp/twitter-roberta-base-sentiment-latest` (trainiert auf Social-Media, naeher am Reddit-Stil)
- Langfristig: Fine-Tuning auf Sport-Reddit-Daten mit Upvote-basiertem Pseudo-Labeling
**Aufwand:** Gering (Drop-in) bis Hoch (Fine-Tuning)

#### IMPROVE-04: Dixon-Coles Modell erweitern
**Aktuell:** Poisson mit statischem rho=0.1, heuristischem xG.
**Verbesserung:**
- Heimvorteil-Faktor: Historisch ~0.12-0.18 xG Aufschlag bei WM-Spielen fuer "Heim"-Team (Venue-basiert)
- Venue-Faktoren: Hoehenlage (Mexico City 2240m → Ausdauer-Malus), Klima, Reisezeit
- Ruhetage-Faktor: Team mit 2 Tagen Pause vs. Team mit 4 Tagen → xG-Adjustment
- Negative-Binomial statt Poisson fuer bessere Varianz-Modellierung (Fussball hat haeufiger 0-Tore-Spiele als Poisson vorhersagt)
**Aufwand:** Mittel

#### IMPROVE-05: Engagement-Weight-Formel verbessern
**Aktuell:** `log(1+score) * log(1+comments) * upvote_ratio`
**Verbesserung:**
- Tier-basierter Multiplikator: Tier-1 (r/soccer, r/worldcup) = 1.0x, Tier-2 (r/england) = 1.5x (Fans wissen mehr), Tier-3 (national) = 0.8x (weniger fussball-spezifisch)
- Author-Reputation: Wiederkehrende Poster in Team-Subs hoeher gewichten (Expertise-Proxy)
- Comment-Sentiment: Post mit 50 wuetenden Antworten hat andere Bedeutung als Post mit 50 zustimmenden
**Aufwand:** Mittel

### 2.2 Daten & Crawling

#### IMPROVE-06: Inkrementelles Crawling
**Aktuell:** Jeder Crawl holt alle Posts neu und prueft einzeln ob sie existieren (BUG-01).
**Verbesserung:**
- `last_crawled_at` Timestamp pro Match in DB speichern
- Reddit API `after`-Timestamp nutzen fuer zeitliches Filtern
- Arctic Shift: `after` Parameter bereits vorhanden, dynamisch auf letzten Crawl-Zeitpunkt setzen
- Nur neue Posts seit letztem Crawl verarbeiten → 80%+ weniger DB-Queries
**Aufwand:** Gering

#### IMPROVE-07: min_post_score aus YAML-Config tatsaechlich nutzen
**Aktuell:** Die YAML-Config enthaelt `min_post_score: 10` pro Subreddit, aber `HttpRedditCrawler` ignoriert diesen Wert. Nur `score < 0` wird in `_parse_post()` gefiltert.
**Verbesserung:** Config-Wert durchreichen und in `_parse_post()` anwenden.
**Aufwand:** Gering

#### IMPROVE-08: Comment-Crawling fuer echten Crawler aktivieren
**Aktuell:** `HttpRedditCrawler._fetch_comments()` existiert als Methode, wird aber NIRGENDS aufgerufen. YAML-Configs haben `include_comments: true` und `comment_depth: 2`, beides wird ignoriert.
**Verbesserung:**
- Fuer Tier-2-Subreddits: Top-Posts (score > 50) identifizieren, deren Kommentare crawlen
- Comments sind sentiment-reicher als Posts (direktere Reaktionen, weniger Link-Posts)
- Comment-Depth begrenzen auf 2 (wie in Config) um Noise zu reduzieren
**Aufwand:** Mittel

#### IMPROVE-09: Rate-Limiting robuster machen
**Aktuell:** Feste 0.5s Pause, Semaphore mit 8 parallel, bei 429 einmal `sleep(10)` und Return `None`.
**Verbesserung:**
- Exponential Backoff bei 429-Responses (1s → 2s → 4s → 8s → Abbruch)
- Adaptive Rate basierend auf `X-Ratelimit-Remaining` Response-Header
- Circuit-Breaker: Nach 3 aufeinanderfolgenden 429/403 den gesamten Crawl-Batch fuer diesen Subreddit abbrechen
- Retry-Count als Metric loggen
**Aufwand:** Mittel

#### IMPROVE-10: Uebersetzungs-Caching und -Qualitaet
**Aktuell:** Google Translate via `deep_translator`, kein Caching, synchron via `asyncio.to_thread`.
**Verbesserung:**
- Hash-basierter Cache: `{sha256(text+lang): translated_text}` in DB oder Redis
- Fallback auf DeepL API fuer europaeische Sprachen (deutlich bessere Qualitaet bei DE, FR, ES)
- Sprach-Konfidenz: `langdetect` ist bei kurzen Texten (< 50 Chars) unzuverlaessig → nur uebersetzen wenn Konfidenz > 0.8
**Aufwand:** Mittel

### 2.3 Datenspeicherung

#### IMPROVE-11: Datenbank-Indizes hinzufuegen
**Aktuell:** Nur `reddit_posts.post_id` und `post_flags.{post_id, match_id}` sind indiziert.
**Verbesserung:** Folgende Indizes fehlen und verursachen Full-Table-Scans:
```sql
CREATE INDEX ix_reddit_posts_match_id ON reddit_posts (match_id);
CREATE INDEX ix_sentiment_scores_match_id ON sentiment_scores (match_id);
CREATE INDEX ix_sentiment_snapshots_match_time ON sentiment_snapshots (match_id, snapshot_time DESC);
CREATE INDEX ix_match_predictions_match_time ON match_predictions (match_id, generated_at DESC);
CREATE INDEX ix_reddit_posts_match_created ON reddit_posts (match_id, created_utc DESC);
```
**Aufwand:** Gering (5 Minuten)

#### IMPROVE-12: Alembic-Migrationen einrichten
**Aktuell:** `_add_missing_columns()` fuehrt rohe `ALTER TABLE` aus, nur fuer SQLite.
**Verbesserung:**
- Alembic initialisieren mit `alembic init`
- Erste Migration: Alle 6 bestehenden Tabellen
- Neue Spalten ueber Alembic-Revisionen statt Auto-ALTER
- Notwendig fuer PostgreSQL-Migration und Multi-Entwickler-Setup
**Aufwand:** Mittel

#### IMPROVE-13: PostgreSQL-Support fuer Produktion
**Aktuell:** Nur SQLite, einige SQLite-spezifische Annahmen (`_sqlite_type()`, `_add_missing_columns()`).
**Verbesserung:**
- `DATABASE_URL` akzeptiert bereits Postgres-URLs, aber Code-Anpassungen noetig
- PostgreSQL bietet: echte Concurrent Writes, JSONB-Indexierung, Window Functions, Full-Text-Search
- Docker-Compose mit `postgres:16` + `pgbouncer` fuer Connection-Pooling
**Aufwand:** Mittel

### 2.4 API & Backend

#### IMPROVE-14: Pagination fuer Match-Liste
**Aktuell:** `GET /api/matches` gibt ALLE 104 Matches zurueck.
**Verbesserung:**
- `limit` und `offset` Parameter
- `phase`-Filter erweitern: "group_stage", "round_of_32", "quarter_finals", etc.
- Sortierung: live > scheduled (nach Kickoff) > finished (nach Kickoff absteigend)
**Aufwand:** Gering

#### IMPROVE-15: Caching-Layer
**Aktuell:** Jeder Request liest direkt aus der DB, kein HTTP-Cache.
**Verbesserung:**
- In-memory Cache (oder Redis) fuer:
  - Match-Liste: TTL 60s
  - Predictions: TTL 5min, invalidiert bei neuem Crawl
  - Sentiment-Snapshots: TTL 5min
- `ETag` / `Last-Modified` Headers fuer conditional HTTP-Requests
- `Cache-Control: max-age=300` fuer statische Predictions (kein laufender Crawl)
**Aufwand:** Mittel

#### IMPROVE-16: Input-Validierung bei record_result
**Datei:** `backend/api/analytics.py:124-168`
**Problem:** `home_score` und `away_score` sind unvalidierte `int` Query-Parameter. Negative Scores oder unrealistische Werte (100-0) werden akzeptiert.
**Fix:** Pydantic Request-Body mit `ge=0, le=20` Constraints.
**Aufwand:** Gering

#### IMPROVE-17: API-Sicherheit
**Aktuell:** Keine Authentifizierung, keine Rate-Limits auf API-Ebene.
**Verbesserung:**
- Rate-Limiting: `slowapi` mit 60 req/min pro IP fuer GET, 5 req/min fuer POST
- Admin-Endpoints (`/result`, `/crawl`) hinter API-Key oder JWT schuetzen
- CORS: Dynamisch statt hardcoded Localhost-URLs
**Aufwand:** Mittel

### 2.5 Frontend

#### IMPROVE-18: KO-Phasen im Dashboard
**Aktuell:** Nur Gruppenfilter (A-L). KO-Spiele sind nicht filterbar.
**Verbesserung:**
- Phase-Tab-Leiste: "Gruppenphase | Achtelfinale | Viertelfinale | Halbfinale | Finale"
- Bei KO-Phase: Turnierbaum-Ansicht statt Grid
**Aufwand:** Gering-Mittel

#### IMPROVE-19: Match-Vergleich Side-by-Side
**Aktuell:** Nur Einzelansicht pro Spiel.
**Verbesserung:**
- Checkbox-Auswahl auf Dashboard-Cards, "Vergleichen"-Button
- Split-Screen mit Predictions, Sentiment, Odds nebeneinander
- Use-Case: "Welches Spiel heute Abend ist interessanter?"
**Aufwand:** Mittel

#### IMPROVE-20: Dark Mode
**Aktuell:** Nur Light-Theme.
**Verbesserung:**
- Tailwind `dark:` Klassen auf allen Komponenten
- System-Preference via `prefers-color-scheme` respektieren
- Toggle im Header
**Aufwand:** Gering-Mittel

#### IMPROVE-21: Error-Handling bei fehlender API-Verbindung
**Aktuell:** Axios-Fehler als rohe Fehlermeldungen.
**Verbesserung:**
- Globaler Axios-Interceptor mit benutzerfreundlichen deutschen Fehlermeldungen
- Retry-Button bei Netzwerkfehlern
- Offline-Indicator im Header
- Toast-Notifications fuer temporaere Fehler
**Aufwand:** Gering

---

## 3. ERWEITERUNGEN (Neue Features)

### 3.1 Zusaetzliche Datenquellen

#### EXTEND-01: Twitter/X-Integration
**Beschreibung:** Twitter/X neben Reddit als zweite grosse Sentiment-Quelle.
**Umsetzung:**
- Twitter API v2 mit Bearer Token
- Suche nach Team-Hashtags (#ENG, #CRO, #WorldCup2026, #WM2026)
- Eigener `TwitterCrawler` analog zu `HttpRedditCrawler`
- Separater Tier (Tier-4) in der Config
- Anpassung des Sentiment-Ensembles (Twitter-Texte kuerzer → VADER staerker)
**Aufwand:** Mittel (API-Zugang kostenpflichtig, strenge Rate-Limits)

#### EXTEND-02: Wettquoten als Prediction-Feature
**Beschreibung:** Bookmaker-Odds als zusaetzliches Signal — Maerkte aggregieren enormes Wissen.
**Umsetzung:**
- API-Client fuer `the-odds-api.com` (Free Tier: 500 Requests/Monat, reicht fuer WM)
- Implizite Wahrscheinlichkeiten berechnen inkl. Overround/Vig-Korrektur
- Neues Feature in `PredictionInput`: `market_home_prob`, `market_draw_prob`, `market_away_prob`
- Blending: Markt-Wahrscheinlichkeiten als "Prior", Sentiment als "Bayesian Update"
- Abweichungs-Score: Wenn unser Modell stark vom Markt abweicht → entweder Value-Bet oder Modell-Fehler
**Aufwand:** Gering-Mittel

#### EXTEND-03: Historische Head-to-Head-Daten
**Beschreibung:** Vergangene Begegnungen zwischen den Teams als Feature fuer bessere Predictions.
**Umsetzung:**
- Datenquelle: `football-data.org` API (kostenlos, Daten seit 1872)
- H2H-Bilanz: Siege/Unentschieden/Niederlagen der letzten 10 Begegnungen
- H2H-Torverhaeltnis und avg Goals
- Neue Features in `PredictionInput`: `h2h_home_wins`, `h2h_draws`, `h2h_away_wins`, `h2h_avg_goals`
**Aufwand:** Gering

#### EXTEND-04: Spieler-Verfuegbarkeit (Injuries/Suspensions)
**Beschreibung:** Ausfall von Schluesselspieler massiv beeinflusst Spielausgang.
**Umsetzung:**
- Datenquelle: Transfermarkt-Scraping oder ESPN Injury Report API
- Impact-Score pro Spieler (gewichtet nach Marktwert/Einsatzminuten)
- xG-Malus basierend auf kumulativem Impact der fehlenden Spieler
- Optional: NER auf Reddit-Posts ("Kane injured", "Modric out") fuer automatische Erkennung
**Aufwand:** Hoch

### 3.2 Erweiterte ML-Modelle

#### EXTEND-05: XGBoost/LightGBM Predictor
**Beschreibung:** Den heuristischen xG-Blender durch ein trainiertes ML-Modell ersetzen.
**Umsetzung:**
- Training auf historischen WM/EM/CL-Daten (Features: Elo, xG, Form, Sentiment, Odds, H2H)
- Target: Torergebnis oder 1X2-Outcome
- Temporale Cross-Validation (keine zukuenftigen Daten im Training)
- Feature-Importance zeigt welche Signale am wertvollsten sind
- Fallback auf heuristisches Modell wenn Trainingsdaten fehlen
- Datei: `models_ml/xg_predictor.py` (ersetzt Heuristik in `match_predictor.py`)
**Voraussetzung:** Mindestens 300-500 historische Spiele mit xG-Daten
**Aufwand:** Hoch

#### EXTEND-06: Aspect-Based Sentiment Analysis (ABSA)
**Beschreibung:** Pro-Aspekt Sentiment statt nur global positiv/negativ.
**Aspekte:** Offensive, Defensive, Trainer, Fitness, Moral, Taktik
**Umsetzung:**
- SpaCy Dependency-Parsing + Sport-Aspekt-Lexikon
- Pro Aspekt separaten Sentiment-Score berechnen
- Dashboard-Widget: "Fans positiv ueber Englands Offensive (+0.7), negativ ueber Defensive (-0.3)"
- Aspekt-gewichtetes xG: Negatives Defensiv-Sentiment → hoehere xG-conceded
**Aufwand:** Hoch

#### EXTEND-07: Sentiment-Drift-Alarm (Breaking-News-Detektion)
**Beschreibung:** Automatische Benachrichtigung bei ploetzlichen Stimmungswandeln.
**Umsetzung:**
- Aufbauend auf `trend_analyzer.py` Anomaly-Detection (existiert bereits!)
- Trigger: z_score > 3.0 UND post_velocity > 2x Durchschnitt
- WebSocket-Push oder E-Mail-Notification
- Use-Cases: Verletzungsnachricht, Aufstellungs-Leak, ueberraschende Pressekonferenz
- Frontend: "Breaking"-Badge auf betroffener Match-Card
**Aufwand:** Mittel

### 3.3 Neue Backend-Features

#### EXTEND-08: WebSocket fuer Live-Match-Updates
**Beschreibung:** Echtzeit-Updates waehrend laufender Spiele.
**Umsetzung:**
- FastAPI WebSocket-Endpoint: `ws://host/ws/match/{match_id}`
- Push-Events: Score-Update, Sentiment-Refresh, Prediction-Recalculation
- Alternative (einfacher): Server-Sent Events (SSE) via `GET /api/matches/{id}/stream`
- Frontend: React WebSocket-Hook mit Auto-Reconnect
- Backend: Crawl alle 2 Min waehrend Live-Spiel, Push delta per WS
**Aufwand:** Mittel

#### EXTEND-09: Batch-Crawl-Endpoint
**Beschreibung:** Alle anstehenden Spiele mit einem Klick crawlen.
**Umsetzung:**
- `POST /api/crawl/batch?lookahead_hours=48`
- Priorisierung: Naechstes Spiel zuerst
- Progress-Reporting via SSE oder Polling
- Basis existiert bereits in `scheduled_jobs.py:crawl_upcoming_matches()`
- Nur ein API-Endpoint + Progress-Tracking noetig
**Aufwand:** Gering

#### EXTEND-10: Prediction-Backtesting-Framework
**Beschreibung:** Systematische Genauigkeits-Auswertung nach Turnierphase.
**Umsetzung:**
- Brier-Score und Log-Loss als Hauptmetriken (nicht nur "1X2 richtig/falsch")
- Kalibrierungskurve: "70% Vorhersage" → trifft es in 70% der Faelle zu?
- Per-Feature-Analyse: "Wie viel hat Sentiment zur Genauigkeit beigetragen vs. nur Elo+xG?"
- Vergleich gegen Bookmaker-Odds (Benchmark)
- `GET /api/stats/backtesting` Endpoint + PDF/CSV-Export
- Dashboard-Widget mit Kalibrierungsplot
**Aufwand:** Mittel

#### EXTEND-11: User-Accounts und Tipp-Spiel
**Beschreibung:** Nutzer koennen eigene Tipps abgeben und gegen das Modell antreten.
**Umsetzung:**
- OAuth2 Login (Google, GitHub, optional Discord)
- Tipp-Eingabe: 1X2 oder exaktes Ergebnis
- Leaderboard: User-Trefferquote vs. Modell-Trefferquote
- Punkte-System: 3 Punkte fuer exaktes Ergebnis, 1 Punkt fuer richtige Tendenz
- Gamification: Streaks, Badges ("Gruppensieger", "Pokal-Prophet")
**Aufwand:** Hoch

### 3.4 Neue Frontend-Features

#### EXTEND-12: Turnierbaum-Visualisierung
**Beschreibung:** Interaktiver Bracket-View fuer die KO-Phase (32 → 16 → 8 → 4 → Final).
**Umsetzung:**
- SVG-basierter Turnierbaum mit D3.js oder custom React-Komponente
- Klick auf Paarung oeffnet Match-Detail
- Farbkodierung nach Vorhersage-Konfidenz (gruen = sicher, rot = unklar)
- Animierter Fortschritt wenn Ergebnisse eintreffen
**Aufwand:** Mittel

#### EXTEND-13: Sentiment-Heatmap
**Beschreibung:** Alle Spiele auf einen Blick — welche sind "heiss" diskutiert?
**Umsetzung:**
- X-Achse: Zeit (letzte 72h), Y-Achse: Spiel, Farbe: Sentiment-Intensitaet
- Recharts oder D3.js Heatmap-Komponente
- Klick auf Zelle oeffnet Detail
- Bubble-Size: Post-Velocity (viele Posts = grosse Bubble)
**Aufwand:** Mittel

#### EXTEND-14: PWA & Mobile-Optimierung
**Aktuell:** Responsive, aber kein PWA-Support.
**Verbesserung:**
- Service-Worker fuer Offline-Faehigkeit (cached Matches + letzte Predictions)
- Installierbar auf Homescreen (manifest.json)
- Bottom-Navigation auf Mobile
- Push-Notifications fuer Live-Spiel-Events
- Swipe-Gesten fuer Match-Navigation
**Aufwand:** Mittel

#### EXTEND-15: Multi-Sprach-Support (i18n)
**Aktuell:** Deutsch hardcoded in UI.
**Verbesserung:**
- `react-i18next` fuer DE/EN/ES/FR
- Sprache automatisch nach Browser-Einstellung
- Backend-API bleibt Englisch, Frontend uebersetzt Labels
- Emotion-Labels (euphorisch, skeptisch, etc.) in alle Sprachen
**Aufwand:** Mittel

---

## 4. PRIORISIERTE UMSETZUNGSREIHENFOLGE

### Phase 1: Bugfixes (1-2 Tage)
| # | Task | Prio | Aufwand |
|---|------|------|---------|
| 1 | BUG-01: N+1 Query fix (Batch-Existenz-Check) | Kritisch | 30 Min |
| 2 | BUG-03: Elo-Nudge Doppel-Anwendung korrigieren | Kritisch | 15 Min |
| 3 | BUG-05: Echte Team-Daten einpflegen | Mittel | 2-4 Std |
| 4 | BUG-07: Bot-Filter Regex praezisieren | Mittel | 15 Min |
| 5 | BUG-10: Slang-Regex cachen | Mittel | 30 Min |
| 6 | BUG-08: O(n*m) Lookup → Dict | Mittel | 15 Min |
| 7 | BUG-09: httpx Client wiederverwenden | Mittel | 15 Min |
| 8 | BUG-11: [deleted] Autoren filtern | Gering | 5 Min |
| 9 | BUG-12: Log-Reihenfolge korrigieren | Gering | 5 Min |

### Phase 2: Quick Wins (2-3 Tage)
| # | Task | Aufwand |
|---|------|---------|
| 1 | IMPROVE-11: DB-Indizes (5 Indizes) | 30 Min |
| 2 | IMPROVE-07: min_post_score Config nutzen | 30 Min |
| 3 | IMPROVE-06: Inkrementelles Crawling | 2 Std |
| 4 | IMPROVE-16: Input-Validierung | 15 Min |
| 5 | IMPROVE-14: Match-Pagination | 1 Std |
| 6 | EXTEND-09: Batch-Crawl-Endpoint | 1 Std |
| 7 | IMPROVE-21: Frontend Error-Handling | 2 Std |

### Phase 3: Datenqualitaet & Modell-Verbesserung (1 Woche)
| # | Task | Aufwand |
|---|------|---------|
| 1 | BUG-02: RoBERTa-Werte korrekt speichern | 2 Std |
| 2 | BUG-04: Sprach-Gewichtung korrigieren | 30 Min |
| 3 | IMPROVE-01: Dynamische Ensemble-Gewichtung | 4 Std |
| 4 | IMPROVE-08: Comment-Crawling aktivieren | 3 Std |
| 5 | IMPROVE-05: Engagement-Weight mit Tier-Faktor | 2 Std |
| 6 | IMPROVE-04: Poisson erweitern (Heimvorteil, Venue) | 4 Std |
| 7 | IMPROVE-10: Uebersetzungs-Caching | 3 Std |

### Phase 4: Neue Datenquellen (1-2 Wochen)
| # | Task | Aufwand |
|---|------|---------|
| 1 | EXTEND-02: Wettquoten-Integration | 1 Tag |
| 2 | EXTEND-03: H2H-Daten | 1 Tag |
| 3 | IMPROVE-03: Sport-Sentiment-Modell (Drop-in) | 2 Std |
| 4 | IMPROVE-02: Sarkasmus-Heuristik | 4 Std |
| 5 | IMPROVE-09: Robustes Rate-Limiting | 3 Std |

### Phase 5: Infrastruktur (1 Woche)
| # | Task | Aufwand |
|---|------|---------|
| 1 | IMPROVE-12: Alembic-Migrationen | 1 Tag |
| 2 | IMPROVE-13: PostgreSQL-Support | 1 Tag |
| 3 | IMPROVE-15: Redis-Caching | 1 Tag |
| 4 | IMPROVE-17: API-Sicherheit (Rate-Limits, Auth) | 1 Tag |
| 5 | EXTEND-08: WebSocket fuer Live-Updates | 1 Tag |

### Phase 6: Erweiterte ML & Analyse (2-3 Wochen)
| # | Task | Aufwand |
|---|------|---------|
| 1 | EXTEND-05: XGBoost-Predictor | 1 Woche |
| 2 | EXTEND-06: Aspect-Based Sentiment | 1 Woche |
| 3 | EXTEND-07: Sentiment-Drift-Alarm | 2-3 Tage |
| 4 | EXTEND-10: Backtesting-Framework | 3-4 Tage |

### Phase 7: Frontend & UX (1-2 Wochen)
| # | Task | Aufwand |
|---|------|---------|
| 1 | IMPROVE-18: KO-Phasen-Filter | 1 Tag |
| 2 | EXTEND-12: Turnierbaum-Visualisierung | 2-3 Tage |
| 3 | IMPROVE-20: Dark Mode | 1 Tag |
| 4 | EXTEND-13: Sentiment-Heatmap | 2 Tage |
| 5 | IMPROVE-19: Match-Vergleich | 2 Tage |
| 6 | EXTEND-14: PWA & Mobile | 2-3 Tage |

### Phase 8: Social & Engagement (3+ Wochen)
| # | Task | Aufwand |
|---|------|---------|
| 1 | EXTEND-01: Twitter/X-Integration | 1 Woche |
| 2 | EXTEND-11: User-Accounts + Tipp-Spiel | 2 Wochen |
| 3 | EXTEND-04: Spieler-Verfuegbarkeit | 1 Woche |
| 4 | EXTEND-15: i18n | 3-4 Tage |

---

*RedditOrakel v2.1 - WM 2026 Edition*
