"""Unit tests for the data preparation in src/model.py.

Run from the project folder:
    python -m pytest
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import model  # noqa: E402


def make_monthly(n=6):
    index = pd.period_range("2020-01", periods=n, freq="M", name="period")
    return pd.DataFrame({
        "dollarization_pct": np.linspace(30, 25, n),
        "usd_kzt_avg": [400.0, 404.0, 404.0, 400.0, 410.0, 410.0][:n],
        "rate_spread": 5.0,
        "inflation_yoy_pct": 7.0,
        "brent_usd": [60.0, 70.0, 80.0, 90.0, 100.0, np.nan][:n],
    }, index=index)


def test_depreciation_is_log_percent_change():
    out = model.add_depreciation(make_monthly())
    assert pd.isna(out["depreciation_1m"].iloc[0])
    assert out["depreciation_1m"].iloc[1] == pytest.approx(100 * np.log(404 / 400))
    assert out["depreciation_1m"].iloc[2] == 0.0
    assert out["depreciation_1m"].iloc[3] < 0  # tenge strengthened


def test_log_brent():
    out = model.add_log_brent(make_monthly())
    assert out["log_brent"].iloc[1] == pytest.approx(np.log(70.0))
    assert pd.isna(out["log_brent"].iloc[5])


def test_model_table_has_exactly_the_preregistered_columns():
    table = model.build_model_table(make_monthly())
    assert list(table.columns) == [
        "dollarization_pct", "depreciation_1m", "rate_spread",
        "inflation_yoy_pct", "log_brent"]


def test_last_complete_month_ignores_missing_brent():
    table = model.build_model_table(make_monthly())
    assert table["log_brent"].isna().iloc[-1]
    assert model.last_complete_month(table) == pd.Period("2020-06", freq="M")


def test_split_puts_the_last_share_into_the_holdout():
    index = pd.period_range("2016-01", periods=100, freq="M")
    table = pd.DataFrame(1.0, index=index, columns=model.MODEL_COLUMNS)
    estimation, holdout = model.split_sample(table)
    assert len(holdout) == 20
    assert len(estimation) == 80
    assert estimation.index[-1] + 1 == holdout.index[0]
    assert estimation.index.intersection(holdout.index).empty


def test_split_starts_at_the_sample_start():
    index = pd.period_range("2012-01", periods=150, freq="M")
    table = pd.DataFrame(1.0, index=index, columns=model.MODEL_COLUMNS)
    estimation, _ = model.split_sample(table)
    assert estimation.index[0] == model.SAMPLE_START


def test_classify_stationarity_combines_opposite_nulls():
    assert model.classify_stationarity(adf_p=0.001, kpss_p=0.50) == "stationary"
    assert model.classify_stationarity(adf_p=0.60, kpss_p=0.01) == "unit root"
    assert model.classify_stationarity(adf_p=0.001, kpss_p=0.01) == "inconclusive"
    assert model.classify_stationarity(adf_p=0.60, kpss_p=0.50) == "inconclusive"


def test_integration_order_of_synthetic_series():
    rng = np.random.default_rng(42)  # fixed seed
    index = pd.period_range("2016-01", periods=200, freq="M")
    noise = pd.Series(rng.normal(size=200), index=index)
    walk = noise.cumsum()
    assert model.integration_order(noise)[-1] == "I(0)"
    assert model.integration_order(walk)[-1] == "I(1)"


def test_preregistered_sample_on_real_data():
    """docs/preregistration.md: about 128 months, hold-out from 2024-07."""
    table = model.build_model_table(model.read_monthly())
    estimation, holdout = model.split_sample(table)
    assert estimation.index[0] == pd.Period("2016-01", freq="M")
    assert holdout.index[0] == pd.Period("2024-07", freq="M")
    assert len(estimation) + len(holdout) == 128
    assert estimation[model.MODEL_COLUMNS].drop(columns="log_brent").notna().all().all()
