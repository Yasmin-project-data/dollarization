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


def test_hac_lags_rule_of_thumb():
    assert model.hac_lags(99) == 3
    assert model.hac_lags(102) == 4


def test_bounds_conclusion_three_outcomes():
    assert model.bounds_conclusion(lower_p=0.001, upper_p=0.02) == "cointegration"
    assert model.bounds_conclusion(lower_p=0.01, upper_p=0.20) == "inconclusive"
    assert model.bounds_conclusion(lower_p=0.30, upper_p=0.60) == "no cointegration"


def make_cointegrated(n=150):
    """y follows the regressors in the long run; fixed seed."""
    rng = np.random.default_rng(7)
    index = pd.period_range("2016-01", periods=n, freq="M")
    data = pd.DataFrame(
        {name: rng.normal(size=n).cumsum() for name in model.REGRESSORS},
        index=index)
    data[model.DEPENDENT] = data["rate_spread"] + rng.normal(scale=0.5, size=n)
    return data


def test_estimation_recovers_long_run_relationship():
    data = make_cointegrated()
    order = (1, 1, 1, 1, 1)
    uecm, result = model.fit_uecm(data, order)
    assert model.run_bounds_test(uecm)["conclusion"] == "cointegration"
    assert model.long_run_coefficients(result)["rate_spread"] == pytest.approx(
        1.0, abs=0.2)


def test_design_matrix_reproduces_the_fitted_coefficients():
    data = make_cointegrated()
    uecm, result = model.fit_uecm(data, (1, 1, 1, 1, 1))
    y, x, months = model.design(uecm)
    coefficients = np.linalg.lstsq(x, y, rcond=None)[0]
    assert coefficients == pytest.approx(result.params.values)
    assert months[0] == data.index[1]  # one observation lost to the lag
    assert len(months) == len(y)


def test_chow_test_detects_a_break_and_not_a_stable_model():
    rng = np.random.default_rng(3)
    data = make_cointegrated(200)
    stable, _ = model.fit_uecm(data, (1, 1, 1, 1, 1))
    assert model.chow_test(stable, "2024-01") > 0.01

    broken = data.copy()
    n_after = len(broken.loc["2024-01":])
    broken.loc["2024-01":, model.DEPENDENT] += 5 + rng.normal(size=n_after)
    unstable, _ = model.fit_uecm(broken, (1, 1, 1, 1, 1))
    assert model.chow_test(unstable, "2024-01") < 0.05


def test_diagnostics_return_every_preregistered_test():
    uecm, _ = model.fit_uecm(make_cointegrated(), (1, 1, 1, 1, 1))
    diagnostics = model.run_diagnostics(uecm)
    for key in ["breusch_godfrey_p", "breusch_pagan_p", "jarque_bera_p",
                "cusum_p", "cusum_stable", "max_vif",
                "chow_2020_03_p", "chow_2022_03_p"]:
        assert key in diagnostics
    assert diagnostics["max_vif"] >= 1.0


def test_holdout_forecast_reproduces_fitted_values_in_sample():
    """Applied to months the model was estimated on, the forecast function
    must return exactly the fitted values: this checks the alignment."""
    data = make_cointegrated()
    order = (1, 1, 1, 1, 1)
    _, result = model.fit_uecm(data, order)
    tail = data.index[-20:]
    forecast = model.holdout_forecast(data, order, result.params.values, tail)
    fitted_change = result.fittedvalues.loc[tail] if hasattr(
        result.fittedvalues, "loc") else result.fittedvalues[-20:]
    expected = data[model.DEPENDENT].shift(1).loc[tail].values + \
        np.asarray(fitted_change)
    assert forecast["model"].values == pytest.approx(expected)
    assert forecast["benchmark"].values == pytest.approx(
        data[model.DEPENDENT].shift(1).loc[tail].values)


