"""
Report tables: every statistic behind the website, in one file for the
technical note.

The website shows only the final numbers. This script re-estimates the
pre-registered model with the same code as src/model.py (same sample, same
lag order chosen by AIC, same HAC standard errors) and writes all the evidence
as Markdown tables that can be pasted into the report:

  1. Sample and specification
  2. Unit-root tests (ADF, KPSS, Zivot-Andrews)
  3. Regression table (short run, HAC standard errors) and goodness of fit
  4. Long-run coefficients (delta-method standard errors)
  5. Bounds test for cointegration
  6. Residual diagnostics: serial correlation, heteroskedasticity, normality,
     stability, multicollinearity (VIF per regressor), structural breaks
  7. Out-of-sample accuracy against the random walk
  8. Robustness checks (read from outputs/robustness.csv if it exists)
  9. Feedback VAR: does dollarization move the tenge? (outputs/feedback_*.csv)
  Annex: the full statsmodels output

Every test row states its null hypothesis and the verdict at 5%, including
the tests the model fails. Nothing is filtered.

Reads:  data/processed/monthly.csv, outputs/robustness.csv (optional)
Writes: outputs/report_tables.md

Run from the project folder (after src/model.py and src/robustness.py):
    python src/report_tables.py
"""

import warnings

import numpy as np
import pandas as pd
import statsmodels.api as sm
from statsmodels.stats.outliers_influence import variance_inflation_factor
from statsmodels.stats.stattools import durbin_watson

import model as m

OUT_FILE = m.OUT_DIR / "report_tables.md"
ROBUSTNESS_FILE = m.OUT_DIR / "robustness.csv"
ALPHA = m.SIGNIFICANCE

LABELS = {
    "const": "Constant",
    "dollarization_pct.L1": "Dollarization, level, t-1 (speed of adjustment)",
    "depreciation_1m.L1": "Depreciation, level, t-1",
    "rate_spread.L1": "Rate spread, level, t-1",
    "inflation_yoy_pct.L1": "Inflation y/y, level, t-1",
    "log_brent_lag1.L1": "log Brent (lagged), level, t-1",
    "D.dollarization_pct.L1": "Δ Dollarization, t-1",
    "D.dollarization_pct.L2": "Δ Dollarization, t-2",
    "D.depreciation_1m.L0": "Δ Depreciation, t",
    "D.depreciation_1m.L1": "Δ Depreciation, t-1",
    "D.depreciation_1m.L2": "Δ Depreciation, t-2",
    "D.rate_spread.L0": "Δ Rate spread, t",
    "D.rate_spread.L1": "Δ Rate spread, t-1",
    "D.rate_spread.L2": "Δ Rate spread, t-2",
    "D.inflation_yoy_pct.L0": "Δ Inflation y/y, t",
    "D.inflation_yoy_pct.L1": "Δ Inflation y/y, t-1",
    "D.inflation_yoy_pct.L2": "Δ Inflation y/y, t-2",
    "D.log_brent_lag1.L0": "Δ log Brent (lagged), t",
    "D.log_brent_lag1.L1": "Δ log Brent (lagged), t-1",
    "D.log_brent_lag1.L2": "Δ log Brent (lagged), t-2",
}


# ---------------------------------------------------------------------------
# Small formatting helpers
# ---------------------------------------------------------------------------

def stars(p):
    """Conventional significance stars: *** 1%, ** 5%, * 10%."""
    if p < 0.01:
        return "***"
    if p < 0.05:
        return "**"
    if p < 0.10:
        return "*"
    return ""


def fmt_p(p):
    if pd.isna(p):
        return "n/a"
    return "<0.001" if p < 0.001 else f"{p:.3f}"


def md_table(frame):
    """A DataFrame as a Markdown table (no extra dependency needed)."""
    header = "| " + " | ".join(str(c) for c in frame.columns) + " |"
    rule = "|" + "|".join("---" for _ in frame.columns) + "|"
    rows = ["| " + " | ".join(str(v) for v in row) + " |"
            for row in frame.itertuples(index=False)]
    return "\n".join([header, rule] + rows)


def label(name):
    return LABELS.get(name, name)


# ---------------------------------------------------------------------------
# Re-estimate the main model exactly as src/model.py does
# ---------------------------------------------------------------------------

