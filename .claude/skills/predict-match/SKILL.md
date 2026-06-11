---
name: predict-match
description: Run the WM-2026 prediction pipeline for a match and interpret the report. Use when the user asks for a match prediction, an edge/value analysis, Asian-handicap / over-under / BTTS probabilities, or wants to run the wm2026 workflow for a fixture.
---

# Predict a WM-2026 match

Run the repo's calibrated 8-phase pipeline and explain the result. Everything
runs **offline** in mock mode (no API keys). Deep methodology:
`prompts/WM2026_MASTER_PROMPT.md`; conventions: `CLAUDE.md`.

## 1. Ensure deps (once)
```bash
pip install -r requirements.txt
```

## 2. Run the prediction
Ad-hoc (no YAML needed):
```bash
python -m wm2026.cli predict --home "<HOME>" --away "<AWAY>" --stage <Group|R16|QF|SF|Final> \
  --odds "<H/D/A>" --odds-ou "<O/U>" --odds-btts "<Y/N>" \
  --odds-dc "<1X/12/X2>" --odds-ah=<-0.5:HOME/AWAY> \
  --out reports/
```
From a config: `--match config/matches/<group>/<slug>.yaml` (list them with
`python -m wm2026.cli list`). For real data: `--mode live` after `cp .env.example .env`
and setting `USE_MOCK_*=false` + keys. Omit any `--odds-*` you don't have.

Note: Asian-handicap **negative** lines must use `=`, e.g. `--odds-ah=-0.5:1.95/1.95`
(argparse treats a leading `-` as a flag otherwise).

## 3. Read the report (`reports/<match_id>.md` + `.json`)
Summarise for the user:
- **Executive summary** — most-likely 1X2, λ (home/away), confidence gauge.
- **Edge table** — and crucially the **`(p5)` columns**: an edge only counts as
  real if it stays positive on the conservative bootstrap lower bound. Flag any
  edge > 10 % with a sanity-check note ("why would the market miss this?").
- **Derived markets** — Double Chance, Draw-No-Bet, Asian Handicap (incl. quarter
  lines), alternative totals, clean sheet, win-to-nil, odd/even.
- **Validation warnings** — especially "mock = illustrative, not live".

## 4. Guardrails
- Never give a point prediction without its confidence interval (p5/p50/p95).
- Mock-mode numbers are illustrative — say so.
- This is research/education, **not** betting advice.

## Verify the workflow itself
```bash
pytest tests/test_wm2026_pipeline.py tests/test_markets.py \
       tests/test_edge_conservative.py tests/test_backtesting_rps.py -q
```
