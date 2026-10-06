"""
Model layer: processed data -> driver model -> model/artifact.json.

Follows docs/preregistration.md, written before any estimation.

Reads:  data/processed/monthly.csv   (built by src/ingest.py)
Writes: (in progress) outputs/ tables and model/artifact.json

Run from the project folder:
    python src/model.py
"""

from pathlib import Path

import numpy as np
import pandas as pd

DATA_FILE = Path("data/processed/monthly.csv")

# Pre-registered choices (docs/preregistration.md, section 3 and 4).
SAMPLE_START = pd.Period("2016-01", freq="M")  # after the 2015 float
HOLDOUT_SHARE = 0.20                           # last 20% never used to estimate

DEPENDENT = "dollarization_pct"
FACTORS = ["depreciation_1m", "rate_spread", "inflation_yoy_pct", "log_brent"]
MODEL_COLUMNS = [DEPENDENT] + FACTORS


def read_monthly(path=DATA_FILE):
    """Read the merged monthly table written by ingest.py."""
    if not path.exists():
        raise FileNotFoundError(
            f"Processed data not found: {path}. Run: python src/ingest.py"
        )
    monthly = pd.read_csv(path)
    monthly["period"] = pd.PeriodIndex(monthly["period"], freq="M")
    return monthly.set_index("period")


def add_depreciation(monthly):
    """Factor 1: 1-month change of the monthly average USD/KZT, in log percent."""
    monthly["depreciation_1m"] = 100 * np.log(monthly["usd_kzt_avg"]).diff()
    return monthly


def add_log_brent(monthly):
    """Factor 4: log of the Brent price in USD per barrel."""
    monthly["log_brent"] = np.log(monthly["brent_usd"])
    return monthly


def build_model_table(monthly):
    """The dependent variable and the four factors, one row per month.

    rate_spread (KZT minus FX deposit rate, pp) and inflation_yoy_pct are
    already built by ingest.py. Brent is published later than deposits, so
    its latest month can be empty; the model uses it only with lags >= 1.
    """
    monthly = monthly.copy()
    monthly = add_depreciation(monthly)
    monthly = add_log_brent(monthly)
    return monthly[MODEL_COLUMNS]


def last_complete_month(table):
    """Latest month in which the dependent variable and all factors that the
    model uses without a lag are present. Brent is used with lags >= 1 only,
    so it is not required in the month itself."""
    needed = [DEPENDENT, "depreciation_1m", "rate_spread", "inflation_yoy_pct"]
    complete = table[needed].dropna()
    return complete.index.max()


def split_sample(table, start=SAMPLE_START, holdout_share=HOLDOUT_SHARE):
    """Cut the model sample and split it into estimation and hold-out.

    The hold-out is the last `holdout_share` of the sample (rounded to whole
    months). Everything chosen from the data, such as lags and unit-root
    orders, must use the estimation part only.
    """
    end = last_complete_month(table)
    sample = table.loc[start:end]
    n_holdout = int(round(holdout_share * len(sample)))
    estimation = sample.iloc[:-n_holdout]
    holdout = sample.iloc[-n_holdout:]
    return estimation, holdout


def main():
    table = build_model_table(read_monthly())
    estimation, holdout = split_sample(table)
    print(f"Sample:     {estimation.index[0]} to {holdout.index[-1]} "
          f"({len(estimation) + len(holdout)} months)")
    print(f"Estimation: {estimation.index[0]} to {estimation.index[-1]} "
          f"({len(estimation)} months)")
    print(f"Hold-out:   {holdout.index[0]} to {holdout.index[-1]} "
          f"({len(holdout)} months)")


if __name__ == "__main__":
    main()
