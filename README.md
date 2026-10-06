# Kazakhstan Deposit Dollarization Index

A local website that shows the share of household bank deposits in Kazakhstan held in foreign currency and, once the model is built, what drives its monthly changes. Course project, KBTU Macroeconomic Modelling and Data Analysis.

Indicator definition: `docs/indicator_card.md`. Driver model, fixed before estimation: `docs/preregistration.md`. Format of the model file: `docs/artifact_schema.md`.

## Project status

| Layer | Entry point | Status |
|---|---|---|
| Data | `src/ingest.py` | Done, covered by `tests/test_ingest.py` |
| Model | `src/model.py` | Main specification done: unit roots, error-correction model, bounds test, diagnostics, hold-out evaluation, `model/artifact.json`. Robustness checks not yet done |
| Website | `src/app.py` | Done: headline, history, driver panel, scenario control, sources, limits. Covered by `tests/test_app.py` |

Main result so far: on the 26 months held out from estimation, the model does **not** beat the random-walk benchmark (RMSE ratio above 1). This is reported on the website and in `model/artifact.json`. Deviations from the pre-registration are in `docs/deviations.md`.

If `model/artifact.json` is missing or unreadable, the website shows a notice instead of the driver panel and scenario control, and the data panels keep working.

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
