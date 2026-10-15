"""Tests for the added transformations and the robustness engine."""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import ingest  # noqa: E402
import robustness  # noqa: E402


def test_constant_rate_dollarization_equals_actual_in_base_month():
    monthly = pd.DataFrame({
        "period": pd.PeriodIndex(["2016-01", "2016-02"], freq="M"),
        "kzt_total": [100.0, 100.0],
        "fx_total": [100.0, 200.0],          # FX doubles only because the
        "usd_kzt_eom": [100.0, 200.0],       # tenge halves: pure revaluation
    })
    monthly = ingest.add_fx_in_usd(monthly)
    monthly = ingest.add_constant_rate_dollarization(monthly, base="2016-01")
    assert monthly["dollarization_const_pct"].iloc[0] == pytest.approx(50.0)
    # Same USD amount, so the constant-rate share does not move.
    assert monthly["dollarization_const_pct"].iloc[1] == pytest.approx(50.0)


def test_monthly_volatility_is_zero_for_a_flat_rate_and_fills_thin_months():
    days = pd.date_range("2020-01-01", "2020-03-31", freq="D")
    daily = pd.Series(100.0, index=days)
    daily["2020-03-01":] = np.linspace(100, 110, 31)
    published = pd.Series([31, 3, 31],
                          index=pd.period_range("2020-01", periods=3, freq="M"))
    vol = ingest.monthly_volatility(daily, published, min_days=15)
    assert vol[pd.Period("2020-01", freq="M")] == pytest.approx(0.0)
    assert vol[pd.Period("2020-03", freq="M")] > 0
    # February has too few published days: filled between its neighbours.
    feb = vol[pd.Period("2020-02", freq="M")]
    assert vol.iloc[0] <= feb <= vol.iloc[2]


def test_logit_back_transform_round_trip():
    pct = np.array([5.0, 19.2, 80.0])
    logit = np.log(pct / (100 - pct))
    back = robustness.to_percent(logit, "logit_dollarization")
    assert back == pytest.approx(pct)


def test_reference_variant_reproduces_the_main_model():
    table = robustness.build_table()
    hold = robustness.holdout_months(table)
    spec = robustness.variants()[0]
    row = robustness.run_variant(table, spec, hold)
    artifact = __import__("json").loads(
        Path("model/artifact.json").read_text(encoding="utf-8"))
    assert row["rmse_ratio"] == pytest.approx(
        artifact["benchmark"]["rmse_ratio"], rel=1e-9)
