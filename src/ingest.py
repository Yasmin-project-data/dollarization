"""
Data layer: raw files -> clean monthly tables.

Reads (never modified):
    data/raw/deposits_individuals_nbk.xlsx   household deposits by currency
    data/raw/usd_kzt_daily_nbk_api.csv        daily official USD/KZT rate
    data/raw/manual_values.csv                hand-transcribed values (documented)
    data/raw/deposit_rates_nbk.xlsx           household deposit rates, KZT and FX
    data/raw/cpi_mom_taldau.xls               CPI, month on month (Taldau)
Writes:
    data/processed/deposits.csv        deposits and dollarization, monthly
    data/processed/exchange_rate.csv   USD/KZT monthly average, end of month
    data/processed/deposit_rates.csv   household deposit rates, monthly
    data/processed/cpi.csv             CPI index and inflation, monthly
    data/processed/monthly.csv         everything merged, one row per month

Run from the project folder:
    python src/ingest.py
"""

from pathlib import Path

import pandas as pd

RAW_FILE = Path("data/raw/deposits_individuals_nbk.xlsx")
RATES_FILE = Path("data/raw/usd_kzt_daily_nbk_api.csv")
MANUAL_FILE = Path("data/raw/manual_values.csv")
DEPOSIT_RATES_FILE = Path("data/raw/deposit_rates_nbk.xlsx")
CPI_FILE = Path("data/raw/cpi_mom_taldau.xls")

OUT_DIR = Path("data/processed")
OUT_DEPOSITS = OUT_DIR / "deposits.csv"
OUT_RATES = OUT_DIR / "exchange_rate.csv"
OUT_DEPOSIT_RATES = OUT_DIR / "deposit_rates.csv"
OUT_CPI = OUT_DIR / "cpi.csv"
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
# Deposit interest rates
# ---------------------------------------------------------------------------
# The NBK web table was copied into Excel. Layout: months run across the
# columns (two columns per month: KZT and СКВ = freely convertible currency),
# deposit types run down the rows. The first row is the overall average
# rate on household deposits, which is the one we use.

RATES_ROW_LABEL = "Депозиты физических лиц"
FIRST_RATES_MONTH = pd.Period("2010-01", freq="M")


def decode_month_header(value):
    """Turn an Excel-mangled 'MM.YY' header back into a monthly period.

    When the table was pasted, Excel converted headers such as '01.10'
    (January 2010) into dates. For 2010-2012 it read them as day.month
    of the current year (01.10 -> 2026-10-01); from 2013 on it read them
    as month.year (01.13 -> 2013-01-01). Both cases are undone here.
    """
    if pd.isna(value):
        return None
    stamp = pd.Timestamp(value)
    if stamp.year == 2026 and stamp.month in (10, 11, 12) and stamp.day <= 12:
        return pd.Period(year=2000 + stamp.month, month=stamp.day, freq="M")
    return pd.Period(year=stamp.year, month=stamp.month, freq="M")


def parse_rate(value):
    """Rates are numbers; '-' means not published."""
    if pd.isna(value) or str(value).strip() in ("-", ""):
        return float("nan")
    return float(str(value).replace(",", "."))


def build_deposit_rates(path=DEPOSIT_RATES_FILE):
    """Return monthly household deposit rates in KZT and in FX, in percent."""
    if not path.exists():
        raise FileNotFoundError(f"Raw file not found: {path}")
    raw = pd.read_excel(path, header=None)

    labels = raw[0].fillna("").astype(str).str.strip()
    if RATES_ROW_LABEL not in labels.values:
        raise ValueError(f"Row '{RATES_ROW_LABEL}' not found in {path}.")
    values = raw[labels == RATES_ROW_LABEL].iloc[0]
    currency = raw.iloc[1]
    header = raw.iloc[0]

    rows = []
    for col in range(1, raw.shape[1], 2):
        if currency[col] != "KZT" or currency[col + 1] != "СКВ":
            raise ValueError(f"Unexpected currency labels in column {col}.")
        rows.append({
            "period": decode_month_header(header[col]),
            "rate_kzt": parse_rate(values[col]),
            "rate_fx": parse_rate(values[col + 1]),
        })
    rates = pd.DataFrame(rows)

    expected = pd.period_range(FIRST_RATES_MONTH, periods=len(rates), freq="M")
    if list(rates["period"]) != list(expected):
        raise ValueError("Month headers are not consecutive months from 2010-01.")
    rates["rate_spread"] = rates["rate_kzt"] - rates["rate_fx"]
    return rates


