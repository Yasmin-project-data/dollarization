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