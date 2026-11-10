# %%
import itertools
import numpy as np
import pandas as pd
import statsmodels.api as sm
from pathlib import Path

d = pd.read_csv(Path("data/processed") / "monthly_clean.csv",
                parse_dates=["period"], index_col="period").loc["2016-01-01":]

data = pd.DataFrame({
    "dollarization": d["dollarization_pct"],
    "depreciation_1m": d["usd_kzt_avg"].pct_change() * 100,
    "rate_spread": d["rate_spread"],
    "inflation_yoy": d["inflation_yoy_pct"],
    "log_brent_lag1": np.log(d["brent_usd"]).shift(1),
})

EST_END = "2024-06-01"   # hold-out (last 20%) is not used for lag selection
MAX_LAG = 3
regressors = ["depreciation_1m", "rate_spread", "inflation_yoy", "log_brent_lag1"]

# Build all lags up to MAX_LAG
lagged = {"y": data["dollarization"]}
for k in range(1, MAX_LAG + 1):
    lagged[f"y_L{k}"] = data["dollarization"].shift(k)
for r in regressors:
    for k in range(0, MAX_LAG + 1):
        lagged[f"{r}_L{k}"] = data[r].shift(k)

# Same sample for every specification: rows where the largest model has no missing values
X_all = pd.DataFrame(lagged).loc[:EST_END].dropna()
print("Common sample:", X_all.index[0].strftime("%Y-%m"), "to",
      X_all.index[-1].strftime("%Y-%m"), "| n =", len(X_all))

results = []
for p in range(1, MAX_LAG + 1):
    for qs in itertools.product(range(0, MAX_LAG + 1), repeat=len(regressors)):
        cols = [f"y_L{k}" for k in range(1, p + 1)]
        for r, q in zip(regressors, qs):
            cols += [f"{r}_L{k}" for k in range(0, q + 1)]
        fit = sm.OLS(X_all["y"], sm.add_constant(X_all[cols])).fit()
        results.append({"p_dollarization": p,
                        **{f"q_{r}": q for r, q in zip(regressors, qs)},
                        "n_params": len(cols) + 1, "AIC": fit.aic, "BIC": fit.bic})

grid = pd.DataFrame(results)
grid.to_csv(Path("outputs") / "lag_selection_grid.csv", index=False)
print("Specifications:", len(grid))

print("\nTop 10 by AIC:")
print(grid.sort_values("AIC").head(10).round(2).to_string(index=False))
print("\nTop 10 by BIC:")
print(grid.sort_values("BIC").head(10).round(2).to_string(index=False))

best_aic = grid.loc[grid["AIC"].idxmin()]
best_bic = grid.loc[grid["BIC"].idxmin()]
print("\nBest by AIC:", best_aic.iloc[:5].astype(int).to_dict())
print("Best by BIC:", best_bic.iloc[:5].astype(int).to_dict())
print("BIC of AIC-best minus best BIC:", round(best_aic["BIC"] - best_bic["BIC"], 2))
print("AIC of BIC-best minus best AIC:", round(best_bic["AIC"] - best_aic["AIC"], 2))