# Model artifact format (`model/artifact.json`)

The contract between the model layer (`src/model.py`, writes the file) and the
presentation layer (`src/app.py`, reads it). The app never estimates anything:
every model number on screen comes from this file.

All numbers below are **placeholders that show the structure only**.

```json
{
  "model": {
    "name": "ARDL / error-correction model of household deposit dollarization",
    "type": "ECM",
    "estimated_at": "2026-10-10T18:00:00+05:00",
    "dependent": {"name": "dollarization_pct", "unit": "percent"},
    "sample": {
      "estimation_start": "2016-01",
      "estimation_end": "2024-06",
      "n_obs": 102,
      "holdout_start": "2024-07",
      "holdout_end": "2026-08"
    },
    "lags": {"dollarization_pct": 1, "depreciation_1m": 2, "rate_spread": 1,
             "inflation_yoy_pct": 0, "log_brent": 1}
  },

  "factors": [
    {"name": "depreciation_1m", "label": "Tenge depreciation, 1 month", "unit": "%", "expected_sign": "+"},
    {"name": "rate_spread", "label": "KZT minus FX deposit rate", "unit": "pp", "expected_sign": "-"},
    {"name": "inflation_yoy_pct", "label": "Inflation, year on year", "unit": "%", "expected_sign": "+"},
    {"name": "log_brent", "label": "Brent oil price (log)", "unit": "log USD", "expected_sign": "-"}
  ],

  "coefficients": {
    "names": ["const", "ect_lag1", "d_depreciation_1m", "..."],
    "values": [0.0, 0.0, 0.0],
    "std_errors": [0.0, 0.0, 0.0],
    "p_values": [0.0, 0.0, 0.0],
    "covariance": [[0.0, 0.0, 0.0], [0.0, 0.0, 0.0], [0.0, 0.0, 0.0]],
    "se_type": "HAC (Newey-West)"
  },
  "residual_std": 0.0,
  "long_run": {"depreciation_1m": 0.0, "rate_spread": 0.0, "inflation_yoy_pct": 0.0, "log_brent": 0.0},

  "latest": {
    "period": "2026-08",
    "value": 19.17,
    "change": -0.05,
    "contributions": {"depreciation_1m": 0.0, "rate_spread": 0.0, "inflation_yoy_pct": 0.0,
                      "log_brent": 0.0, "error_correction": 0.0, "constant": 0.0, "residual": 0.0}
  },

  "scenario": {
    "base_period": "2026-09",
    "base_regressors": [1.0, 0.0, 0.0],
    "base_prediction": 19.1,
    "controls": [
      {"factor": "rate_spread", "label": "Change in KZT–FX rate spread, pp",
       "min": -5.0, "max": 5.0, "step": 0.5,
       "regressor_effect": {"d_rate_spread": 1.0, "rate_spread_lag1": 0.0}}
    ]
  },

  "diagnostics": {
    "unit_roots": {"dollarization_pct": {"adf_p": 0.0, "kpss_p": 0.0, "order": "I(1)"}},
    "bounds_test": {"f_stat": 0.0, "conclusion": "cointegration | no cointegration | inconclusive"},
    "breusch_godfrey_p": 0.0,
    "breusch_pagan_p": 0.0,
    "jarque_bera_p": 0.0,
    "cusum_stable": true,
    "max_vif": 0.0,
    "chow_2020_03_p": 0.0,
    "chow_2022_03_p": 0.0
  },

  "benchmark": {
    "name": "Random walk",
    "rmse_model": 0.0, "rmse_benchmark": 0.0, "rmse_ratio": 0.0,
    "mae_model": 0.0, "mae_benchmark": 0.0, "mae_ratio": 0.0,
    "winner": "model | benchmark"
  }
}
```

## Differences from the placeholder above (as written by `src/model.py`)
- `model.sample` also has `n_months` (months in the estimation sample); `n_obs` is the number of equation observations after the lags.
- `model.specifications_estimated` is the number of lag combinations compared by AIC.
- `latest.contributions` has the keys of the four factors plus `own_dynamics` (lagged changes of the indicator), `error_correction`, `constant` and `residual`. Each term is measured against its average in the estimation sample, so `constant` is the average monthly change in that sample and the parts add up to `latest.change` exactly.
- `scenario.base_level` is the latest observed level; the scenario is next month's level with all drivers unchanged: `level = base_level + x · values`. The controls change a driver's change next month by `s`.
- `diagnostics.bounds_test` also has the 5% critical bounds; `diagnostics` also has `breusch_godfrey_p`, `breusch_pagan_p`, `jarque_bera_p`, `cusum_p`, `cusum_stable`, `max_vif`, `chow_2020_03_p`, `chow_2022_03_p`.
- `benchmark` also has `n_holdout`.

## How the app uses it
- **Driver panel:** `latest.contributions` (percentage points of the latest monthly change, signed).
- **Scenario control:** for a slider value `s`, the regressor vector is
  `x = base_regressors + s × regressor_effect` (by coefficient name).
  Change = `x · values`; level = `base_level` + change; standard error of the
  change = `sqrt(x' · covariance · x)`; 95% band = level ± 1.96 × standard
  error. Plain matrix arithmetic on numbers read from the file, no estimation.
  The band reflects uncertainty about the coefficients only; `residual_std`
  is the typical size of a monthly surprise on top of it.
- **Provenance panel:** `model.estimated_at`, `model.sample`, plus `data/processed/metadata.json`.
- **Honesty panel:** `benchmark.winner` and the RMSE ratio are shown as they are, even if the model loses.
- If the file is missing or unreadable, the app shows a plain-language message and keeps the data panels working.
