# %%
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path

df = pd.read_csv(Path("data/processed") / "monthly.csv",
                 parse_dates=["period"], index_col="period")
clean = df.copy()

cols = ["dollarization_pct", "dollarization_const_pct", "usd_kzt_avg",
        "rate_spread", "inflation_yoy_pct", "brent_usd"]
log_cols = ["usd_kzt_avg", "brent_usd"]  # detect on % change, not on level change
start = "2016-01-01"
log_rows = []

for col in cols:
    s = df.loc[start:, col]
    ch = np.log(s).diff() if col in log_cols else s.diff()
    q1, q3 = ch.quantile([0.25, 0.75])
    iqr = q3 - q1
    low, high = q1 - 3 * iqr, q3 + 3 * iqr
    bad = ch[(ch < low) | (ch > high)].index
    for month in bad:
        log_rows.append({"series": col, "month": month.strftime("%Y-%m"),
                         "old_value": round(s[month], 3), "change": round(ch[month], 3)})
        clean.loc[month, col] = np.nan
    clean[col] = clean[col].interpolate(limit_area="inside")

outlier_log = pd.DataFrame(log_rows)
print(outlier_log.to_string(index=False))
print("\nTotal replaced:", len(outlier_log))

clean.to_csv(Path("data/processed") / "monthly_clean.csv")
Path("outputs").mkdir(exist_ok=True)
outlier_log.to_csv(Path("outputs") / "outlier_log.csv", index=False)

fig, axes = plt.subplots(len(cols), 1, figsize=(11, 15), sharex=True)
for ax, col in zip(axes, cols):
    ax.plot(df.loc[start:, col], label="original", color="lightgray", lw=2)
    ax.plot(clean.loc[start:, col], label="cleaned", color="tab:blue", lw=1)
    ax.set_title(col)
axes[0].legend()
plt.tight_layout()
plt.show()