def test_forecast_accuracy_ratio_and_winner():
    forecast = pd.DataFrame({
        "actual": [10.0, 11.0, 12.0],
        "model": [10.0, 11.0, 12.5],
        "benchmark": [9.0, 10.0, 11.0],
    })
    accuracy = model.forecast_accuracy(forecast)
    assert accuracy["rmse_benchmark"] == pytest.approx(1.0)
    assert accuracy["rmse_model"] == pytest.approx(np.sqrt(0.25 / 3))
    assert accuracy["winner"] == "model"
    worse = forecast.assign(model=[0.0, 0.0, 0.0])
    assert model.forecast_accuracy(worse)["winner"] == "benchmark"


def test_latest_contributions_add_up_to_the_actual_change():
    data = make_cointegrated()
    order = (2, 1, 1, 1, 1)
    _, result = model.fit_uecm(data, order)
    period, change, contributions = model.latest_contributions(
        data, data.iloc[:100], order, result.params)
    assert period == str(data.index[-1])
    assert change == pytest.approx(
        data[model.DEPENDENT].iloc[-1] - data[model.DEPENDENT].iloc[-2])
    assert sum(contributions.values()) == pytest.approx(change)
    assert set(contributions) == set(model.REGRESSORS) | {
        "own_dynamics", "error_correction", "constant", "residual"}


def test_next_month_regressors_hold_drivers_flat():
    data = make_cointegrated()
    order = (2, 1, 1, 1, 1)
    _, result = model.fit_uecm(data, order)
    names = list(result.params.index)
    row = dict(zip(names, model.next_month_regressors(data, order, names)))
    assert row["const"] == 1.0
    assert row["D.rate_spread.L0"] == 0.0           # driver flat next month
    assert row["rate_spread.L1"] == data["rate_spread"].iloc[-1]
    assert row["dollarization_pct.L1"] == data[model.DEPENDENT].iloc[-1]
    assert row["D.dollarization_pct.L1"] == pytest.approx(
        data[model.DEPENDENT].diff().iloc[-1])


def test_term_group_covers_every_coefficient_name():
    assert model.term_group("const") == "constant"
    assert model.term_group("dollarization_pct.L1") == "error_correction"
    assert model.term_group("D.dollarization_pct.L2") == "own_dynamics"
    assert model.term_group("D.rate_spread.L0") == "rate_spread"
    assert model.term_group("log_brent_lag1.L1") == "log_brent_lag1"
    with pytest.raises(ValueError):
        model.term_group("mystery.L1")


def test_committed_artifact_is_consistent():
    """The file the website reads: shapes agree, parts add up."""
    import json
    artifact = json.loads(model.ARTIFACT_FILE.read_text(encoding="utf-8"))
    coefficients = artifact["coefficients"]
    k = len(coefficients["names"])
    assert len(coefficients["values"]) == k
    assert len(coefficients["std_errors"]) == k
    assert len(coefficients["covariance"]) == k
    assert all(len(row) == k for row in coefficients["covariance"])
    assert len(artifact["scenario"]["base_regressors"]) == k
    latest = artifact["latest"]
    assert sum(latest["contributions"].values()) == pytest.approx(latest["change"])
    # standard errors are the square roots of the covariance diagonal
    diagonal = np.sqrt(np.diag(np.array(coefficients["covariance"])))
    assert diagonal == pytest.approx(coefficients["std_errors"])
    assert artifact["benchmark"]["winner"] in ("model", "benchmark")


def test_select_order_counts_every_specification():
    data = make_cointegrated()
    order, n_specs, table = model.select_order(data, max_lag=2)
    assert n_specs == 2 ** (1 + len(model.REGRESSORS))
    assert len(order) == 1 + len(model.REGRESSORS)
    assert table["aic"].is_monotonic_increasing


def test_preregistered_sample_on_real_data():
    """docs/preregistration.md: about 128 months, hold-out from 2024-07."""
    table = model.build_model_table(model.read_monthly())
    estimation, holdout = model.split_sample(table)
    assert estimation.index[0] == pd.Period("2016-01", freq="M")
    assert holdout.index[0] == pd.Period("2024-07", freq="M")
    assert len(estimation) + len(holdout) == 128
    assert estimation[model.MODEL_COLUMNS].drop(columns="log_brent").notna().all().all()
