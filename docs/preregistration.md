# Pre-registration of the driver model

Team: Yasmin, Gulzat · Date: 2026-10-05 · Written before any estimation.
Binding: any later change is listed in the technical note as *what changed, why, and what this specification produced*.

## 1. Dependent variable
D_t: household deposit dollarization, percent (see `docs/indicator_card.md`), monthly.

## 2. Mechanism and factors

| # | Factor | Variable (source, transformation) | Channel | Expected sign | Lag |
|---|---|---|---|---|---|
| 1 | Tenge depreciation | 1-month log change of the monthly average USD/KZT rate, × 100 (NBK API) | A weakening tenge raises expected further depreciation, so households move savings into FX; it also revalues existing FX deposits upwards. Lags 0–3 let the model capture a cumulative (up to 4-month) reaction | + | 0–3, chosen by AIC |
| 2 | Interest rate spread | Rate on household KZT deposits minus rate on FX deposits, pp (NBK) | A higher return on tenge deposits makes holding foreign currency more costly | − | 0–3, chosen by AIC |
| 3 | Inflation | Year-on-year CPI inflation, % (Taldau) | High inflation erodes tenge savings and signals weaker trust in the tenge | + | 0–3, chosen by AIC |
| 4 | Oil price | Log of Brent price, USD/barrel (FRED, POILBREUSDM) | Higher oil prices bring FX inflows and support the tenge, lowering fear of devaluation | − | 1–3 (not 0: oil is published with a delay) |

## 3. Specification
- **Sample:** 2016-01 to the latest month with all variables (about 128 months). Starts after the August 2015 move to a floating tenge and inflation targeting.
- **Integration:** ADF (null: unit root, lags by AIC) and KPSS (null: stationarity) on every series, in levels and first differences.
- **Structural breaks:** the sample spans 2020 (COVID) and 2022 (war shock, rouble volatility). Chow tests at 2020-03 and 2022-03 and CUSUM of residuals.
- **Estimator:** ARDL in levels with the Pesaran–Shin–Smith bounds test for a long-run relationship. If the bounds test finds cointegration, the model is written and reported in error-correction form (long-run coefficients + speed of adjustment). If not, a model in first differences is estimated instead, and no long-run claim is made. Maximum 3 lags for each variable, chosen by AIC. Newey–West (HAC) standard errors.
- **Diagnostics:** Breusch–Godfrey (serial correlation), Breusch–Pagan (heteroskedasticity), Jarque–Bera (normality), CUSUM (stability), VIF (multicollinearity). Failures are reported.

## 4. Out-of-sample evaluation and benchmark
- **Hold-out:** the last 20% of the sample (about 26 months, from 2024-07). The model is estimated on the earlier months only; the hold-out is never used for estimation or lag selection.
- **Forecast:** one month ahead, conditional on the observed factor values for that month (a nowcast: the exchange rate and oil price are known before the NBK publishes deposits).
- **Benchmark (fixed now):** random walk, D_t = D_(t−1).
- **Metrics:** RMSE and MAE for model and benchmark, and their ratio. The model "wins" only if the RMSE ratio is below 1.

## 5. Falsification
The model is considered wrong if any of the following holds:
1. The bounds test finds no long-run relationship **and** neither depreciation nor the spread is significant at 5% in the short run.
2. The spread coefficient is positive, or the depreciation coefficient is negative, and significant at 5% (opposite to the mechanism).
3. The model does not beat the random walk out of sample (RMSE ratio ≥ 1). This is reported plainly as a negative result.

## 6. Robustness checks (planned)
1. **Alternative sample:** 2011-12 to latest (the full period with CPI data, crossing the 2014–2015 devaluations; with a 2015-08 regime dummy).
2. **Alternative specification:** logit transformation of the dependent variable, ln(D/(100 − D)), which respects the 0–100 bounds.
3. **Alternative measure:** dollarization at a constant exchange rate (removes the revaluation effect, see the indicator card).
4. **Additional (factor definition):** 3-month instead of 1-month change of the USD/KZT rate.

Every specification estimated, including discarded ones, will be counted and reported.

## 7. Decisions taken by the team
- Depreciation measured as the 1-month change (more flexible with lags 0–3; the 3-month change is kept as a robustness check).
- Benchmark: random walk (the indicator is highly persistent month to month).
- Main sample starts in 2016-01 (floating exchange rate regime).
- Four factors only; no fifth factor (e.g. the rouble rate) is added.

## 8. New element
Monthly household-only dollarization for Kazakhstan, decomposed into a revaluation part and a behavioural part, with a driver model linked to a decision rule for bank liquidity management.
