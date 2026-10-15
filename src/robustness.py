"""
Robustness checks and literature-based extensions of the driver model.

The main, pre-registered model stays in src/model.py and is not changed here.
This script re-estimates variants of it and reports, for every variant, the
same few numbers so they can be compared side by side:

  Pre-registered robustness checks (docs/preregistration.md, section 6)
    R1  alternative sample: 2011-12 onwards, with a dummy for the floating
        exchange-rate regime from 2015-09
    R2  alternative specification: logit of the dependent variable
    R3  alternative measure: dollarization at a constant exchange rate
    R4  factor definition: 3-month instead of 1-month depreciation

  Added after the literature review (docs/deviations.md)
    L1  exchange-rate volatility as a fifth regressor
        (Ben Naceur, Hosny & Hadjian 2015; Cakir et al. 2022)
    L2  state dependence: depreciation x last month's dollarization level
        (Neanidis & Savva 2009: effects are stronger where dollarization is high)
    L3  step dummies for the breaks found by the Chow tests (2020-03, 2022-03)

Every variant follows the same rules as the main model: lags chosen by AIC
on the estimation months only (orders 1-3), HAC standard errors, the
Pesaran-Shin-Smith bounds test, and one-month-ahead forecasts on the SAME
hold-out months as the main model (2024-07 onwards) against a random walk.
The hold-out is never used to choose anything.

Reads:  data/processed/monthly.csv
Writes: outputs/robustness.csv

Run from the project folder:
    python src/robustness.py
"""

import itertools
import warnings

import numpy as np
import pandas as pd
from statsmodels.tsa.ardl import UECM

import model as main_model

OUT_FILE = main_model.OUT_DIR / "robustness.csv"
MAX_LAG = main_model.MAX_LAG
BASE_REGRESSORS = main_model.REGRESSORS          # the four pre-registered factors
MAIN_START = main_model.SAMPLE_START             # 2016-01
ALT_START = pd.Period("2011-12", freq="M")        # first month with y/y CPI
FLOAT_START = pd.Period("2015-09", freq="M")      # first full month of the float


# ---------------------------------------------------------------------------
# Data for all variants
# ---------------------------------------------------------------------------

def build_table():
    """All columns any variant needs, one row per month."""
    monthly = main_model.read_monthly()
    table = main_model.add_regressors(main_model.build_model_table(monthly))
    table["dollarization_const_pct"] = monthly["dollarization_const_pct"]
    table["usd_kzt_vol"] = monthly["usd_kzt_vol"]
    table["depreciation_3m"] = 100 * np.log(monthly["usd_kzt_avg"]).diff(3)
    d = table["dollarization_pct"]
    table["logit_dollarization"] = np.log(d / (100 - d))
    # State dependence: depreciation scaled by last month's level (0-1 share).
    table["dep_x_level"] = table["depreciation_1m"] * d.shift(1) / 100
    months = table.index
    table["float_regime"] = (months >= FLOAT_START).astype(float)
    table["break_2020"] = (months >= pd.Period("2020-03", freq="M")).astype(float)
    table["break_2022"] = (months >= pd.Period("2022-03", freq="M")).astype(float)
    return table


def holdout_months(table):
    """The main model's hold-out months, reused by every variant."""
    _, holdout = main_model.split_sample(table)
    return holdout.index


# ---------------------------------------------------------------------------
# One variant
# ---------------------------------------------------------------------------

def make_uecm(data, dependent, regressors, order, fixed):
    lags = dict(zip(regressors, order[1:]))
    fixed_data = data[fixed] if fixed else None
    return UECM(data[dependent], order[0], data[regressors], lags,
                trend="c", fixed=fixed_data)


def select_order(data, dependent, regressors, fixed):
    """AIC over every combination of orders 1..MAX_LAG (estimation months only)."""
    best, best_aic, n_specs = None, np.inf, 0
    for order in itertools.product(range(1, MAX_LAG + 1),
                                   repeat=1 + len(regressors)):
        try:
            aic = make_uecm(data, dependent, regressors, order, fixed).fit().aic
        except ValueError:
            continue
        n_specs += 1
        if aic < best_aic:
            best, best_aic = order, aic
    return best, n_specs


def forecast_levels(full, dependent, regressors, order, fixed, params, months):
    """One-step-ahead forecasts of the dependent variable's level."""
    uecm = make_uecm(full, dependent, regressors, order, fixed)
    _, x, rows = main_model.design(uecm)
    keep = np.asarray(rows.isin(months))
    last = full[dependent].shift(1).loc[rows[keep]].values
    return pd.Series(last + x[keep] @ np.asarray(params), index=rows[keep])


def to_percent(values, dependent):
    """Back-transform a logit forecast to percent; other measures unchanged."""
    if dependent == "logit_dollarization":
        return 100 / (1 + np.exp(-values))
    return values


