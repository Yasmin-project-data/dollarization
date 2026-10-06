"""Unit tests for the transformation functions in src/ingest.py.

Run from the project folder:
    python -m pytest
"""

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import ingest  # noqa: E402


def test_parse_period():
    assert ingest.parse_period("01.10") == pd.Period("2010-01", freq="M")
    assert ingest.parse_period(" 12.25 ") == pd.Period("2025-12", freq="M")


def test_parse_number_removes_spaces_and_handles_empty():
    assert ingest.parse_number("1 935 789") == 1935789.0
    assert ingest.parse_number("1\xa0935\xa0789") == 1935789.0
    assert ingest.parse_number("12,5") == 12.5
    assert pd.isna(ingest.parse_number(float("nan")))


def test_dollarization_is_fx_share_in_percent():
    data = pd.DataFrame({"fx_total": [25.0], "total": [100.0]})
    data = ingest.add_dollarization(data)
    assert data["dollarization_pct"].iloc[0] == pytest.approx(25.0)


def test_add_totals_sums_components():
    row = {c: 1.0 for c in ingest.KZT_COLUMNS + ingest.FX_COLUMNS}
    data = ingest.add_totals(pd.DataFrame([row]))
    assert data["kzt_total"].iloc[0] == 4.0
    assert data["fx_total"].iloc[0] == 4.0


def test_fill_missing_with_zero_only_touches_value_columns():
    row = {c: float("nan") for c in ingest.KZT_COLUMNS + ingest.FX_COLUMNS}
    row["period"] = "x"
    data = ingest.fill_missing_with_zero(pd.DataFrame([row]))
    assert (data[ingest.KZT_COLUMNS + ingest.FX_COLUMNS] == 0).all().all()


def test_check_totals_accepts_rounding_and_rejects_real_gap():
    ok = pd.DataFrame({"period": ["a"], "kzt_total": [60.0],
                       "fx_total": [40.0], "total": [102.0]})
    ingest.check_totals(ok)  # gap of 2 is within the tolerance of 5
    bad = ok.assign(total=[200.0])
    with pytest.raises(ValueError):
        ingest.check_totals(bad)


def test_fill_calendar_gaps_carries_last_rate_forward():
    daily = pd.Series(
        [450.0, 452.0],
        index=pd.to_datetime(["2020-01-01", "2020-01-04"]),
    )
    filled, was_missing = ingest.fill_calendar_gaps(daily)
    assert len(filled) == 4
    assert filled["2020-01-02"] == 450.0
    assert filled["2020-01-03"] == 450.0
    assert list(was_missing) == [False, True, True, False]


def test_monthly_rates_average_end_of_month_and_published_days():
    daily = pd.Series(
        [100.0, 200.0],
        index=pd.to_datetime(["2020-01-01", "2020-01-03"]),
    )
    filled, was_missing = ingest.fill_calendar_gaps(daily)
    table = ingest.monthly_rates(filled, was_missing)
    row = table.loc[pd.Period("2020-01", freq="M")]
    assert row["usd_kzt_avg"] == pytest.approx((100 + 100 + 200) / 3)
    assert row["usd_kzt_eom"] == 200.0
    assert row["published_days"] == 2


def test_parse_month_ru():
    assert ingest.parse_month_ru("Январь 2011 г.") == pd.Period("2011-01", freq="M")
    assert ingest.parse_month_ru("Декабрь 2025 г.") == pd.Period("2025-12", freq="M")


def test_parse_rate_handles_dash_and_decimal_comma():
    assert ingest.parse_rate("7,9") == 7.9
    assert pd.isna(ingest.parse_rate("-"))
    assert pd.isna(ingest.parse_rate(float("nan")))


def test_decode_month_header_undoes_excel_conversion():
    # 2010-2012 headers were read as day.month of 2026: 01.10 -> 2026-10-01
    assert ingest.decode_month_header(pd.Timestamp("2026-10-01")) == \
        pd.Period("2010-01", freq="M")
    # from 2013 on they were read as month.year: 01.13 -> 2013-01-01
    assert ingest.decode_month_header(pd.Timestamp("2013-01-01")) == \
        pd.Period("2013-01", freq="M")


def test_fx_in_usd_uses_end_of_month_rate():
    monthly = pd.DataFrame({"fx_total": [4800.0], "usd_kzt_eom": [480.0]})
    monthly = ingest.add_fx_in_usd(monthly)
    assert monthly["fx_total_usd_mn"].iloc[0] == pytest.approx(10.0)


def test_processed_monthly_matches_raw_rebuild():
    """The committed processed table must equal a fresh rebuild."""
    rebuilt = ingest.build_deposits()
    saved = pd.read_csv(ingest.OUT_DEPOSITS)
    assert len(rebuilt) == len(saved)
    assert saved["dollarization_pct"].iloc[-1] == pytest.approx(
        rebuilt["dollarization_pct"].iloc[-1], abs=1e-3)
