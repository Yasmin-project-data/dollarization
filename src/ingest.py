"""
Data layer: raw files -> clean monthly tables.

Reads (never modified):
    data/raw/deposits_individuals_nbk.xlsx   household deposits by currency
    data/raw/usd_kzt_daily_nbk_api.csv        daily official USD/KZT rate
    data/raw/manual_values.csv                hand-transcribed values (documented)
Writes:
    data/processed/deposits.csv        deposits and dollarization, monthly
    data/processed/exchange_rate.csv   USD/KZT monthly average, end of month
    data/processed/monthly.csv         everything merged, one row per month

Run from the project folder:
    python src/ingest.py
"""

from pathlib import Path

import pandas as pd

RAW_FILE = Path("data/raw/deposits_individuals_nbk.xlsx")
RATES_FILE = Path("data/raw/usd_kzt_daily_nbk_api.csv")
MANUAL_FILE = Path("data/raw/manual_values.csv")

OUT_DIR = Path("data/processed")
OUT_DEPOSITS = OUT_DIR / "deposits.csv"
OUT_RATES = OUT_DIR / "exchange_rate.csv"
OUT_MONTHLY = OUT_DIR / "monthly.csv"

# A month needs at least this many published daily rates for its average
# to be computed from daily data; otherwise a documented manual value is used.
MIN_DAYS_FOR_AVERAGE = 15

# The NBK table has a 6-row header with merged cells, so we name the
# columns ourselves, in the order they appear in the file.
COLUMN_NAMES = [
    "period",          # MM.YY, end of month
    "total",           # all household deposits
    "demand_kzt",      # demand deposits and current accounts, national currency
    "demand_fx",       # demand deposits and current accounts, foreign currency
    "conditional_kzt", # conditional deposits, national currency
    "conditional_fx",  # conditional deposits, foreign currency
    "term_kzt",        # term deposits, national currency
    "term_fx",         # term deposits, foreign currency
    "savings_kzt",     # savings deposits, national currency
    "savings_fx",      # savings deposits, foreign currency
]

KZT_COLUMNS = ["demand_kzt", "conditional_kzt", "term_kzt", "savings_kzt"]
FX_COLUMNS = ["demand_fx", "conditional_fx", "term_fx", "savings_fx"]

# Header text we expect to find in the file. If NBK changes the layout,
# the script stops with a clear message instead of producing wrong numbers.
EXPECTED_HEADER = ["Всего", "в национальной валюте", "в иностранной валюте"]
HEADER_ROW = 5  # 6th row of the sheet (counting from 0)


def read_raw(path):
    """Read the Excel sheet as text, exactly as published."""
    if not path.exists():
        raise FileNotFoundError(f"Raw file not found: {path}")
    return pd.read_excel(path, header=None, dtype=str)


def check_layout(raw):
    """Stop if the table does not look like the NBK layout we expect."""
    header = raw.iloc[HEADER_ROW].fillna("").str.strip().tolist()
    for text in EXPECTED_HEADER:
        if text not in header:
            raise ValueError(
                f"Unexpected file layout: '{text}' not found in header row. "
                "The NBK table may have changed."
            )
    if raw.shape[1] != len(COLUMN_NAMES):
        raise ValueError(
            f"Expected {len(COLUMN_NAMES)} columns, found {raw.shape[1]}."
        )


def keep_data_rows(raw):
    """Keep only rows whose first cell is a date like '01.10'.

    This drops the title, the header rows and the footnotes at the bottom.
    """
    first_cell = raw[0].fillna("").str.strip()
    is_data = first_cell.str.fullmatch(r"\d{2}\.\d{2}")
    data = raw[is_data].copy()
    data.columns = COLUMN_NAMES
    return data


def parse_period(text):
    """Convert 'MM.YY' (e.g. '01.10') into a monthly period (2010-01)."""
    month, year = text.strip().split(".")
    return pd.Period(year=2000 + int(year), month=int(month), freq="M")


def parse_number(text):
    """Convert NBK number text like '1 935 789' into 1935789.0.

    Removes normal and non-breaking spaces. Empty cells become NaN.
    """
    if pd.isna(text):
        return float("nan")
    cleaned = str(text).replace(" ", "").replace("\xa0", "").replace(",", ".")
    return float(cleaned)


def fill_missing_with_zero(data):
    """Savings deposits did not exist in early years: empty means zero."""
    value_columns = KZT_COLUMNS + FX_COLUMNS
    data[value_columns] = data[value_columns].fillna(0.0)
    return data


def add_totals(data):
    """Add totals by currency, recomputed from the components."""
    data["kzt_total"] = data[KZT_COLUMNS].sum(axis=1)
    data["fx_total"] = data[FX_COLUMNS].sum(axis=1)
    return data


def check_totals(data, tolerance=5.0):
    """The NBK 'total' must equal the sum of components (rounding allowed)."""
    gap = (data["kzt_total"] + data["fx_total"] - data["total"]).abs()
    if gap.max() > tolerance:
        bad = data.loc[gap.idxmax(), "period"]
        raise ValueError(
            f"Components do not add up to total in {bad}: "
            f"gap {gap.max():.0f} million KZT."
        )


def add_dollarization(data):
    """Dollarization = foreign-currency deposits / all deposits, in percent."""
    data["dollarization_pct"] = 100 * data["fx_total"] / data["total"]
    return data


