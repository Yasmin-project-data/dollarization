# Data cleaning log (revision after defence)

Data source: data/processed/monthly.csv (built by src/ingest.py). Raw files unchanged.
Model sample: 2016-01 onwards.

## Data issues
| Series | Month | Issue | Decision |
|---|---|---|---|
| usd_kzt_vol | 2023-08 | NBK API has only 4 daily rates (gap 28 Jul - 21 Aug) | Set to missing; used only in robustness L1 |
| usd_kzt_avg | 2023-08 | Same gap | Keep official NBK monthly average 451.94 (manual_values.csv) |
| brent_usd | 2026-08 | Not yet published by FRED at download | No effect: model uses Brent lagged one month |
| brent_usd | 2026-03, 2026-06 | Large jumps | Verified against FRED: [write result] |

## Outliers (replaced by linear interpolation)
Rule: monthly change beyond Q1 - 3*IQR or Q3 + 3*IQR (Tukey far-out), model sample 2016-01 onwards.
FX rate and Brent: change measured in logs. Same rule for all six model variables.
Original data kept in monthly.csv; cleaned data in data/processed/monthly_clean.csv; full list in outputs/outlier_log.csv.

| Series | Month | Old value | Monthly change | Reason |
|---|---|---|---|---|
| dollarization_pct | 2020-03 | 47.437 | +5.046 | COVID / tenge shock (revaluation) |
| dollarization_const_pct | 2019-06 | 44.854 | +2.864 | Extreme monthly jump |
| usd_kzt_avg | 2020-03 | 415.301 | +9.5% | COVID / oil shock |
| usd_kzt_avg | 2022-03 | 499.749 | +13.7% | Early-2022 tenge shock |
| usd_kzt_avg | 2022-04 | 453.384 | -9.7% | Reversal after shock |
| rate_spread | 2016-02 | 8.200 | +2.8 | Rate jump after 2015 float |
| inflation_yoy_pct | 2016-10 | 11.297 | -5.089 | Base effect after 2015 price spike |
| inflation_yoy_pct | 2016-11 | 8.614 | -2.683 | Base effect after 2015 price spike |
| inflation_yoy_pct | 2022-03 | 12.080 | +3.350 | Early-2022 price shock |
| inflation_yoy_pct | 2023-03 | 18.150 | -3.279 | Base effect after 2022 price spike |
| brent_usd | 2020-03 | 33.947 | -49.5% | COVID oil price crash |

Sensitivity: a 2*IQR threshold was considered but not used as the main rule (no standard justification).
Robustness: model will be estimated on both original and cleaned data, results compared.

## Stationarity (cleaned data, 2016-01 onwards)
Tests: ADF (H0 unit root), KPSS (H0 stationary), Zivot-Andrews (H0 unit root, one break).
Full results: outputs/stationarity_tests.csv, outputs/stationarity_extra.csv.

| Variable | Order | Note |
|---|---|---|
| depreciation_1m_pct | I(0) | All tests agree |
| rate_spread | I(1) | Level non-stationary, difference stationary |
| log_brent | I(1) | Level non-stationary (trend-stationary at 5%), difference stationary |
| inflation_yoy_pct | I(1) | Difference stationary once a break (2023-02) is allowed |
| dollarization_pct | I(0)/I(1) | ADF and ZA (break 2017-10) reject unit root, KPSS rejects stationarity |
| dollarization_const_pct | I(0)/I(1) | Difference stationary by all three tests |

No variable is I(2), so the ARDL bounds test is valid. Logit transform checked and gives the same picture, so percentages are kept.

## ACF / PACF (stationary forms, cleaned data, 2016-01 onwards)
Band: +/-1.96/sqrt(n) = +/-0.17. Full results: outputs/acf_pacf_lags.csv.

| Series | Significant PACF lags | Reading | Lag range |
|---|---|---|---|
| d_dollarization | 1 (weak), 10 (isolated) | Short memory | 1-3 |
| depreciation_1m | 1, 2 (negative), 16 (isolated) | Overshoot and partial reversal | 0-3 |
| d_rate_spread | 20 (isolated) | No memory, close to white noise | 0-3 |
| d_inflation_yoy | 1 (strong), 13 | AR(1); lag 12-13 is a base effect of the year-on-year measure | 0-3 |
| d_log_brent | 1, 3 | Short memory | 0-3 |

No structure beyond lag 3 except isolated spikes (about 1 in 24 is expected by chance at 5%).
Maximum lag 3 is kept. Change from the original design: regressor lags now start at 0 (spread shows no memory).
Grid: dependent 1-3, regressors 0-3 = 768 specifications.

## Lag selection (AIC and BIC)
Grid: dependent lags 1-3, regressor lags 0-3, 768 specifications (outputs/lag_selection_grid.csv).
Common sample for all specifications: 2016-05 to 2024-06, n = 98. Hold-out (2024-07 onwards) excluded.
Regressors: depreciation_1m, rate_spread, inflation_yoy, log_brent_lag1.

Result: AIC and BIC both select ARDL(1,0,0,0,0): AIC 273.89, BIC 289.40.
Several models are within 2 AIC points (e.g. Brent with 2 lags: 274.42), so the simplest one is kept;
BIC prefers it clearly (next best +3.8, Brent with 2 lags +5.7).
Consistent with ACF/PACF: only lag 1 of d_dollarization is significant.
Original model (3,1,1,2,2) needed more lags mainly to fit shock-and-reversal patterns that cleaning removed.