def estimate():
    table = m.build_model_table(m.read_monthly())
    estimation, holdout = m.split_sample(table)
    full = m.add_regressors(table)
    est = full.loc[estimation.index]
    order, n_specs, _ = m.select_order(est)
    uecm, result = m.fit_uecm(est, order)
    sample = full.loc[estimation.index[0]:holdout.index[-1]]
    forecast = m.holdout_forecast(sample, order, result.params.values,
                                  holdout.index)
    return {
        "estimation": estimation, "holdout": holdout, "est": est,
        "order": order, "n_specs": n_specs, "uecm": uecm, "result": result,
        "forecast": forecast,
    }


def fit_statistics(fit):
    """R², adjusted R², F-test, AIC/BIC, Durbin-Watson for the estimated
    equation (dependent variable: monthly change in dollarization)."""
    y, x, _ = m.design(fit["uecm"])
    ols = sm.OLS(y, x).fit(cov_type="HAC",
                          cov_kwds={"maxlags": m.hac_lags(len(fit["est"]))})
    return {
        "n_obs": int(ols.nobs),
        "n_params": int(x.shape[1]),
        "r2": ols.rsquared,
        "r2_adj": ols.rsquared_adj,
        "f_stat": float(ols.fvalue),
        "f_p": float(ols.f_pvalue),
        "aic": float(fit["result"].aic),     # same AIC as used to pick the lags
        "bic": float(fit["result"].bic),
        "dw": float(durbin_watson(ols.resid)),
        "resid_std": float(np.sqrt(ols.scale)),
    }


def vif_table(uecm, names):
    _, x, _ = m.design(uecm)
    rows = []
    for i in range(1, x.shape[1]):          # column 0 is the constant
        vif = variance_inflation_factor(x[:, 1:], i - 1)
        rows.append({"Regressor": label(names[i]), "VIF": f"{vif:.2f}",
                     "Verdict (VIF < 10)": "ok" if vif < 10 else "high"})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Sections
# ---------------------------------------------------------------------------

def section_sample(fit, stats_):
    est, hold = fit["estimation"], fit["holdout"]
    order = fit["order"]
    lags = ", ".join(f"{n} {o}" for n, o in
                     zip([m.DEPENDENT] + m.REGRESSORS, order))
    rows = pd.DataFrame([
        ("Model", "ARDL in unrestricted error-correction form (UECM), OLS"),
        ("Dependent variable", "Δ dollarization_pct (monthly change, pp)"),
        ("Estimation sample", f"{est.index[0]} to {est.index[-1]} "
                              f"({len(est)} months, {stats_['n_obs']} used after lags)"),
        ("Hold-out sample", f"{hold.index[0]} to {hold.index[-1]} ({len(hold)} months), never used to estimate"),
        ("Lag orders (AIC)", f"{lags}; chosen among {fit['n_specs']} specifications"),
        ("Standard errors", f"HAC (Newey-West, {m.hac_lags(len(est))} lags)"),
        ("Bounds-test case", f"Case {m.BOUNDS_CASE}: unrestricted constant, no trend"),
    ], columns=["Item", "Value"])
    return "## 1. Sample and specification\n\n" + md_table(rows)


def section_unit_roots(fit):
    ur = m.unit_root_table(fit["estimation"])
    rows = pd.DataFrame({
        "Series": ur["series"],
        "ADF p (level)": ur["level_adf_p"].map(fmt_p),
        "KPSS p (level)": ur["level_kpss_p"].map(fmt_p),
        "ZA p (level)": ur["level_za_p"].map(fmt_p),
        "ZA break": ur["level_za_break"],
        "ADF p (Δ)": ur["diff_adf_p"].map(fmt_p),
        "KPSS p (Δ)": ur["diff_kpss_p"].map(fmt_p),
        "Order": ur["order"],
    })
    note = (
        "ADF: H0 unit root. KPSS: H0 stationary (p-values are clipped by the "
        "KPSS table at 0.01 and 0.10). Zivot-Andrews: H0 unit root, allowing "
        "one break in the level. A series is I(0) if ADF rejects and KPSS "
        "does not, I(1) if that holds for the first difference, otherwise "
        "\"unclear\". No series is I(2), which is the condition the bounds "
        "test needs; the mix of I(0), I(1) and unclear series is why the "
        "bounds test is used instead of Johansen or Engle-Granger."
    )
    return "## 2. Unit-root tests (estimation sample)\n\n" + md_table(rows) + "\n\n" + note


