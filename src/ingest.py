"""
Data layer: raw NBK Excel file -> clean monthly table.

Reads:  data/raw/deposits_individuals_nbk.xlsx  (never modified)
Writes: data/processed/deposits.csv

Run from the project folder:
    python src/ingest.py
"""

from pathlib import Path

import pandas as pd

RAW_FILE = Path("data/raw/deposits_individuals_nbk.xlsx")
OUT_FILE = Path("data/processed/deposits.csv")

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


def build_table(path=RAW_FILE):
    """Run all transformations in order and return the clean table."""
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


def main():
    data = build_table()
    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    data.to_csv(OUT_FILE, index=False, float_format="%.4f")

    first, last = data["period"].iloc[0], data["period"].iloc[-1]
    latest = data["dollarization_pct"].iloc[-1]
    print(f"Saved {len(data)} months ({first} to {last}) to {OUT_FILE}")
    print(f"Latest dollarization ({last}): {latest:.1f}%")


if __name__ == "__main__":
    main()
