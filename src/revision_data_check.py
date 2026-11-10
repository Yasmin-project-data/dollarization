# %%
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path
from statsmodels.graphics.tsaplots import plot_acf, plot_pacf
from statsmodels.tsa.stattools import acf, pacf

d = pd.read_csv(Path("data/processed") / "monthly_clean.csv",
                parse_dates=["period"], index_col="period").loc["2016-01-01":]

# Stationary versions: differences for I(1) series, depreciation as is (I(0))
series = {
    "d_dollarization": d["dollarization_pct"].diff(),
    "depreciation_1m": d["usd_kzt_avg"].pct_change() * 100,
    "d_rate_spread": d["rate_spread"].diff(),
    "d_inflation_yoy": d["inflation_yoy_pct"].diff(),
    "d_log_brent": np.log(d["brent_usd"]).diff(),
}
LAGS = 24

fig, axes = plt.subplots(len(series), 2, figsize=(12, 14))
for i, (name, s) in enumerate(series.items()):
    x = s.dropna()
    plot_acf(x, lags=LAGS, ax=axes[i, 0], title=f"ACF: {name}")
    plot_pacf(x, lags=LAGS, ax=axes[i, 1], title=f"PACF: {name}", method="ywm")
plt.tight_layout()
plt.show()

rows = []
for name, s in series.items():
    x = s.dropna()
    band = 1.96 / np.sqrt(len(x))
    a = acf(x, nlags=LAGS)[1:]
    p = pacf(x, nlags=LAGS, method="ywm")[1:]
    rows.append({"series": name, "n": len(x), "band": round(band, 3),
                 "significant ACF lags": [k + 1 for k, v in enumerate(a) if abs(v) > band],
                 "significant PACF lags": [k + 1 for k, v in enumerate(p) if abs(v) > band]})

out = pd.DataFrame(rows)
print(out.to_string(index=False))
out.to_csv(Path("outputs") / "acf_pacf_lags.csv", index=False)