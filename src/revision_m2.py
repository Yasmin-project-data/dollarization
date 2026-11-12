# %%
import itertools
import numpy as np
import pandas as pd
import statsmodels.api as sm
import matplotlib.pyplot as plt
from pathlib import Path
from scipy import stats
from statsmodels.stats.diagnostic import (acorr_breusch_godfrey, het_breuschpagan,
                                          acorr_ljungbox, breaks_cusumolsresid)
from statsmodels.stats.stattools import jarque_bera

proc, out = Path("data/processed"), Path("outputs")
out.mkdir(exist_ok=True)
clean = pd.read_csv(proc / "monthly_clean.csv", parse_dates=["period"], index_col="period")
raw = pd.read_csv(proc / "monthly.csv", parse_dates=["period"], index_col="period")

START, EST_END, HOLD_START, MAX_LAG = "2016-01-01", "2024-06-01", "2024-07-01", 3

# ---------- 1. Clean the end-of-month rate with the same rule (3 x IQR on log change) ----------
eom = raw["usd_kzt_eom"].copy()
ch = np.log(eom.loc[START:]).diff()
q1, q3 = ch.quantile([0.25, 0.75])
iqr = q3 - q1
bad = ch[(ch < q1 - 3 * iqr) | (ch > q3 + 3 * iqr)].index
eom_clean = eom.copy()
eom_clean.loc[bad] = np.nan
eom_clean = eom_clean.interpolate(limit_area="inside")
print("usd_kzt_eom outliers replaced:", [m.strftime("%Y-%m") for m in bad])
clean["usd_kzt_eom"] = eom_clean
clean.to_csv(proc / "monthly_clean.csv")
log_path = out / "outlier_log.csv"
if log_path.exists():
    log = pd.read_csv(log_path)
    log = log[log["series"] != "usd_kzt_eom"]
    new = pd.DataFrame({"series": "usd_kzt_eom", "month": [m.strftime("%Y-%m") for m in bad],
                        "old_value": [round(eom[m], 3) for m in bad],
                        "change": [round(ch[m], 3) for m in bad]})
    pd.concat([log, new]).to_csv(log_path, index=False)

# ---------- 2. Variables ----------
y = clean["dollarization_pct"].loc[START:]
s_prev = y.shift(1) / 100
data = pd.DataFrame({
    "dep_eom_scaled": (eom_clean.pct_change() * 100).loc[START:] * s_prev * (1 - s_prev),
    "rate_spread": clean["rate_spread"].loc[START:],
    "inflation_yoy": clean["inflation_yoy_pct"].loc[START:],
    "log_brent_lag1": np.log(clean["brent_usd"]).shift(1).loc[START:],
})
regs = list(data.columns)


def ecm_frame(p, qs):
    """ARDL(p, q1..q4) rewritten in error-correction form (same fit as the levels ARDL)."""
    f = pd.DataFrame({"dy": y.diff(), "y_L1": y.shift(1)})
    for i in range(1, p):
        f[f"dy_L{i}"] = y.diff().shift(i)
    for r, q in zip(regs, qs):
        x = data[r]
        if q == 0:
            f[r] = x
        else:
            f[f"{r}_L1"] = x.shift(1)
            for i in range(q):
                f[f"d_{r}_L{i}"] = x.diff().shift(i)
    return f


def level_terms(qs):
    return ["y_L1"] + [r if q == 0 else f"{r}_L1" for r, q in zip(regs, qs)]


# ---------- 3. Lag selection: AIC and BIC on one common sample ----------
common = ecm_frame(MAX_LAG, (MAX_LAG,) * 4).loc[:EST_END].dropna().index
grid = []
for p in range(1, MAX_LAG + 1):
    for qs in itertools.product(range(MAX_LAG + 1), repeat=4):
        f = ecm_frame(p, qs).loc[common]
        fit = sm.OLS(f["dy"], sm.add_constant(f.drop(columns="dy"))).fit()
        grid.append({"p": p, **{f"q_{r}": q for r, q in zip(regs, qs)}, "AIC": fit.aic, "BIC": fit.bic})
grid = pd.DataFrame(grid)
grid.to_csv(out / "m2_lag_grid.csv", index=False)
best_aic = grid.loc[grid["AIC"].idxmin()]
best_bic = grid.loc[grid["BIC"].idxmin()]
chosen = best_bic if best_bic["AIC"] - best_aic["AIC"] < 2 else best_aic
p = int(chosen["p"])
qs = tuple(int(chosen[f"q_{r}"]) for r in regs)
print(f"\nCommon sample {common[0]:%Y-%m} to {common[-1]:%Y-%m}, n = {len(common)}, specs = {len(grid)}")
print("Best AIC:", best_aic.round(2).to_dict())
print("Best BIC:", best_bic.round(2).to_dict())
print(f"Chosen: ARDL({p},{','.join(map(str, qs))})  (BIC choice kept if within 2 AIC points)")