def section_regression(fit, stats_):
    r = fit["result"]
    rows = pd.DataFrame({
        "Term": [label(n) for n in r.params.index],
        "Coefficient": [f"{v:.4f}{stars(p)}" for v, p in zip(r.params, r.pvalues)],
        "HAC s.e.": [f"{v:.4f}" for v in r.bse],
        "t": [f"{v:.2f}" for v in r.tvalues],
        "p-value": [fmt_p(p) for p in r.pvalues],
    })
    fit_rows = pd.DataFrame([
        ("Observations", stats_["n_obs"]),
        ("Parameters", stats_["n_params"]),
        ("R²", f"{stats_['r2']:.3f}"),
        ("Adjusted R²", f"{stats_['r2_adj']:.3f}"),
        ("F-test, all slopes = 0 (HAC)", f"F = {stats_['f_stat']:.2f}, p = {fmt_p(stats_['f_p'])}"),
        ("Residual standard error, pp", f"{stats_['resid_std']:.3f}"),
        ("AIC / BIC", f"{stats_['aic']:.1f} / {stats_['bic']:.1f}"),
        ("Durbin-Watson", f"{stats_['dw']:.2f}"),
    ], columns=["Statistic", "Value"])
    note = (
        "Dependent variable: monthly change in dollarization, pp. "
        "*** p<0.01, ** p<0.05, * p<0.10 (HAC standard errors). "
        "R² refers to the monthly *change*, not the level: a regression of "
        "the level on its own lag would give R² close to 1 and say nothing. "
        "Monthly changes are noisy, so a modest R² is normal for this kind of "
        "equation; the F-test shows the regressors are jointly significant."
    )
    return ("## 3. Regression table (short-run equation)\n\n" + md_table(rows)
            + "\n\n" + md_table(fit_rows) + "\n\n" + note)


def section_long_run(fit):
    r = fit["result"]
    rows = []
    for name in m.REGRESSORS:
        key = name
        # statsmodels normalises the cointegrating vector as y - b'x = 0,
        # so the long-run effect of x on y is minus the reported coefficient.
        rows.append({
            "Factor": name,
            "Long-run effect (pp per unit)": f"{-r.ci_params[key]:.3f}{stars(r.ci_pvalues[key])}",
            "s.e. (delta method)": f"{r.ci_bse[key]:.3f}",
            "p-value": fmt_p(r.ci_pvalues[key]),
        })
    rho = r.params[f"{m.DEPENDENT}.L1"]
    note = (
        f"Long-run effect = -θ/ρ, where ρ = {rho:.4f} is the coefficient on "
        f"last month's dollarization level (speed of adjustment: about "
        f"{abs(rho) * 100:.1f}% of a gap from the long-run level closes each "
        f"month, half-life ≈ {np.log(0.5) / np.log(1 + rho):.0f} months). "
        "Because ρ is small, long-run effects are imprecise."
    )
    return "## 4. Long-run coefficients\n\n" + md_table(pd.DataFrame(rows)) + "\n\n" + note


def section_bounds(fit):
    test = fit["uecm"].fit().bounds_test(case=m.BOUNDS_CASE)
    crit = test.critical_values
    rows = pd.DataFrame([
        (f"{100 - lvl:g}%", f"{crit.loc[lvl, 'lower']:.2f}", f"{crit.loc[lvl, 'upper']:.2f}")
        for lvl in crit.index
    ], columns=["Significance", "I(0) bound", "I(1) bound"])
    conclusion = m.bounds_conclusion(test.pvalue["lower"], test.pvalue["upper"])
    note = (
        f"F = {test.statistic:.3f}; p-value against the I(0) bound "
        f"{fmt_p(test.pvalue['lower'])}, against the I(1) bound "
        f"{fmt_p(test.pvalue['upper'])}. H0: no long-run relationship. "
        f"Conclusion at 5%: **{conclusion}**. The statistic is only just "
        "above the 5% upper bound, so the evidence for a long-run "
        "relationship is borderline, not strong."
    )
    return ("## 5. Bounds test for a long-run relationship (Pesaran, Shin & Smith 2001)\n\n"
            + md_table(rows) + "\n\n" + note)


