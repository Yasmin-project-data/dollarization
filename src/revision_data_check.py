# %%
import warnings
import numpy as np
import pandas as pd
from pathlib import Path
from statsmodels.tsa.stattools import adfuller, kpss

warnings.filterwarnings("ignore")  # KPSS warns when p-value is outside its lookup table

d = pd.read_csv(Path("data/processed") / "monthly_clean.csv",
                parse_dates=["period"], index_col="period").loc["2016-01-01":]

series = {
    "dollarization_pct": d["dollarization_pct"],
    "dollarization_const_pct": d["dollarization_const_pct"],
    "depreciation_1m_pct": d["usd_kzt_avg"].pct_change() * 100,
    "rate_spread": d["rate_spread"],
    "inflation_yoy_pct": d["inflation_yoy_pct"],
    "log_brent": np.log(d["brent_usd"]),
}

rows = []
for name, s in series.items():
    for form, x, reg in [("level", s, "c"), ("level+trend", s, "ct"), ("diff", s.diff(), "c")]:
        x = x.dropna()
        adf_p = adfuller(x, regression=reg, autolag="AIC")[1]
        kpss_p = kpss(x, regression=reg, nlags="auto")[1]
        if adf_p < 0.05 and kpss_p > 0.05:
            verdict = "stationary"
        elif adf_p >= 0.05 and kpss_p <= 0.05:
            verdict = "non-stationary"
        else:
            verdict = "unclear"
        rows.append({"series": name, "form": form, "ADF p": round(adf_p, 3),
                     "KPSS p": round(kpss_p, 3), "verdict": verdict})

table = pd.DataFrame(rows)
print(table.to_string(index=False))
table.to_csv(Path("outputs") / "stationarity_tests.csv", index=False)

# %%
from statsmodels.tsa.stattools import zivot_andrews

extra = {
    "dollarization_pct": d["dollarization_pct"],
    "dollarization_const_pct": d["dollarization_const_pct"],
    "logit_dollarization": np.log(d["dollarization_pct"] / (100 - d["dollarization_pct"])),
    "logit_dollarization_const": np.log(d["dollarization_const_pct"] / (100 - d["dollarization_const_pct"])),
    "inflation_yoy_pct": d["inflation_yoy_pct"],
}

rows = []
for name, s in extra.items():
    for form, x in [("level", s), ("diff", s.diff())]:
        x = x.dropna()
        adf_ct = adfuller(x, regression="ct", autolag="AIC")[1]
        kpss_ct = kpss(x, regression="ct", nlags="auto")[1]
        za = zivot_andrews(x, regression="c", autolag="AIC")
        rows.append({"series": name, "form": form,
                     "ADF(ct) p": round(adf_ct, 3), "KPSS(ct) p": round(kpss_ct, 3),
                     "ZA p": round(za[1], 3), "ZA break": x.index[za[4]].strftime("%Y-%m")})

extra_table = pd.DataFrame(rows)
print()
print(extra_table.to_string(index=False))
extra_table.to_csv(Path("outputs") / "stationarity_extra.csv", index=False)