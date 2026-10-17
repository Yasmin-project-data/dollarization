"""
Feedback analysis: does dollarization move the exchange rate?

The main model (src/model.py) explains dollarization by the exchange rate and
other factors. This script asks the reverse question, suggested by our
instructor: when households hold more of their deposits in foreign currency,
does the tenge weaken afterwards? Both directions are estimated at once in a
small vector autoregression (VAR), where every variable is explained by the
past of all of them.

Variables (all monthly, all stationary):
    d_oil          change in log Brent price, %
    d_spread       change in the KZT minus FX deposit rate spread, pp
    depreciation   change in log USD/KZT, % (positive = tenge weaker)
    d_dollar       change in dollarization, pp

Timing matters. Dollarization is an end-of-month stock valued at the
end-of-month exchange rate, so the main specification measures depreciation
from end-of-month rates too. With the monthly AVERAGE rate, a fall of the
tenge late in month t shows up in dollarization in month t but in the
average-rate depreciation only in month t+1, which looks like "dollarization
predicts depreciation" when it is only a timing artefact. Both timings are
reported (variants V1-V4).

What is reported:
  - Granger causality F-tests in both directions
    (H0: past values of one variable do not help predict the other)
  - Impulse response of depreciation to a one-standard-deviation shock to
    dollarization, 12 months, with 95% Monte Carlo bands. Cholesky order:
    oil, spread, depreciation, dollarization, so a dollarization shock cannot
    move the exchange rate in the same month: their same-month correlation
    is mostly mechanical revaluation, not behaviour.
  - Forecast-error variance decomposition: share of depreciation's 12-month
    forecast variance due to dollarization shocks
  - Stability, residual whiteness (Portmanteau) and normality

Sample: 2016-01 to the latest month (after the move to a floating tenge).
This is an explanatory analysis, not a forecast, so no hold-out is kept.
It was added after the pre-registration (docs/deviations.md, entry 5) and
does not change the main model.

Reads:  data/processed/monthly.csv
Writes: outputs/feedback_granger.csv, outputs/feedback_irf.csv,
        model/feedback.json (read by the website)

Run from the project folder:
    python src/feedback.py
"""

import json
import warnings

import numpy as np
import pandas as pd
from statsmodels.tsa.api import VAR

import model as m

OUT_GRANGER = m.OUT_DIR / "feedback_granger.csv"
OUT_IRF = m.OUT_DIR / "feedback_irf.csv"
OUT_JSON = m.ARTIFACT_FILE.parent / "feedback.json"

START = m.SAMPLE_START          # 2016-01, as in the main model
MAX_LAGS = 6                    # AIC searches 1..6 monthly lags
HORIZON = 12                    # months shown in the impulse response
BAND_REPLICATIONS = 1000        # Monte Carlo draws for the 95% band
SEED = 2026                     # fixed, so the band is reproducible
ORDER = ["d_oil", "d_spread", "depreciation", "d_dollar"]   # Cholesky order

VARIANTS = [
    {"id": "V1", "rate": "usd_kzt_eom", "measure": "dollarization_pct",
     "label": "End-of-month rate, dollarization (main)"},
    {"id": "V2", "rate": "usd_kzt_eom", "measure": "dollarization_const_pct",
     "label": "End-of-month rate, dollarization at constant rate"},
    {"id": "V3", "rate": "usd_kzt_avg", "measure": "dollarization_pct",
     "label": "Monthly average rate, dollarization (timing mismatch)"},
    {"id": "V4", "rate": "usd_kzt_avg", "measure": "dollarization_const_pct",
     "label": "Monthly average rate, dollarization at constant rate"},
]
MAIN = "V1"


# ---------------------------------------------------------------------------
# Data and estimation
# ---------------------------------------------------------------------------

def build_var_data(monthly, rate="usd_kzt_eom", measure="dollarization_pct",
                   start=START):
    """The four stationary series, in Cholesky order, without missing months."""
    data = pd.DataFrame({
        "d_oil": 100 * np.log(monthly["brent_usd"]).diff(),
        "d_spread": monthly["rate_spread"].diff(),
        "depreciation": 100 * np.log(monthly[rate]).diff(),
        "d_dollar": monthly[measure].diff(),
    })[ORDER]
    return data.loc[start:].dropna()


def fit_var(data, max_lags=MAX_LAGS):
    """VAR with a constant; lags by AIC, at least one."""
    selection = VAR(data).select_order(max_lags)
    lags = max(1, int(selection.selected_orders["aic"]))
    return VAR(data).fit(lags)


def granger(result, cause, effect):
    test = result.test_causality(effect, [cause], kind="f")
    return float(test.test_statistic), float(test.pvalue)