def section_diagnostics(fit):
    d = m.run_diagnostics(fit["uecm"])

    def verdict(p, bad):
        return bad if p < ALPHA else "passed"

    rows = pd.DataFrame([
        ("Breusch-Godfrey (6 lags)", "No serial correlation", fmt_p(d["breusch_godfrey_p"]),
         verdict(d["breusch_godfrey_p"], "serial correlation")),
        ("Breusch-Pagan", "Constant error variance", fmt_p(d["breusch_pagan_p"]),
         verdict(d["breusch_pagan_p"], "heteroskedasticity → HAC s.e. used")),
        ("Jarque-Bera", "Normal residuals", fmt_p(d["jarque_bera_p"]),
         verdict(d["jarque_bera_p"], "non-normal (crisis months)")),
        ("CUSUM (OLS residuals)", "Stable coefficients", fmt_p(d["cusum_p"]),
         verdict(d["cusum_p"], "unstable")),
        ("Chow, break at 2020-03", "No break", fmt_p(d["chow_2020_03_p"]),
         verdict(d["chow_2020_03_p"], "break")),
        ("Chow, break at 2022-03", "No break", fmt_p(d["chow_2022_03_p"]),
         verdict(d["chow_2022_03_p"], "break")),
        ("Max VIF", "—", f"{d['max_vif']:.2f}",
         "passed (< 10)" if d["max_vif"] < 10 else "multicollinearity"),
    ], columns=["Test", "H0", "p-value / value", "Verdict at 5%"])
    vifs = vif_table(fit["uecm"], list(fit["result"].params.index))
    note = (
        "Failures are reported, not hidden. Heteroskedasticity does not bias "
        "the coefficients but makes ordinary standard errors wrong; all "
        "p-values in section 3 use HAC standard errors, which are valid under "
        "heteroskedasticity and autocorrelation. Non-normal residuals come "
        "from a few large crisis months; with ~100 observations inference "
        "relies on large-sample approximations. The Chow tests find breaks at "
        "2020-03 and 2022-03 although CUSUM does not; robustness variant L3 "
        "adds step dummies for both dates (section 8)."
    )
    return ("## 6. Residual diagnostics\n\n" + md_table(rows) + "\n\n"
            + "Variance inflation factors, every regressor:\n\n" + md_table(vifs)
            + "\n\n" + note)


def section_holdout(fit):
    acc = m.forecast_accuracy(fit["forecast"])
    rows = pd.DataFrame([
        ("RMSE, pp", f"{acc['rmse_model']:.3f}", f"{acc['rmse_benchmark']:.3f}", f"{acc['rmse_ratio']:.3f}"),
        ("MAE, pp", f"{acc['mae_model']:.3f}", f"{acc['mae_benchmark']:.3f}", f"{acc['mae_ratio']:.3f}"),
    ], columns=["Measure", "Model", "Random walk", "Ratio (model / RW)"])
    note = (
        f"{acc['n_holdout']} hold-out months, one-month-ahead nowcasts with "
        "coefficients from the estimation sample only. A ratio above 1 means "
        f"the random walk is more accurate. Winner: **{acc['winner']}**. The "
        "model explains *why* the indicator moved, but does not forecast the "
        "next month better than \"no change\"; this is the usual result for "
        "persistent monthly series and is reported on the website."
    )
    return "## 7. Out-of-sample accuracy (hold-out)\n\n" + md_table(rows) + "\n\n" + note


def section_robustness():
    if not ROBUSTNESS_FILE.exists():
        return ("## 8. Robustness checks\n\n`outputs/robustness.csv` not found. "
                "Run `python src/robustness.py` first.")
    rob = pd.read_csv(ROBUSTNESS_FILE)
    rows = pd.DataFrame({
        "ID": rob["id"],
        "Variant": rob["variant"],
        "N": rob["n_obs"],
        "ECT (ρ)": [f"{c:.3f}{stars(p)}" for c, p in zip(rob["ect_coef"], rob["ect_p"])],
        "Depreciation, short run": [f"{c:.3f}{stars(p)}" for c, p in
                                     zip(rob["depreciation_sr_coef"], rob["depreciation_sr_p"])],
        "Bounds test": rob["bounds_conclusion"],
        "RMSE ratio": rob["rmse_ratio"].map(lambda v: f"{v:.3f}"),
    })
    extra = []
    for col, name in [("float_regime", "Float-regime dummy (R1)"),
                      ("usd_kzt_vol", "Exchange-rate volatility (L1)"),
                      ("dep_x_level", "Depreciation × dollarization level (L2)"),
                      ("break_2020", "Step dummy 2020-03 (L3)"),
                      ("break_2022", "Step dummy 2022-03 (L3)")]:
        if f"{col}_coef" in rob:
            r = rob.dropna(subset=[f"{col}_coef"]).iloc[0]
            extra.append((name, f"{r[f'{col}_coef']:.3f}{stars(r[f'{col}_p'])}",
                          fmt_p(r[f"{col}_p"])))
    extra = pd.DataFrame(extra, columns=["Added term", "Coefficient", "p-value"])
    note = (
        f"{len(rob)} variants, {int(rob['n_specs_searched'].sum())} "
        "specifications searched in total. Each variant chooses its own lags "
        "by AIC on the estimation months and is evaluated on the same "
        "hold-out months. R2 (logit) is a short-run coefficient on the logit "
        "scale, not in pp. R3 (constant exchange rate) removes revaluation; "
        "the depreciation effect disappears there, so the main model's "
        "depreciation effect is largely mechanical revaluation."
    )
    return ("## 8. Robustness checks\n\n" + md_table(rows) + "\n\n"
            + md_table(extra) + "\n\n" + note)


