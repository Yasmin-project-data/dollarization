"""
Model layer: processed data -> driver model -> model/artifact.json.

Follows docs/preregistration.md, written before any estimation.

Reads:  data/processed/monthly.csv   (built by src/ingest.py)
Writes: (in progress) outputs/ tables and model/artifact.json

Run from the project folder:
    python src/model.py
"""

import itertools
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy import stats
from statsmodels.stats.diagnostic import (acorr_breusch_godfrey,
                                          breaks_cusumolsresid,
                                          het_breuschpagan)
from statsmodels.stats.outliers_influence import variance_inflation_factor
from statsmodels.stats.stattools import jarque_bera
from statsmodels.tools.sm_exceptions import InterpolationWarning
from statsmodels.tsa.ardl import UECM
from statsmodels.tsa.stattools import adfuller, kpss, zivot_andrews

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


# ---------------------------------------------------------------------------
# Integration: unit-root tests (pre-registration, section 3)
# ---------------------------------------------------------------------------
# ADF has the null "unit root", KPSS has the null "stationary": two tests with
# opposite nulls. Zivot-Andrews allows one break in the level, because the
# sample spans 2020 and 2022. All tests use the estimation sample only.

SIGNIFICANCE = 0.05
OUT_DIR = Path("outputs")
OUT_UNIT_ROOTS = OUT_DIR / "unit_roots.csv"


def run_unit_root_tests(series):
    """ADF (lags by AIC), KPSS (automatic bandwidth) and Zivot-Andrews p-values.

    All three use a constant and no trend. Returns the three p-values and the
    break month that Zivot-Andrews picks.
    """
    series = series.dropna()
    adf_p = adfuller(series, regression="c", autolag="AIC",
                     result_object=False)[1]
    with warnings.catch_warnings():
        # KPSS p-values are interpolated from a table and clipped at 0.01/0.10
        warnings.simplefilter("ignore", InterpolationWarning)
        kpss_p = kpss(series, regression="c", nlags="auto",
                      result_object=False)[1]
    za_stat, za_p, _, _, break_pos = zivot_andrews(
        series, regression="c", autolag="AIC")
    return {
        "adf_p": adf_p,
        "kpss_p": kpss_p,
        "za_p": za_p,
        "za_break": str(series.index[break_pos]),
    }


def classify_stationarity(adf_p, kpss_p, level=SIGNIFICANCE):
    """Combine the two opposite-null tests.

    stationary:   ADF rejects the unit root and KPSS keeps stationarity
    unit root:    ADF keeps the unit root and KPSS rejects stationarity
    inconclusive: the two tests disagree
    """
    adf_rejects = adf_p < level
    kpss_rejects = kpss_p < level
    if adf_rejects and not kpss_rejects:
        return "stationary"
    if not adf_rejects and kpss_rejects:
        return "unit root"
    return "inconclusive"


def integration_order(series):
    """I(0) if the level is stationary, I(1) if the first difference is."""
    levels = run_unit_root_tests(series)
    diffs = run_unit_root_tests(series.diff())
    level_verdict = classify_stationarity(levels["adf_p"], levels["kpss_p"])
    diff_verdict = classify_stationarity(diffs["adf_p"], diffs["kpss_p"])
    if level_verdict == "stationary":
        order = "I(0)"
    elif diff_verdict == "stationary":
        order = "I(1)"
    else:
        order = "unclear"
    return levels, diffs, level_verdict, diff_verdict, order