def summarise(result, variant):
    """One row of the comparison table."""
    k_dollar = ORDER.index("d_dollar")
    k_fx = ORDER.index("depreciation")
    f_dx, p_dx = granger(result, "d_dollar", "depreciation")
    f_xd, p_xd = granger(result, "depreciation", "d_dollar")
    irf = result.irf(HORIZON).orth_irfs[:, k_fx, k_dollar]
    data = result.model.endog
    return {
        "id": variant["id"],
        "variant": variant["label"],
        "n_obs": int(result.nobs),
        "lags": int(result.k_ar),
        "dollar_to_fx_F": f_dx,
        "dollar_to_fx_p": p_dx,
        "fx_to_dollar_F": f_xd,
        "fx_to_dollar_p": p_xd,
        "irf_fx_peak": float(irf[np.argmax(np.abs(irf))]),
        "irf_fx_cumulative_12m": float(irf.sum()),
        "fevd_fx_from_dollar_12m": float(
            result.fevd(HORIZON).decomp[k_fx, -1, k_dollar]),
        "same_month_corr": float(np.corrcoef(data[:, k_fx], data[:, k_dollar])[0, 1]),
        "stable": bool(result.is_stable()),
        "whiteness_p": float(result.test_whiteness(nlags=12).pvalue),
        "normality_p": float(result.test_normality().pvalue),
    }


def irf_table(result):
    """Response of depreciation to a dollarization shock, and the reverse,
    with 95% Monte Carlo bands."""
    k_dollar = ORDER.index("d_dollar")
    k_fx = ORDER.index("depreciation")
    irf = result.irf(HORIZON)
    lower, upper = irf.errband_mc(orth=True, repl=BAND_REPLICATIONS,
                                  signif=0.05, seed=SEED)
    return pd.DataFrame({
        "month": np.arange(HORIZON + 1),
        "fx_response": irf.orth_irfs[:, k_fx, k_dollar],
        "fx_lower": lower[:, k_fx, k_dollar],
        "fx_upper": upper[:, k_fx, k_dollar],
        "dollar_response": irf.orth_irfs[:, k_dollar, k_fx],
        "dollar_lower": lower[:, k_dollar, k_fx],
        "dollar_upper": upper[:, k_dollar, k_fx],
    })


def shock_sizes(result):
    """Size of a one-standard-deviation orthogonal shock (Cholesky diagonal)."""
    chol = np.linalg.cholesky(np.asarray(result.sigma_u))
    return {name: float(chol[i, i]) for i, name in enumerate(ORDER)}


def verdict(p, level=m.SIGNIFICANCE):
    return "significant" if p < level else "not significant"


def build_feedback(rows, irf, result, data):
    main = next(r for r in rows if r["id"] == MAIN)
    sizes = shock_sizes(result)
    return {
        "question": "Does dollarization move the tenge exchange rate?",
        "method": "VAR with lags chosen by AIC; Granger causality; "
                  "Cholesky impulse responses (oil, spread, depreciation, "
                  "dollarization) with 95% Monte Carlo bands",
        "sample": {"start": str(data.index[0]), "end": str(data.index[-1]),
                   "n_obs": main["n_obs"], "lags": main["lags"]},
        "granger": {
            "dollarization_to_fx_p": main["dollar_to_fx_p"],
            "dollarization_to_fx": verdict(main["dollar_to_fx_p"]),
            "fx_to_dollarization_p": main["fx_to_dollar_p"],
            "fx_to_dollarization": verdict(main["fx_to_dollar_p"]),
        },
        "shock_size_dollarization_pp": sizes["d_dollar"],
        "shock_size_depreciation_pct": sizes["depreciation"],
        "fevd_fx_from_dollar_12m": main["fevd_fx_from_dollar_12m"],
        "same_month_corr": main["same_month_corr"],
        "irf": irf.to_dict(orient="list"),
        "variants": rows,
    }


def main():
    warnings.simplefilter("ignore")
    monthly = m.read_monthly()
    rows, main_result, main_data = [], None, None
    for variant in VARIANTS:
        data = build_var_data(monthly, variant["rate"], variant["measure"])
        result = fit_var(data)
        rows.append(summarise(result, variant))
        if variant["id"] == MAIN:
            main_result, main_data = result, data
    irf = irf_table(main_result)

    m.OUT_DIR.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(OUT_GRANGER, index=False, float_format="%.4f")
    irf.to_csv(OUT_IRF, index=False, float_format="%.4f")
    feedback = build_feedback(rows, irf, main_result, main_data)
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(feedback, indent=2), encoding="utf-8")

    for r in rows:
        print(f"{r['id']}  {r['variant']:<55} lags {r['lags']}  "
              f"dollar->FX p={r['dollar_to_fx_p']:.3f}  "
              f"FX->dollar p={r['fx_to_dollar_p']:.3f}  "
              f"FEVD {100 * r['fevd_fx_from_dollar_12m']:.1f}%")
    print(f"-> {OUT_GRANGER}, {OUT_IRF}, {OUT_JSON}")


if __name__ == "__main__":
    main()
