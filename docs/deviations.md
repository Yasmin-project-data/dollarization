# Deviations from the pre-registration

Each entry: what changed, why, and what the pre-registered specification produced. These become the three-line list in Section 3 of the technical note.

## 1. Every factor has at least one lag (error-correction form)

- **What changed:** pre-registration says lags 0–3 chosen by AIC. The model is estimated in error-correction form, which contains the lagged level of every variable, so each factor must have at least one lag. AIC is searched over orders 1–3 for the dependent variable and for each factor (243 specifications).
- **Why:** without a lagged level there is no long-run term and the bounds test cannot be run.
- **What the pre-registered rule produced:** an unrestricted AIC search over lags 0–3 (`ardl_select_order`, on the estimation sample only) picked the dependent variable at lags 1–2 and the factors at lag 0 only, which has no long-run relationship to test. This exploratory search is not part of the committed code.

## 2. Brent enters with a one-month shift

- **What changed:** the fourth factor is `log_brent_lag1`, the log Brent price shifted by one month, used with the same lag search as the other factors.
- **Why:** pre-registration allows Brent only at lags 1–3 because oil is published with a delay. Shifting once keeps the August 2026 observation usable (128 months, as planned).
- **What the pre-registered specification produced:** the same model, written with a shifted regressor.

## 3. Robustness checks share the main model's hold-out months

- **What changed:** pre-registration says the hold-out is the last 20% of the sample. For the robustness checks (`src/robustness.py`) every variant is evaluated on the same hold-out months as the main model (2024-07 onwards), including R1, whose longer sample would otherwise move the hold-out earlier.
- **Why:** so that RMSE ratios can be compared across variants on identical months.
- **What the pre-registered rule produced:** for M0 to R4 the rule gives the same months, since they share the 2016-01 start; only R1 would differ.

## 4. Three extensions added after the literature review

- **What changed:** three variants not in the pre-registration: exchange-rate volatility as a fifth regressor (L1), an interaction of depreciation with last month's dollarization level (L2), and step dummies at the two Chow break dates (L3). They are robustness checks only; the main model is unchanged.
- **Why:** L1 follows Ben Naceur, Hosny & Hadjian (2015) and Cakir et al. (2022); L2 follows Neanidis & Savva (2009), who find stronger effects where dollarization is high; L3 follows our own Chow tests.
- **What the pre-registered specification produced:** the main model (M0), reproduced exactly by the robustness script. All eight variants and the 2,430 specifications searched by AIC are reported in `outputs/robustness.csv`.

## 5. Feedback analysis: does dollarization move the exchange rate?

- **What changed:** a vector autoregression (`src/feedback.py`) of four stationary series (change in log Brent, change in the rate spread, depreciation, change in dollarization), 2016 onwards, lags by AIC. It reports Granger causality in both directions, impulse responses with 95% bands and a variance decomposition, and is shown on the website in its own panel. The main model is unchanged.
- **Why:** suggested by our instructor; the main model explains dollarization by the exchange rate, and this checks the reverse direction.
- **Timing choice, made after a first exploratory run (stated openly):** a first run used the monthly average rate (the measure in the main model) and found dollarization strongly "Granger-causing" depreciation. Because dollarization is an end-of-month stock, a late-month fall of the tenge reaches dollarization one month before it reaches the average-rate depreciation, so that result is a timing artefact. The main variant therefore uses end-of-month rates; with them, or with dollarization at a constant exchange rate, the effect disappears. All four combinations are reported in `outputs/feedback_granger.csv`, not only the main one.
- **What the pre-registered specification produced:** not applicable; this question is not in the pre-registration.

