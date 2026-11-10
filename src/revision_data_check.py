# %%
import numpy as np
import pandas as pd
import statsmodels.api as sm
import matplotlib.pyplot as plt
from pathlib import Path
from statsmodels.stats.diagnostic import (acorr_breusch_godfrey, het_breuschpagan,
                                          acorr_ljungbox, breaks_cusumolsresid)
from statsmodels.stats.stattools import jarque_bera
from statsmodels.graphics.tsaplots import plot_acf

d = pd.read_csv(Path("data/processed") / "monthly_clean.csv",
                parse_dates=["period"], index_col="period").loc["2016-01-01":]

EST_END = "2024-06-01"
regressors = ["depreciation_1m", "rate_spread", "inflation_yoy", "log_brent_lag1"]
data = pd.DataFrame({
    "dollarization": d["dollarization_pct"],
    "depreciation_1m": d["usd_kzt_avg"].pct_change() * 100,
    "rate_spread": d["rate_spread"],
    "inflation_yoy": d["inflation_yoy_pct"],
    "log_brent_lag1": np.log(d["brent_usd"]).shift(1),
})

# ARDL(1,0,0,0,0) in error-correction form (exact rewrite, same fit):
# d_dollarization_t = c + alpha * dollarization_{t-1} + sum(theta_j * x_j,t) + e_t
eq = pd.DataFrame({"d_dollarization": data["dollarization"].diff(),
                   "dollarization_L1": data["dollarization"].shift(1)})
for r in regressors:
    eq[r] = data[r]
eq = eq.loc[:EST_END].dropna()
y = eq["d_dollarization"]
X = sm.add_constant(eq.drop(columns="d_dollarization"))
print("Estimation sample:", eq.index[0].strftime("%Y-%m"), "to",
      eq.index[-1].strftime("%Y-%m"), "| n =", len(eq))

ols = sm.OLS(y, X).fit()
hac = sm.OLS(y, X).fit(cov_type="HAC", cov_kwds={"maxlags": 4})

# 1. Residual diagnostics
resid = ols.resid
bg = acorr_breusch_godfrey(ols, nlags=4, result_object=False)
bp = het_breuschpagan(resid, X)
jb = jarque_bera(resid)
lb = acorr_ljungbox(resid, lags=[12], return_df=True)
cusum = breaks_cusumolsresid(resid, ddof=X.shape[1])
diag = pd.DataFrame([
    ["Breusch-Godfrey (4 lags)", "no autocorrelation", bg[1]],
    ["Ljung-Box (12 lags)", "no autocorrelation", lb["lb_pvalue"].iloc[0]],
    ["Breusch-Pagan", "homoskedastic", bp[1]],
    ["Jarque-Bera", "normal residuals", jb[1]],
    ["CUSUM (OLS residuals)", "stable coefficients", cusum[1]],
], columns=["test", "H0", "p-value"])
diag["H0 rejected at 5%"] = diag["p-value"] < 0.05
print("\nResidual diagnostics:")
print(diag.round(3).to_string(index=False))

# 2. Standard errors: plain OLS vs HAC (coefficients are identical)
coef = pd.DataFrame({"coef": ols.params, "p (OLS)": ols.pvalues, "p (HAC)": hac.pvalues})
print("\nCoefficients:")
print(coef.round(4).to_string())
print("R-squared:", round(ols.rsquared, 3), "| Durbin-Watson:",
      round(sm.stats.stattools.durbin_watson(resid), 2))

# 3. Bounds test, Pesaran-Shin-Smith (2001) case III, k = 4
levels = ["dollarization_L1"] + regressors
F = float(np.squeeze(ols.f_test(" = 0, ".join(levels) + " = 0").fvalue))
t_alpha = ols.tvalues["dollarization_L1"]
f_crit = {"10%": (2.45, 3.52), "5%": (2.86, 4.01), "1%": (3.74, 5.06)}
t_crit = {"10%": (-2.57, -3.66), "5%": (-2.86, -3.99), "1%": (-3.43, -4.60)}
print(f"\nBounds F = {F:.2f} | t(alpha) = {t_alpha:.2f}")
for lvl in f_crit:
    f0, f1 = f_crit[lvl]
    t0, t1 = t_crit[lvl]
    f_res = "cointegration" if F > f1 else ("no cointegration" if F < f0 else "inconclusive")
    t_res = "cointegration" if t_alpha < t1 else ("no cointegration" if t_alpha > t0 else "inconclusive")
    print(f"  {lvl}: F bounds {f0}/{f1} -> {f_res}; t bounds {t0}/{t1} -> {t_res}")

# 4. Long-run effects and speed of adjustment (delta method)
alpha = ols.params["dollarization_L1"]
cov = ols.cov_params()
rows = []
for r in regressors:
    th = ols.params[r]
    lr = -th / alpha
    g = np.zeros(len(ols.params))
    g[list(ols.params.index).index(r)] = -1 / alpha
    g[list(ols.params.index).index("dollarization_L1")] = th / alpha ** 2
    se = float(np.sqrt(g @ cov.values @ g))
    rows.append({"variable": r, "long-run effect": lr, "se": se, "t": lr / se})
print("\nSpeed of adjustment alpha:", round(alpha, 4),
      "| half-life, months:", round(np.log(0.5) / np.log(1 + alpha), 1) if -1 < alpha < 0 else "n/a")
print("Long-run effects:")
print(pd.DataFrame(rows).round(3).to_string(index=False))

Path("outputs").mkdir(exist_ok=True)
diag.to_csv(Path("outputs") / "revision_diagnostics.csv", index=False)
coef.to_csv(Path("outputs") / "revision_coefficients.csv")

# 5. Residual plots
fig, axes = plt.subplots(2, 1, figsize=(10, 7))
axes[0].plot(resid.index, resid)
axes[0].axhline(0, color="grey", lw=0.8)
axes[0].set_title("Residuals over time")
plot_acf(resid, lags=24, ax=axes[1], title="ACF of residuals")
plt.tight_layout()
plt.show()