def run_variant(table, spec, hold):
    """Estimate one variant and return its summary row."""
    dependent = spec["dependent"]
    regressors = spec["regressors"]
    fixed = spec.get("fixed", [])
    columns = [dependent] + regressors + fixed
    data = table[columns].loc[spec["start"]:hold[-1]].dropna()
    est = data.loc[:hold[0] - 1]

    order, n_specs = select_order(est, dependent, regressors, fixed)
    uecm = make_uecm(est, dependent, regressors, order, fixed)
    result = uecm.fit(cov_type="HAC",
                      cov_kwds={"maxlags": main_model.hac_lags(len(est))})
    bounds = uecm.fit().bounds_test(case=main_model.BOUNDS_CASE)
    params, pvalues = result.params, result.pvalues
    rho = params[f"{dependent}.L1"]

    # Forecasts in percent of deposits; the benchmark is the random walk of
    # the measure being modelled (for R3 that is the constant-rate measure).
    level = forecast_levels(data, dependent, regressors, order, fixed,
                            params.values, hold)
    measure = "dollarization_const_pct" if dependent == "dollarization_const_pct" \
        else "dollarization_pct"
    actual = table[measure].loc[level.index]
    previous = table[measure].shift(1).loc[level.index]
    model_error = actual - to_percent(level, dependent)
    bench_error = actual - previous
    rmse_model = float(np.sqrt((model_error ** 2).mean()))
    rmse_bench = float(np.sqrt((bench_error ** 2).mean()))

    dep_name = spec.get("depreciation", "depreciation_1m")
    row = {
        "id": spec["id"],
        "variant": spec["label"],
        "estimation": f"{est.index[0]} to {est.index[-1]}",
        "n_obs": int(result.nobs),
        "order": str(order),
        "n_specs_searched": n_specs,
        "ect_coef": float(rho),
        "ect_p": float(pvalues[f"{dependent}.L1"]),
        "depreciation_sr_coef": float(params[f"D.{dep_name}.L0"]),
        "depreciation_sr_p": float(pvalues[f"D.{dep_name}.L0"]),
        "depreciation_lr": float(-params[f"{dep_name}.L1"] / rho),
        "spread_lr": float(-params["rate_spread.L1"] / rho),
        "spread_level_p": float(pvalues["rate_spread.L1"]),
        "bounds_f": float(bounds.statistic),
        "bounds_conclusion": main_model.bounds_conclusion(
            bounds.pvalue["lower"], bounds.pvalue["upper"]),
        "rmse_model": rmse_model,
        "rmse_benchmark": rmse_bench,
        "rmse_ratio": rmse_model / rmse_bench,
    }
    for name in spec.get("report", []):
        key = name if name in params.index else f"{name}.L1"
        row[f"{name}_coef"] = float(params[key])
        row[f"{name}_p"] = float(pvalues[key])
    return row


# ---------------------------------------------------------------------------
# The variants
# ---------------------------------------------------------------------------

def variants():
    base = {"dependent": "dollarization_pct", "regressors": BASE_REGRESSORS,
            "start": MAIN_START}
    with_dep3 = ["depreciation_3m"] + BASE_REGRESSORS[1:]
    return [
        dict(base, id="M0", label="Main model (re-estimated, for reference)"),
        dict(base, id="R1", label="Sample from 2011-12, float-regime dummy",
             start=ALT_START, fixed=["float_regime"], report=["float_regime"]),
        dict(base, id="R2", label="Logit of dollarization",
             dependent="logit_dollarization"),
        dict(base, id="R3", label="Dollarization at constant exchange rate",
             dependent="dollarization_const_pct"),
        dict(base, id="R4", label="3-month depreciation",
             regressors=with_dep3, depreciation="depreciation_3m"),
        dict(base, id="L1", label="+ exchange-rate volatility",
             regressors=BASE_REGRESSORS + ["usd_kzt_vol"], report=["usd_kzt_vol"]),
        dict(base, id="L2", label="+ depreciation x dollarization level",
             fixed=["dep_x_level"], report=["dep_x_level"]),
        dict(base, id="L3", label="+ break dummies 2020-03 and 2022-03",
             fixed=["break_2020", "break_2022"],
             report=["break_2020", "break_2022"]),
    ]


def main():
    warnings.simplefilter("ignore")
    table = build_table()
    hold = holdout_months(table)
    rows = []
    for spec in variants():
        row = run_variant(table, spec, hold)
        rows.append(row)
        print(f"{row['id']}  {row['variant']:<45} order {row['order']:<16} "
              f"dep SR {row['depreciation_sr_coef']:+.3f} (p={row['depreciation_sr_p']:.3f})  "
              f"ECT {row['ect_coef']:+.3f}  bounds {row['bounds_conclusion']:<16} "
              f"RMSE ratio {row['rmse_ratio']:.3f}")
    result = pd.DataFrame(rows)
    main_model.OUT_DIR.mkdir(parents=True, exist_ok=True)
    result.to_csv(OUT_FILE, index=False, float_format="%.4f")
    total = int(result["n_specs_searched"].sum())
    print(f"\n{len(result)} variants, {total} specifications searched in total "
          f"-> {OUT_FILE}")


if __name__ == "__main__":
    main()