# ---------------------------------------------------------------------------
# Consumer prices (CPI)
# ---------------------------------------------------------------------------
# Taldau export: a title block, then one header row with month names
# ("Январь 2011 г.") and one row per region. Values are "previous month = 100"
# with a decimal comma ("101,7").

CPI_REGION = "РЕСПУБЛИКА КАЗАХСТАН"
MONTHS_RU = ["Январь", "Февраль", "Март", "Апрель", "Май", "Июнь", "Июль",
             "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"]


def parse_month_ru(text):
    """'Январь 2011 г.' -> Period('2011-01')."""
    parts = str(text).split()
    return pd.Period(year=int(parts[1]), month=MONTHS_RU.index(parts[0]) + 1,
                     freq="M")


def build_cpi(path=CPI_FILE):
    """Monthly CPI: m/m inflation, a chained index and y/y inflation."""
    if not path.exists():
        raise FileNotFoundError(f"Raw file not found: {path}")
    raw = pd.read_excel(path, header=None, dtype=str)  # needs the xlrd package

    first_col = raw[0].fillna("").str.strip()
    header_row = first_col[first_col == "Регион"].index
    data_row = first_col[first_col == CPI_REGION].index
    if len(header_row) != 1 or len(data_row) != 1:
        raise ValueError(f"Could not find header or '{CPI_REGION}' row in {path}.")

    header = raw.loc[header_row[0], 1:]
    values = raw.loc[data_row[0], 1:]
    cpi = pd.DataFrame({
        "period": [parse_month_ru(h) for h in header],
        "cpi_mom": [float(str(v).replace(",", ".")) for v in values],
    })

    expected = pd.period_range(cpi["period"].iloc[0], periods=len(cpi), freq="M")
    if list(cpi["period"]) != list(expected):
        raise ValueError("CPI months are not consecutive.")

    cpi["inflation_mom_pct"] = cpi["cpi_mom"] - 100
    # Chain the monthly changes into an index: December 2010 = 100.
    cpi["cpi_index"] = 100 * (cpi["cpi_mom"] / 100).cumprod()
    # Year-on-year inflation: product of the last 12 monthly changes.
    cpi["inflation_yoy_pct"] = 100 * (
        (cpi["cpi_mom"] / 100).rolling(12).apply(lambda x: x.prod(), raw=True) - 1
    )
    return cpi


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


def merge_monthly(deposits, rates, deposit_rates, cpi):
    """One row per deposit month.

    Exchange rate and deposit rates cover the whole deposit period.
    CPI starts later (2011), so earlier months get empty CPI values;
    the model chooses its own sample window.
    """
    monthly = deposits.merge(rates, on="period", how="inner")
    monthly = monthly.merge(deposit_rates, on="period", how="inner")
    monthly = monthly.merge(cpi, on="period", how="left")
    return add_fx_in_usd(monthly)


def save(table, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    table.to_csv(path, index=False, float_format="%.4f")


def main():
    deposits = build_deposits()
    rates = build_exchange_rate()
    deposit_rates = build_deposit_rates()
    cpi = build_cpi()
    monthly = merge_monthly(deposits, rates, deposit_rates, cpi)

    save(deposits, OUT_DEPOSITS)
    save(rates, OUT_RATES)
    save(deposit_rates, OUT_DEPOSIT_RATES)
    save(cpi, OUT_CPI)
    save(monthly, OUT_MONTHLY)

    first, last = monthly["period"].iloc[0], monthly["period"].iloc[-1]
    latest = monthly.iloc[-1]
    print(f"Deposits:      {len(deposits)} months -> {OUT_DEPOSITS}")
    print(f"Exchange rate: {len(rates)} months -> {OUT_RATES}")
    print(f"Deposit rates: {len(deposit_rates)} months -> {OUT_DEPOSIT_RATES}")
    print(f"CPI:           {len(cpi)} months -> {OUT_CPI}")
    print(f"Merged:        {len(monthly)} months ({first} to {last}) -> {OUT_MONTHLY}")
    print(f"Latest ({last}): dollarization {latest['dollarization_pct']:.1f}%, "
          f"USD/KZT average {latest['usd_kzt_avg']:.2f}, "
          f"deposit rates KZT {latest['rate_kzt']:.1f}% / FX {latest['rate_fx']:.1f}%, "
          f"inflation y/y {latest['inflation_yoy_pct']:.1f}%")


if __name__ == "__main__":
    main()
