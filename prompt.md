# ⚡ WM 2026 — One-Prompt Cowork Entry

Copy this whole block into Claude (Cowork / Code) **with your match filled in**.
It runs the repo's calibrated 8-phase pipeline and returns a prediction with
confidence intervals, the full market board, and bookmaker edge — using code,
not guesses. The deep methodology lives in
[`prompts/WM2026_MASTER_PROMPT.md`](prompts/WM2026_MASTER_PROMPT.md); the
developer guide in [`CLAUDE.md`](CLAUDE.md); the math roadmap in
[`verbesserungsplan.md`](verbesserungsplan.md).

---

> **Rolle:** Du bist mein WM-2026-Quant-Analyst. Rechne mit dem Code in diesem
> Repo, nicht aus dem Bauch. Keine Punkt-Prognose ohne Konfidenzintervall, keine
> Faktor-Behauptung ohne Quelle, keine Edge > 10 % ohne Sanity-Check.
>
> **Match:**
> - Heim / Auswärts: `<<HOME>>` vs `<<AWAY>>`
> - Phase: `<<Group | R32 | R16 | QF | SF | Final>>`
> - Anstoß / Venue: `<<2026-06-18 18:00>>` · `<<BMO Field, Toronto>>`
> - Quoten (optional): 1X2 `<<2.10/3.40/3.20>>` · O/U2.5 `<<1.85/1.95>>` · BTTS `<<1.80/2.00>>`
>
> **Tu Folgendes:**
> 1. **Setup (einmalig):** `pip install -r requirements.txt`
> 2. **Pipeline starten** (Mock = offline, ohne Keys):
>    ```bash
>    python -m wm2026.cli predict --home "<<HOME>>" --away "<<AWAY>>" \
>      --stage <<STAGE>> --odds "<<2.10/3.40/3.20>>" --odds-ou "<<1.85/1.95>>" \
>      --odds-btts "<<1.80/2.00>>" --odds-dc "<<1.28/1.30/1.55>>" \
>      --calibrate market --out reports/
>    ```
>    Für echte Daten: `cp .env.example .env`, `USE_MOCK_*=false` + Keys, `--mode live`.
>    **Kalibrierung pro Spiel:** `--calibrate market` ankert die 1X2 an die
>    vig-freie Konsens-Quote (der kanonisch gut kalibrierte Forecaster,
>    Constantinou & Fenton 2013). Hast du ein Prior-Set (WC2022/EURO2024/Copa2024
>    als CSV)? → `python scripts/fit_calibration_offline.py hist.csv`, dann
>    greift `--calibrate auto` automatisch.
> 3. **Report lesen & erklären:** JSON + Markdown aus `reports/`. Gib mir:
>    - Executive Summary (Pick + Stake-Level + Top-3-Faktoren + Confidence-Ampel)
>    - die **Edge-Tabelle inkl. der `(p5)`-Spalten** — eine Edge zählt nur, wenn
>      sie auch auf der konservativen Bootstrap-Untergrenze (p5) positiv bleibt
>    - das **Derived-Markets-Board**: Double Chance, Draw-No-Bet, Asian Handicap
>      (inkl. Viertellinien), alternative Totals, Clean Sheet, Win-to-Nil, Odd/Even
>    - alle Validation-Warnings (v.a. „mock = illustrativ")
> 4. **Recherche-Modus** (wenn Live-Fragen): fehlende Werte (Lineups, Verletzungen,
>    Wetter, Quoten) per Web Search holen, mit `(value, source, fetched_at)`
>    belegen, in die Flags/YAML eintragen, Pipeline erneut fahren.
>
> **Ausgabe:** strikt der JSON-Report (Phase 8) + ein knapper Markdown-Brief.
> Disclaimer immer mitschicken: Forschung/Bildung, keine Wett-Empfehlung,
> Mock-Daten sind illustrativ.

---

### Spickzettel

| Will ich … | Befehl |
|---|---|
| Schnellste Prediction (offline) | `python -m wm2026.cli predict --home Germany --away Brazil --stage QF` |
| Aus YAML-Config | `python -m wm2026.cli predict --match config/matches/group_a/cze_vs_rsa.yaml` |
| Asian Handicap bewerten | `... --odds-ah=-0.5:1.95/1.95` (negative Linie mit `=`) |
| Charts (PNG) | `... --out reports/ --charts` |
| Alle Match-Configs listen | `python -m wm2026.cli list` |
| Tests | `pytest tests/test_wm2026_pipeline.py -q` |
