# Kazakhstan Deposit Dollarization Index

A local website that shows the share of household bank deposits in Kazakhstan held in foreign currency and, once the model is built, what drives its monthly changes. Course project, KBTU Macroeconomic Modelling and Data Analysis.

Indicator definition: `docs/indicator_card.md`. Driver model, fixed before estimation: `docs/preregistration.md`. Format of the model file: `docs/artifact_schema.md`.

## Project status

| Layer | Entry point | Status |
|---|---|---|
| Data | `src/ingest.py` | Done, covered by `tests/test_ingest.py` |
| Model | `src/model.py` | Main specification done: unit roots, error-correction model, bounds test, diagnostics, hold-out evaluation, `model/artifact.json`. Robustness checks in `src/robustness.py` |
| Website | `src/app.py` | Done: headline, history, driver panel, scenario control, sources, limits. Covered by `tests/test_app.py` |

Main result so far: on the 26 months held out from estimation, the model does **not** beat the random-walk benchmark (RMSE ratio above 1). This is reported on the website and in `model/artifact.json`. Deviations from the pre-registration are in `docs/deviations.md`.

If `model/artifact.json` is missing or unreadable, the website shows a notice instead of the driver panel and scenario control, and the data panels keep working.

## Quick start: one command

On Windows, from the project folder (double-click `run.bat`, or type it in a terminal):

```bat
run.bat
```

On the first run it creates a Python environment in `.venv` and installs `requirements.txt`. Then it rebuilds every number from `data/raw` (data, model, robustness checks, feedback VAR, decision rule, report tables, figures), checks them against `docs/expected_numbers.json`, and starts the website. A full run takes about 5 minutes the first time and 2-3 minutes after that.

- `run.bat build` rebuilds and checks only, without starting the site.
- `run.bat site` only starts the site from the files already built.

The step-by-step commands below do the same thing one script at a time.

## Reproducibility and tolerance

`python src/check.py` compares the numbers the pipeline has just produced with the reported numbers in `docs/expected_numbers.json` and prints PASS or FAIL for each.

- **Headline tolerance: the latest dollarization value must reproduce within ±0.01 percentage points** (19.17% for August 2026).
- Model coefficients within ±0.001, the bounds-test F statistic within ±0.01, the RMSE ratio within ±0.001, the decision-rule threshold within ±0.01 pp; text results (bounds-test conclusion, hold-out winner, latest signal) must match exactly.
- The only random step, the Monte Carlo band of the impulse response in `src/feedback.py`, uses a fixed seed (2026).

`python src/check.py --record` overwrites the expected numbers; use it only after a deliberate change and say so in the commit message.

## Install

Python 3.11 or newer.

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

On macOS or Linux, activate with `source .venv/bin/activate`.

## Run the website

```bash
streamlit run src/app.py
```

Open the address printed in the terminal (normally http://localhost:8501). The site reads only files in this repository and never downloads anything, so it works offline. Stop it with Ctrl+C.

## Rebuild the processed data

```bash
python src/ingest.py
```

Reads `data/raw/` and rewrites everything in `data/processed/`. Raw files are never edited by hand. Where each raw file came from is in `data/raw/SOURCES.md`.

## Refresh the raw data

```bash
python src/download_rates.py
python src/download_oil.py
```

These download the daily USD/KZT rate (National Bank of Kazakhstan API) and the Brent oil price (FRED). Deposits, deposit rates and CPI are manual downloads; the navigation path for each is in `data/raw/SOURCES.md`. After refreshing, run `python src/ingest.py`.

## Re-estimate the model

```bash
python src/model.py
```

Estimates the model on 2016-01 to 2024-06, evaluates it on the held-out months, and writes `model/artifact.json` and the tables in `outputs/`. The website only reads this file and never estimates anything. Takes under a minute.

## Robustness checks

```bash
python src/robustness.py
```

Re-estimates eight variants of the model (alternative sample, logit, constant exchange rate, 3-month depreciation, and three extensions from the literature review) on the same hold-out months and writes `outputs/robustness.csv`. Takes about 15 seconds. Changes to the plan are listed in `docs/deviations.md`.

## Feedback analysis: does dollarization move the tenge?

```bash
python src/feedback.py
```

Estimates a small vector autoregression (oil, rate spread, depreciation, dollarization) from 2016 onwards and tests both directions: does the exchange rate predict dollarization, and does dollarization predict the exchange rate? Writes `outputs/feedback_granger.csv`, `outputs/feedback_irf.csv` and `model/feedback.json`, which the website shows in the panel "Does dollarization move the tenge?". Takes a few seconds.

## Decision rule for the treasury

```bash
python src/decision_rule.py
```

Turns the latest monthly change into a green / amber / red signal for a bank treasury. The thresholds are the 90th percentiles of monthly changes over the estimation months only (2016-01 to 2024-06): headline dollarization, and dollarization at a constant exchange rate, which separates revaluation from households actually buying foreign currency. Writes `outputs/decision_signals.csv`, `outputs/decision_sensitivity.csv` and `model/decision_rule.json`, which the website shows under the headline and below the history chart.

## Tables for the report

```bash
python src/report_tables.py
```

Writes `outputs/report_tables.md`: every statistic behind the website, as tables for the technical note. Sample and lag choice, unit-root tests (ADF, KPSS, Zivot-Andrews), the regression table with HAC standard errors and R², long-run coefficients, the bounds test with critical values, all residual diagnostics with their null hypotheses and verdicts (including the tests the model fails), VIF for every regressor, hold-out accuracy, the robustness table, and the full statsmodels output. Run it after `src/model.py`, `src/robustness.py`, `src/feedback.py` and `src/decision_rule.py`.

## Figures for the report

```bash
python src/figures.py
```

Draws the six figures of the technical note into `outputs/figures/` (PNG, 200 dpi, 6.5 inches wide): the history of the indicator, headline vs constant-exchange-rate dollarization, the hold-out against the random walk, residual diagnostics with the CUSUM test, the VAR impulse responses, and the decision-rule signals. Every figure is drawn from the files the pipeline writes, never from typed numbers. `run.bat` runs it automatically.

## Acceptance self-check

```bash
python src/acceptance.py
```

Runs the acceptance checks of the assignment guide that can be automated (3-10 and "deleting data/processed restores it exactly") on temporary copies, without changing the project, and writes `outputs/acceptance_report.md`. The checks that need a person (fresh clone on another laptop, stopwatch, network off) and the record of all results are in `docs/acceptance_checks.md`.

## Run the tests

```bash
python -m pytest
```

Run from the project folder.

## Known limitations

- The indicator is the foreign-currency share of household deposits. When the tenge weakens, foreign-currency deposits rise in tenge terms even if nobody buys dollars.
- Cash held outside banks is not counted. Accounts of non-resident individuals are included.
- Deposits are published with a lag, so the latest month is not the current month.
- Full list of weaknesses: `docs/indicator_card.md`.

## Declared borrowing

No code from external sources has been copied. Libraries are listed with pinned versions in `requirements.txt`.
