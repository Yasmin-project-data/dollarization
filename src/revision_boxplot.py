# %%
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path

proc = Path("data/processed")
START = "2016-01-01"
before = pd.read_csv(proc / "monthly.csv", parse_dates=["period"], index_col="period").loc[START:]
after = pd.read_csv(proc / "monthly_clean.csv", parse_dates=["period"], index_col="period").loc[START:]


def monthly_changes(d):
    """Monthly changes of the model variables (FX rates and Brent in % log change)."""
    return pd.DataFrame({
        "dollarization": d["dollarization_pct"].diff(),
        "dollarization_const": d["dollarization_const_pct"].diff(),
        "fx_avg_%": np.log(d["usd_kzt_avg"]).diff() * 100,
        "fx_eom_%": np.log(d["usd_kzt_eom"]).diff() * 100,
        "rate_spread": d["rate_spread"].diff(),
        "inflation_yoy": d["inflation_yoy_pct"].diff(),
        "brent_%": np.log(d["brent_usd"]).diff() * 100,
    })


ch_before, ch_after = monthly_changes(before), monthly_changes(after)
cols = list(ch_before.columns)

# Whiskers at 3 x IQR = the cleaning rule; circles beyond them would be outliers by that rule
fig, axes = plt.subplots(2, len(cols), figsize=(16, 7))
for j, c in enumerate(cols):
    for i, (label, ch) in enumerate([("before", ch_before), ("after", ch_after)]):
        ax = axes[i, j]
        ax.boxplot(ch[c].dropna(), whis=3)
        ax.set_title(f"{c}\n{label}", fontsize=9)
        ax.set_xticks([])
    lo = min(ch_before[c].min(), ch_after[c].min())
    hi = max(ch_before[c].max(), ch_after[c].max())
    pad = (hi - lo) * 0.05
    axes[0, j].set_ylim(lo - pad, hi + pad)
    axes[1, j].set_ylim(lo - pad, hi + pad)
fig.suptitle("Monthly changes before and after cleaning (whiskers = 3 x IQR, same scale in each column)")
plt.tight_layout()
plt.show()


def count_outliers(x, k):
    x = x.dropna()
    q1, q3 = x.quantile([0.25, 0.75])
    iqr = q3 - q1
    return int(((x < q1 - k * iqr) | (x > q3 + k * iqr)).sum())


table = pd.DataFrame({
    "before, 1.5xIQR": [count_outliers(ch_before[c], 1.5) for c in cols],
    "after, 1.5xIQR": [count_outliers(ch_after[c], 1.5) for c in cols],
    "before, 3xIQR": [count_outliers(ch_before[c], 3) for c in cols],
    "after, 3xIQR": [count_outliers(ch_after[c], 3) for c in cols],
}, index=cols)
print("Number of outliers in monthly changes, 2016 onwards:")
print(table.to_string())