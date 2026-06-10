# ML Training Guide — xG Predictor

## What the model does

`scripts/train_xg_predictor.py` trains a Ridge regression that predicts expected goals (home and away separately) from purely historical, non-sentiment features:

| Feature | Meaning |
|---|---|
| `elo_delta` | World-Football-Elo gap (home − away) before kickoff |
| `home_avg_xg` / `away_avg_xg` | Rolling mean goals scored, last 10 matches |
| `home_avg_xg_conceded` / `away_avg_xg_conceded` | Rolling mean goals conceded, last 10 matches |
| `home_form_pts` / `away_form_pts` | Points from last 5 results (W=3, D=1, L=0) |
| `h2h_score` | (home wins − away wins) / total prior meetings |

The trained coefficients are stored as `models_ml/artifacts/xg_predictor.json` and loaded by `MlBlendFactor`, which plugs into the factor ensemble as an optional extra signal.

**Important:** Sentiment, rest days, altitude, and travel are not in the free historical data, so their learned coefficients stay near zero. The model is additive — it nudges the base xG rather than replacing it.

---

## Prerequisites

```
Python 3.11+
scikit-learn
numpy
```

Install the extras (the venv already has FastAPI dependencies; scikit-learn may be missing):

```bash
cd backend
pip install scikit-learn numpy
```

---

## Data source

The script has two modes controlled by the `USE_MOCK_OPENFOOTBALL` environment variable:

| Mode | Data | Rows |
|---|---|---|
| `USE_MOCK_OPENFOOTBALL=true` (default) | Deterministic synthetic history | ~40 rows (illustrative only) |
| `USE_MOCK_OPENFOOTBALL=false` | Real 2018 + 2022 World Cup via openfootball API | ~120–150 rows |

For a model worth using in production, set `USE_MOCK_OPENFOOTBALL=false`. The script requires at least 30 leakage-free rows; mock mode may produce fewer and exit early.

---

## How to run

```bash
cd backend
python scripts/train_xg_predictor.py
```

With real data:

```bash
cd backend
USE_MOCK_OPENFOOTBALL=false python scripts/train_xg_predictor.py
```

The script prints progress and writes the artifact on success:

```
Rows: 143 (from 128 matches)
Temporal-CV MAE  home=0.832 goals  away=0.779 goals
Wrote models_ml/artifacts/xg_predictor.json
Set FACTOR_WEIGHT_ML > 0 to activate the MlBlendFactor.
```

---

## Interpreting the output

**Temporal-CV MAE** (Mean Absolute Error, expanding-window cross-validation):

- Trained on historical data in chronological order; each fold tests on future matches.
- Unit: goals. A MAE of 0.83 means the model is off by 0.83 goals on average.
- International football goals-per-game average ≈ 1.3 per side. An MAE near 1.0 is roughly ±1 goal — reasonable for a linear model on sparse data.

**When is the model good enough to activate?**

| MAE | Interpretation | Recommendation |
|---|---|---|
| < 0.70 | Strong fit | Activate at `FACTOR_WEIGHT_ML=0.05–0.10` |
| 0.70–1.00 | Acceptable | Activate at `FACTOR_WEIGHT_ML=0.03–0.05` |
| > 1.00 | Weak — model adds noise | Keep at 0 (default) |

With real data (`USE_MOCK_OPENFOOTBALL=false`) you should see **60–80 qualifying rows** from WC 2018+2022 combined. Fewer than 40 rows means the MAE will be unreliable — check the "Rows:" line in the output before deciding to activate.

If only mock data was used, the MAE is meaningless. Always train on real data before activating.

---

## Activating the model

After a successful training run, open `.env` (create it if it doesn't exist next to `main.py`) and add:

```env
FACTOR_WEIGHT_ML=0.05
```

The `MlBlendFactor` reads `models_ml/artifacts/xg_predictor.json` at startup. If the file is missing, the factor silently reports `available=false` and the ensemble re-normalises without it — so a missing artifact never breaks predictions.

To deactivate again, set `FACTOR_WEIGHT_ML=0` or remove the line.

---

## Output artifact

`backend/models_ml/artifacts/xg_predictor.json` structure:

```json
{
  "model": "ridge",
  "trained_on": 143,
  "cv_mae_home": 0.832,
  "cv_mae_away": 0.779,
  "home_coeffs": {
    "elo_delta": 0.0015,
    "home_avg_xg": 0.82,
    "away_avg_xg": -0.11,
    "home_avg_xg_conceded": 0.09,
    "away_avg_xg_conceded": 0.31,
    "home_form_pts": 0.018,
    "away_form_pts": -0.007,
    "h2h_score": 0.12
  },
  "away_coeffs": { "..." : "..." },
  "home_intercept": 0.95,
  "away_intercept": 0.91
}
```

Commit this file to version control so the factor is available in all environments without re-training.

---

## Re-training schedule

Re-train after each World Cup group stage to incorporate actual 2026 results once they are added to the openfootball data source.