# ---------- 4. Final estimation and diagnostics ----------
f_all = ecm_frame(p, qs)
f = f_all.loc[:EST_END].dropna()
X = sm.add_constant(f.drop(columns="dy"))
ols = sm.OLS(f["dy"], X).fit()
hac = sm.OLS(f["dy"], X).fit(cov_type="HAC", cov_kwds={"maxlags": 4})
resid = ols.resid
diag = pd.DataFrame([
    ["Breusch-Godfrey (4)", acorr_breusch_godfrey(ols, nlags=4, result_object=False)[1]],
    ["Ljung-Box (12)", acorr_ljungbox(resid, lags=[12], return_df=True)["lb_pvalue"].iloc[0]],
    ["Breusch-Pagan", het_breuschpagan(resid, X)[1]],
    ["Jarque-Bera", jarque_bera(resid)[1]],
    ["CUSUM", breaks_cusumolsresid(resid, ddof=X.shape[1])[1]],
], columns=["test", "p-value"])
diag["problem at 5%"] = diag["p-value"] < 0.05
print(f"\nEstimation sample {f.index[0]:%Y-%m} to {f.index[-1]:%Y-%m}, n = {len(f)}")
print(diag.round(3).to_string(index=False))
print("\nCoefficients:")
print(pd.DataFrame({"coef": ols.params, "p (OLS)": ols.pvalues, "p (HAC)": hac.pvalues}).round(4).to_string())
print("R-squared:", round(ols.rsquared, 3))

lv = level_terms(qs)
F = float(np.squeeze(ols.f_test(" = 0, ".join(lv) + " = 0").fvalue))
t_a = ols.tvalues["y_L1"]
print(f"\nBounds test (PSS case III, k=4): F = {F:.2f} [5%: 2.86/4.01, 1%: 3.74/5.06]; "
      f"t = {t_a:.2f} [5%: -2.86/-3.99, 1%: -3.43/-4.60]")
alpha = ols.params["y_L1"]
print("alpha:", round(alpha, 4), "| half-life, months:",
      round(np.log(0.5) / np.log(1 + alpha), 1) if -1 < alpha < 0 else "n/a")

# ---------- 5. Hold-out: expanding window, one month ahead ----------
actual = raw["dollarization_pct"]
hold = f_all.loc[HOLD_START:].dropna().index
rows = []
for t in hold:
    train = f_all.loc[:t - pd.DateOffset(months=1)].dropna()
    fit = sm.OLS(train["dy"], sm.add_constant(train.drop(columns="dy"))).fit()
    x_t = sm.add_constant(f_all.drop(columns="dy"), has_constant="add").loc[[t]]
    rows.append({"month": t, "actual": actual.loc[t], "random_walk": actual.loc[t - pd.DateOffset(months=1)],
                 "model": y.loc[t - pd.DateOffset(months=1)] + float(fit.predict(x_t).iloc[0])})
fc = pd.DataFrame(rows).set_index("month")
e_m, e_rw = fc["actual"] - fc["model"], fc["actual"] - fc["random_walk"]
dlt = e_m ** 2 - e_rw ** 2
n = len(dlt)
dm = dlt.mean() / np.sqrt(dlt.var(ddof=1) / n) * np.sqrt((n - 1) / n)
dm_p = 2 * stats.t.sf(abs(dm), df=n - 1)
acc = pd.DataFrame({
    "forecast": ["random_walk", "model"],
    "RMSE": [np.sqrt((e_rw ** 2).mean()), np.sqrt((e_m ** 2).mean())],
    "MAE": [e_rw.abs().mean(), e_m.abs().mean()],
})
acc["ratio vs RW (RMSE)"] = acc["RMSE"] / acc["RMSE"].iloc[0]
acc["ratio vs RW (MAE)"] = acc["MAE"] / acc["MAE"].iloc[0]
print(f"\nHold-out {hold[0]:%Y-%m} to {hold[-1]:%Y-%m}, months = {n}")
print(acc.round(3).to_string(index=False))
print(f"Diebold-Mariano: stat = {dm:.2f}, p = {dm_p:.3f} | model better in "
      f"{(e_m.abs() < e_rw.abs()).sum()} of {n} months")

fc.to_csv(out / "m2_holdout_forecasts.csv")
acc.to_csv(out / "m2_forecast_accuracy.csv", index=False)

fig, ax = plt.subplots(figsize=(11, 5))
ax.plot(fc.index, fc["actual"], color="black", lw=2.5, label="actual")
ax.plot(fc.index, fc["random_walk"], color="grey", ls=":", label="random walk")
ax.plot(fc.index, fc["model"], color="tab:orange", lw=1.8, label=f"model ARDL({p},{','.join(map(str, qs))})")
ax.set_title("Hold-out nowcasts of dollarization, %")
ax.legend()
plt.tight_layout()
plt.show()