def unit_root_table(estimation):
    """One row per series: tests in levels and first differences, and the order."""
    rows = []
    for name in MODEL_COLUMNS:
        levels, diffs, level_verdict, diff_verdict, order = integration_order(
            estimation[name])
        rows.append({
            "series": name,
            "level_adf_p": levels["adf_p"],
            "level_kpss_p": levels["kpss_p"],
            "level_verdict": level_verdict,
            "level_za_p": levels["za_p"],
            "level_za_break": levels["za_break"],
            "diff_adf_p": diffs["adf_p"],
            "diff_kpss_p": diffs["kpss_p"],
            "diff_verdict": diff_verdict,
            "order": order,
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Estimation: ARDL in error-correction form (UECM) and the bounds test
# ---------------------------------------------------------------------------
# Pre-registration, section 3. The unrestricted error-correction model is the
# ARDL rewritten in levels and differences, so the bounds test and the
# long-run coefficients come from the same estimated equation. Brent enters
# with a one-month lag (it is published late), so its column is shifted once.

REGRESSORS = ["depreciation_1m", "rate_spread", "inflation_yoy_pct",
              "log_brent_lag1"]
MAX_LAG = 3
BOUNDS_CASE = 3          # unrestricted constant, no trend
OUT_COEFFICIENTS = OUT_DIR / "coefficients.csv"
OUT_BOUNDS = OUT_DIR / "bounds_test.csv"


def add_regressors(table):
    """Add the lagged Brent column used as the fourth regressor."""
    table = table.copy()
    table["log_brent_lag1"] = table["log_brent"].shift(1)
    return table


def hac_lags(n_obs):
    """Newey-West rule of thumb for the number of autocovariance lags."""
    return int(4 * (n_obs / 100) ** (2 / 9))


def make_uecm(data, order):
    """Build (not fit) the error-correction model for a given order.

    `order` is (lags of the dependent variable, lags of each regressor).
    """
    lags = dict(zip(REGRESSORS, order[1:]))
    return UECM(data[DEPENDENT], order[0], data[REGRESSORS], lags, trend="c")


def select_order(estimation, max_lag=MAX_LAG):
    """Choose the lag orders by AIC over every combination up to `max_lag`.

    Every regressor needs at least one lag, because the error-correction form
    contains the lagged level of each variable. Returns the best order, the
    number of specifications estimated and the full AIC table.
    """
    rows = []
    lag_range = range(1, max_lag + 1)
    for order in itertools.product(lag_range, repeat=1 + len(REGRESSORS)):
        try:
            aic = make_uecm(estimation, order).fit().aic
        except ValueError:
            continue
        rows.append({"order": order, "aic": aic})
    table = pd.DataFrame(rows).sort_values("aic").reset_index(drop=True)
    return table["order"].iloc[0], len(table), table


def fit_uecm(estimation, order):
    """Fit the chosen model; standard errors are HAC (Newey-West)."""
    uecm = make_uecm(estimation, order)
    result = uecm.fit(cov_type="HAC",
                      cov_kwds={"maxlags": hac_lags(len(estimation))})
    return uecm, result


def run_bounds_test(uecm):
    """Pesaran-Shin-Smith bounds F-test for a long-run relationship.

    The null is "no long-run relationship". The statistic is compared with
    the lower bound (all variables I(0)) and the upper bound (all I(1)).
    """
    test = uecm.fit().bounds_test(case=BOUNDS_CASE)
    crit = test.critical_values.loc[95.0]
    return {
        "f_stat": float(test.statistic),
        "lower_p": float(test.pvalue["lower"]),
        "upper_p": float(test.pvalue["upper"]),
        "crit_5pct_lower": float(crit["lower"]),
        "crit_5pct_upper": float(crit["upper"]),
        "conclusion": bounds_conclusion(
            test.pvalue["lower"], test.pvalue["upper"]),
    }


def bounds_conclusion(lower_p, upper_p, level=SIGNIFICANCE):
    """Cointegration if even the I(1) bound is passed; none if the I(0) bound is
    not passed; otherwise inconclusive."""
    if upper_p < level:
        return "cointegration"
    if lower_p >= level:
        return "no cointegration"
    return "inconclusive"


def long_run_coefficients(result):
    """Long-run effect of each regressor: -theta / rho, with rho the
    coefficient on the lagged dependent level (the speed of adjustment)."""
    params = result.params
    rho = params[f"{DEPENDENT}.L1"]
    return {name: -params[f"{name}.L1"] / rho for name in REGRESSORS}


def coefficient_table(result):
    """Names, estimates, HAC standard errors and p-values."""
    return pd.DataFrame({
        "name": result.params.index,
        "coef": result.params.values,
        "std_err": result.bse.values,
        "p_value": result.pvalues.values,
    })


# ---------------------------------------------------------------------------
# Diagnostics (pre-registration, section 3)
# ---------------------------------------------------------------------------
# All tests run on the residuals and design matrix of the estimated equation.
# A p-value below 5% is a failure of that test; failures are reported.

BG_LAGS = 6              # serial correlation: six monthly lags
CHOW_DATES = ["2020-03", "2022-03"]
OUT_DIAGNOSTICS = OUT_DIR / "diagnostics.csv"


def design(uecm):
    """The estimated equation as arrays: dependent (first difference of the
    indicator), regressors with constant, and the month of each row.

    statsmodels keeps these in private attributes; the first rows are lost
    to the lags, so the months are the last rows of the data index.
    """
    y = np.asarray(uecm._y).squeeze()
    x = np.asarray(uecm._x)
    months = pd.PeriodIndex(list(uecm.data.row_labels)[-len(y):], freq="M")
    return y, x, months


def ols_of(uecm):
    """The same equation as plain OLS, for the residual tests."""
    y, x, _ = design(uecm)
    return sm.OLS(y, x).fit()


def chow_test(uecm, break_month):
    """Chow F-test: do the coefficients differ before and after `break_month`?"""
    y, x, months = design(uecm)
    after = np.asarray(months >= pd.Period(break_month, freq="M"))
    k = x.shape[1]
    n1, n2 = (~after).sum(), after.sum()
    if min(n1, n2) <= k:
        return float("nan")
    ssr_all = sm.OLS(y, x).fit().ssr
    ssr_split = (sm.OLS(y[~after], x[~after]).fit().ssr
                 + sm.OLS(y[after], x[after]).fit().ssr)
    f_stat = ((ssr_all - ssr_split) / k) / (ssr_split / (n1 + n2 - 2 * k))
    return float(stats.f.sf(f_stat, k, n1 + n2 - 2 * k))


def max_vif(uecm):
    """Largest variance inflation factor among the regressors (no constant)."""
    _, x, _ = design(uecm)
    x = x[:, 1:]  # first column is the constant
    return float(max(variance_inflation_factor(x, i) for i in range(x.shape[1])))


def run_diagnostics(uecm):
    """Serial correlation, heteroskedasticity, normality, stability, VIF, breaks."""
    ols = ols_of(uecm)
    diagnostics = {
        "breusch_godfrey_p": float(acorr_breusch_godfrey(
            ols, nlags=BG_LAGS, result_object=False)[1]),
        "breusch_pagan_p": float(het_breuschpagan(ols.resid, ols.model.exog)[1]),
        "jarque_bera_p": float(jarque_bera(ols.resid)[1]),
        "cusum_p": float(breaks_cusumolsresid(ols.resid, ols.df_model + 1)[1]),
        "max_vif": max_vif(uecm),
    }
    diagnostics["cusum_stable"] = diagnostics["cusum_p"] >= SIGNIFICANCE
    for month in CHOW_DATES:
        diagnostics[f"chow_{month.replace('-', '_')}_p"] = chow_test(uecm, month)
    return diagnostics


# ---------------------------------------------------------------------------
# Out-of-sample evaluation (pre-registration, section 4)
# ---------------------------------------------------------------------------
# The coefficients come from the estimation sample only. For each hold-out
# month the model predicts the change in dollarization from last month's
# observed value and this month's factors (a nowcast), and the benchmark is
# the random walk: no change from last month.

OUT_HOLDOUT = OUT_DIR / "holdout_forecast.csv"


def holdout_forecast(full, order, params, holdout_index):
    """One-step-ahead forecasts for the hold-out months with fixed coefficients.

    `full` holds the estimation and hold-out months. The equation is rebuilt
    on all of them with the same order, so its rows line up with `params`;
    the parameters are never re-estimated.
    """
    uecm = make_uecm(full, order)
    y_change, x, months = design(uecm)
    keep = np.asarray(months.isin(holdout_index))
    predicted_change = x[keep] @ np.asarray(params)
    last_month = full[DEPENDENT].shift(1).loc[months[keep]].values
    actual = full[DEPENDENT].loc[months[keep]].values
    return pd.DataFrame({
        "period": months[keep].astype(str),
        "actual": actual,
        "model": last_month + predicted_change,
        "benchmark": last_month,
    })


def forecast_accuracy(forecast):
    """RMSE and MAE of the model and the benchmark, and their ratios."""
    model_error = forecast["actual"] - forecast["model"]
    bench_error = forecast["actual"] - forecast["benchmark"]
    rmse_model = float(np.sqrt((model_error ** 2).mean()))
    rmse_bench = float(np.sqrt((bench_error ** 2).mean()))
    mae_model = float(model_error.abs().mean())
    mae_bench = float(bench_error.abs().mean())
    ratio = rmse_model / rmse_bench
    return {
        "name": "Random walk",
        "rmse_model": rmse_model, "rmse_benchmark": rmse_bench,
        "rmse_ratio": ratio,
        "mae_model": mae_model, "mae_benchmark": mae_bench,
        "mae_ratio": mae_model / mae_bench,
        "n_holdout": int(len(forecast)),
        "winner": "model" if ratio < 1 else "benchmark",
    }


def main():
    table = build_model_table(read_monthly())
    estimation, holdout = split_sample(table)
    print(f"Sample:     {estimation.index[0]} to {holdout.index[-1]} "
          f"({len(estimation) + len(holdout)} months)")
    print(f"Estimation: {estimation.index[0]} to {estimation.index[-1]} "
          f"({len(estimation)} months)")
    print(f"Hold-out:   {holdout.index[0]} to {holdout.index[-1]} "
          f"({len(holdout)} months)")

    unit_roots = unit_root_table(estimation)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    unit_roots.to_csv(OUT_UNIT_ROOTS, index=False, float_format="%.4f")
    print(f"Unit roots: -> {OUT_UNIT_ROOTS}")
    print(unit_roots[["series", "level_adf_p", "level_kpss_p",
                      "level_verdict", "diff_verdict", "order"]]
          .to_string(index=False))

    full = add_regressors(table)
    est = full.loc[estimation.index]
    order, n_specs, _ = select_order(est)
    uecm, result = fit_uecm(est, order)
    bounds = run_bounds_test(uecm)
    coefficients = coefficient_table(result)
    coefficients.to_csv(OUT_COEFFICIENTS, index=False, float_format="%.6f")
    pd.DataFrame([bounds]).to_csv(OUT_BOUNDS, index=False, float_format="%.6f")
    print(f"Order {order} chosen by AIC among {n_specs} specifications")
    print(coefficients.to_string(index=False))
    print(f"Long run: { {k: round(v, 3) for k, v in long_run_coefficients(result).items()} }")
    diagnostics = run_diagnostics(uecm)
    pd.DataFrame([diagnostics]).to_csv(OUT_DIAGNOSTICS, index=False,
                                       float_format="%.6f")
    print("Diagnostics: " + ", ".join(
        f"{k}={v:.3f}" if isinstance(v, float) else f"{k}={v}"
        for k, v in diagnostics.items()))
    sample = full.loc[estimation.index[0]:holdout.index[-1]]
    forecast = holdout_forecast(sample, order, result.params.values,
                                holdout.index)
    forecast.to_csv(OUT_HOLDOUT, index=False, float_format="%.4f")
    accuracy = forecast_accuracy(forecast)
    print(f"Hold-out ({accuracy['n_holdout']} months): RMSE model "
          f"{accuracy['rmse_model']:.3f} vs random walk "
          f"{accuracy['rmse_benchmark']:.3f}, ratio "
          f"{accuracy['rmse_ratio']:.3f}; MAE ratio "
          f"{accuracy['mae_ratio']:.3f} -> {accuracy['winner']} wins")
    print(f"Bounds test: F = {bounds['f_stat']:.2f}, 5% bounds "
          f"[{bounds['crit_5pct_lower']:.2f}, {bounds['crit_5pct_upper']:.2f}] "
          f"-> {bounds['conclusion']}")


if __name__ == "__main__":
    main()