def section_feedback():
    """Reverse direction: does dollarization move the exchange rate? (VAR)"""
    granger_file = m.OUT_DIR / "feedback_granger.csv"
    irf_file = m.OUT_DIR / "feedback_irf.csv"
    if not granger_file.exists() or not irf_file.exists():
        return ("## 9. Feedback: does dollarization move the tenge? (VAR)\n\n"
                "Not found. Run `python src/feedback.py` first.")
    var = pd.read_csv(granger_file)
    rows = pd.DataFrame({
        "ID": var["id"],
        "Variant": var["variant"],
        "N": var["n_obs"],
        "Lags (AIC)": var["lags"],
        "Dollarization → FX, p": var["dollar_to_fx_p"].map(fmt_p),
        "FX → dollarization, p": var["fx_to_dollar_p"].map(fmt_p),
        "FEVD of FX from dollarization, 12m": var["fevd_fx_from_dollar_12m"].map(lambda v: f"{100 * v:.1f}%"),
        "Same-month corr.": var["same_month_corr"].map(lambda v: f"{v:.2f}"),
        "Stable": var["stable"],
        "Portmanteau p": var["whiteness_p"].map(fmt_p),
        "Normality p": var["normality_p"].map(fmt_p),
    })
    irf = pd.read_csv(irf_file).head(7)
    irf_rows = pd.DataFrame({
        "Month": irf["month"],
        "FX response to dollarization shock, %": [
            f"{v:+.3f} [{lo:+.3f}, {hi:+.3f}]"
            for v, lo, hi in zip(irf["fx_response"], irf["fx_lower"], irf["fx_upper"])],
        "Dollarization response to FX shock, pp": [
            f"{v:+.3f} [{lo:+.3f}, {hi:+.3f}]"
            for v, lo, hi in zip(irf["dollar_response"], irf["dollar_lower"], irf["dollar_upper"])],
    })
    note = (
        "Four-variable VAR (change in log Brent, change in the rate spread, "
        "depreciation, change in dollarization), 2016 onwards, lags by AIC "
        "(1 to 6). Granger H0: past values of the first variable do not help "
        "predict the second. Impulse responses are Cholesky-orthogonalised in "
        "that order, one-standard-deviation shocks, 95% Monte Carlo bands in "
        "brackets. V1 is the main variant: dollarization is an end-of-month "
        "stock, so depreciation is also measured end of month. V3 uses the "
        "monthly average rate: a late-month fall of the tenge then reaches "
        "dollarization one month before it reaches average-rate depreciation, "
        "which makes dollarization appear to Granger-cause the exchange rate. "
        "The effect disappears with consistent timing (V1) and with the "
        "constant-rate measure (V2, V4 at 5%). Added at the instructor's "
        "suggestion, after the pre-registration (docs/deviations.md, entry 5)."
    )
    return ("## 9. Feedback: does dollarization move the tenge? (VAR)\n\n"
            + md_table(rows) + "\n\nImpulse responses, main variant V1 "
            "(first 6 months; later months are close to zero):\n\n"
            + md_table(irf_rows) + "\n\n" + note)


def section_annex(fit):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        text = str(fit["result"].summary())
    return ("## Annex. Full statsmodels output\n\n```\n" + text + "\n```")


def build_report():
    warnings.simplefilter("ignore")
    fit = estimate()
    stats_ = fit_statistics(fit)
    parts = [
        "# Model evidence: tables for the technical note",
        "Generated by `python src/report_tables.py` from the cached data. "
        "Same estimation code as `src/model.py`.",
        section_sample(fit, stats_),
        section_unit_roots(fit),
        section_regression(fit, stats_),
        section_long_run(fit),
        section_bounds(fit),
        section_diagnostics(fit),
        section_holdout(fit),
        section_robustness(),
        section_feedback(),
        section_annex(fit),
    ]
    return "\n\n".join(parts) + "\n"


def main():
    report = build_report()
    m.OUT_DIR.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(report, encoding="utf-8")
    print(f"Report tables -> {OUT_FILE}")


if __name__ == "__main__":
    main()