def build_deposits(path=RAW_FILE):
    """Run all deposit transformations in order and return the clean table."""
    raw = read_raw(path)
    check_layout(raw)
    data = keep_data_rows(raw)

    data["period"] = data["period"].apply(parse_period)
    numeric_columns = COLUMN_NAMES[1:]
    for column in numeric_columns:
        data[column] = data[column].apply(parse_number)

    data = fill_missing_with_zero(data)
    data = add_totals(data)
    check_totals(data)
    data = add_dollarization(data)

    data = data.sort_values("period").reset_index(drop=True)
    if data["period"].duplicated().any():
        raise ValueError("Duplicate months found in the raw file.")
    return data


# ---------------------------------------------------------------------------
# Exchange rate
# ---------------------------------------------------------------------------

def read_daily_rates(path=RATES_FILE):
    """Read daily USD/KZT rates downloaded from the NBK API."""
    if not path.exists():
        raise FileNotFoundError(
            f"Raw file not found: {path}. Run: python src/download_rates.py"
        )
    rates = pd.read_csv(path, parse_dates=["date"])
    if (rates["quant"] != 1).any():
        raise ValueError("Unexpected quant: rates must be per 1 USD.")
    if rates["date"].duplicated().any():
        raise ValueError("Duplicate dates in the daily rate file.")
    return rates.set_index("date")["usd_kzt"].sort_index()


def fill_calendar_gaps(daily):
    """Put every calendar day in the series and carry the last rate forward.

    NBK publishes no rate on some days (weekends, a few missing dates);
    the previous official rate stays in force on those days.
    Returns the filled series and a flag that marks filled days.
    """
    all_days = pd.date_range(daily.index.min(), daily.index.max(), freq="D")
    published = daily.reindex(all_days)
    was_missing = published.isna()
    return published.ffill(), was_missing


def monthly_rates(daily, was_missing):
    """Monthly average, end-of-month rate and number of published days."""
    by_month = daily.groupby(daily.index.to_period("M"))
    table = pd.DataFrame({
        "usd_kzt_avg": by_month.mean(),
        "usd_kzt_eom": by_month.last(),
    })
    table["published_days"] = (~was_missing).groupby(
        was_missing.index.to_period("M")).sum()
    table.index.name = "period"
    return table


def read_manual_values(path=MANUAL_FILE):
    """Read hand-transcribed values; each row documents its own source."""
    if not path.exists():
        return pd.DataFrame(columns=["series", "period", "value", "source"])
    manual = pd.read_csv(path, dtype={"period": str})
    manual["period"] = pd.PeriodIndex(manual["period"], freq="M")
    return manual


def apply_manual_averages(table, manual):
    """Use the documented manual monthly average where daily data are thin."""
    table["usd_kzt_avg_source"] = "daily_api"
    rows = manual[manual["series"] == "usd_kzt_monthly_avg"]
    for _, row in rows.iterrows():
        if row["period"] in table.index:
            table.loc[row["period"], "usd_kzt_avg"] = float(row["value"])
            table.loc[row["period"], "usd_kzt_avg_source"] = "manual_nbk"
    thin = (table["published_days"] < MIN_DAYS_FOR_AVERAGE) & (
        table["usd_kzt_avg_source"] == "daily_api")
    if thin.any():
        months = ", ".join(str(p) for p in table.index[thin])
        raise ValueError(
            f"Too few published daily rates for: {months}. "
            "Add a documented value to data/raw/manual_values.csv."
        )
    return table


def build_exchange_rate():
    """Run all exchange-rate transformations and return the monthly table."""
    daily, was_missing = fill_calendar_gaps(read_daily_rates())
    table = monthly_rates(daily, was_missing)
    table = apply_manual_averages(table, read_manual_values())
    return table.reset_index()


# ---------------------------------------------------------------------------
# Merge and save
# ---------------------------------------------------------------------------

def add_fx_in_usd(monthly):
    """Foreign-currency deposits in million USD (at the end-of-month rate).

    Deposits are end-of-month stocks, so they are converted at the
    end-of-month rate. This removes the pure revaluation effect.
    """
    monthly["fx_total_usd_mn"] = monthly["fx_total"] / monthly["usd_kzt_eom"]
    return monthly


def merge_monthly(deposits, rates):
    """One row per month; keep only months present in both tables."""
    monthly = deposits.merge(rates, on="period", how="inner")
    return add_fx_in_usd(monthly)


def save(table, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    table.to_csv(path, index=False, float_format="%.4f")


def main():
    deposits = build_deposits()
    rates = build_exchange_rate()
    monthly = merge_monthly(deposits, rates)

    save(deposits, OUT_DEPOSITS)
    save(rates, OUT_RATES)
    save(monthly, OUT_MONTHLY)

    first, last = monthly["period"].iloc[0], monthly["period"].iloc[-1]
    latest = monthly.iloc[-1]
    print(f"Deposits:      {len(deposits)} months -> {OUT_DEPOSITS}")
    print(f"Exchange rate: {len(rates)} months -> {OUT_RATES}")
    print(f"Merged:        {len(monthly)} months ({first} to {last}) -> {OUT_MONTHLY}")
    print(f"Latest ({last}): dollarization {latest['dollarization_pct']:.1f}%, "
          f"USD/KZT average {latest['usd_kzt_avg']:.2f}")


if __name__ == "__main__":
    main()
