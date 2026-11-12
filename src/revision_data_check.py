# %%
import numpy as np
import pandas as pd
import statsmodels.api as sm
import matplotlib.pyplot as plt
from pathlib import Path
from scipy import stats

proc = Path("data/processed")
clean = pd.read_csv(proc / "monthly_clean.csv", parse_dates=["period"], index_col="period")
raw = pd.read_csv(proc / "monthly.csv", parse_dates=["period"], index_col="period")

HOLD_START = "2024-07-01"

# Deposits are end-of-month stocks, so revaluation depends on the END-OF-MONTH exchange rate
s_prev = raw["dollarization_pct"].shift(1) / 100          # FX share last month
fx_ratio = raw["usd_kzt_eom"] / raw["usd_kzt_eom"].shift(1)  # tenge move this month
s_mech = s_prev * fx_ratio / (1 - s_prev + s_prev * fx_ratio)
reval = (s_mech - s_prev) * 100   # pure revaluation effect, percentage points

df = pd.DataFrame({
    "dollarization": clean["dollarization_pct"],
    "dollarization_raw": raw["dollarization_pct"],
    "dep_avg": clean["usd_kzt_avg"].pct_change() * 100,
    "dep_eom": raw["usd_kzt_eom"].pct_change() * 100,
    "rate_spread": clean["rate_spread"],
    "inflation_yoy": clean["inflation_yoy_pct"],
    "log_brent_lag1": np.log(clean["brent_usd"]).shift(1),
    "reval": reval,
}).loc["2016-01-01":]
df["dep_eom_scaled"] = df["dep_eom"] * s_prev * (1 - s_prev)
other = ["rate_spread", "inflation_yoy", "log_brent_lag1"]


def make_eq(y_col, level_col, dep_col):
    """Error-correction equation: change in y on lagged level, depreciation term and other drivers."""
    eq = pd.DataFrame({"dy": y_col.diff() if dep_col != "behaviour" else y_col,
                       "level_L1": level_col.shift(1)})
    if dep_col not in (None, "behaviour"):
        eq[dep_col] = df[dep_col]
    for r in other:
        eq[r] = df[r]
    return eq.dropna()


# Candidate models (all re-estimated every month on data before the forecast month)
models = {
    "M0 current (avg rate)": make_eq(df["dollarization"], df["dollarization"], "dep_avg"),
    "M1 end-of-month rate": make_eq(df["dollarization"], df["dollarization"], "dep_eom"),
    "M2 eom rate x share(1-share)": make_eq(df["dollarization"], df["dollarization"], "dep_eom_scaled"),
    # M4: revaluation computed exactly, regression explains only the behavioural change
    "M4 exact revaluation + behaviour": make_eq(df["dollarization_raw"].diff() - df["reval"],
                                                df["dollarization_raw"], "behaviour"),
}

actual = df["dollarization_raw"]
hold = actual.loc[HOLD_START:].dropna().index
fc = pd.DataFrame(index=hold)
fc["actual"] = actual.loc[hold]
fc["random_walk"] = actual.shift(1).loc[hold]
fc["M3 revaluation only"] = actual.shift(1).loc[hold] + df["reval"].loc[hold]

for name, eq in models.items():
    preds = []
    for t in hold:
        train = eq.loc[:t - pd.DateOffset(months=1)]
        fit = sm.OLS(train["dy"], sm.add_constant(train.drop(columns="dy"))).fit()
        x_t = sm.add_constant(eq.drop(columns="dy"), has_constant="add").loc[[t]]
        change = float(fit.predict(x_t).iloc[0])
        if name.startswith("M4"):
            change += df.loc[t, "reval"]
        preds.append(actual.shift(1).loc[t] + change)
    fc[name] = preds


def dm_test(e_model, e_bench):
    dlt = e_model ** 2 - e_bench ** 2
    n = len(dlt)
    dm = dlt.mean() / np.sqrt(dlt.var(ddof=1) / n) * np.sqrt((n - 1) / n)
    return dm, 2 * stats.t.sf(abs(dm), df=n - 1)


e_rw = fc["actual"] - fc["random_walk"]
rmse_rw = np.sqrt((e_rw ** 2).mean())
rows = []
for col in fc.columns.drop("actual"):
    e = fc["actual"] - fc[col]
    rmse = np.sqrt((e ** 2).mean())
    dm, p = dm_test(e, e_rw) if col != "random_walk" else (np.nan, np.nan)
    rows.append({"forecast": col, "RMSE": rmse, "MAE": e.abs().mean(),
                 "RMSE ratio vs RW": rmse / rmse_rw, "DM stat": dm, "DM p": p})
summary = pd.DataFrame(rows).sort_values("RMSE")
print("Hold-out", hold[0].strftime("%Y-%m"), "to", hold[-1].strftime("%Y-%m"), "| months =", len(hold))
print(summary.round(3).to_string(index=False))

# Coefficient on the scaled depreciation term (pure revaluation predicts about 1)
eq2 = models["M2 eom rate x share(1-share)"].loc[:"2024-06-01"]
fit2 = sm.OLS(eq2["dy"], sm.add_constant(eq2.drop(columns="dy"))).fit()
print("\nM2 coefficient on dep_eom_scaled:", round(fit2.params["dep_eom_scaled"], 3),
      "(p =", round(fit2.pvalues["dep_eom_scaled"], 4), ") - pure revaluation would give 1.0")

Path("outputs").mkdir(exist_ok=True)
fc.to_csv(Path("outputs") / "forecast_candidates.csv")
summary.to_csv(Path("outputs") / "forecast_candidates_accuracy.csv", index=False)

fig, ax = plt.subplots(figsize=(11, 5))
ax.plot(fc.index, fc["actual"], color="black", lw=2.5, label="actual")
ax.plot(fc.index, fc["random_walk"], color="grey", ls=":", label="random walk")
best = summary["forecast"].iloc[0] if summary["forecast"].iloc[0] != "random_walk" else summary["forecast"].iloc[1]
ax.plot(fc.index, fc["M0 current (avg rate)"], alpha=0.6, label="M0 current")
ax.plot(fc.index, fc[best], lw=1.8, label=f"best: {best}")
ax.set_title("Hold-out nowcasts of dollarization, %")
ax.legend()
plt.tight_layout()
plt.show()