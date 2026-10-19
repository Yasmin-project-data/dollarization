"""
Figures for the technical note, generated from the pipeline's own files.

The guide (Section 18): "Figures and tables are generated into outputs/ and
placed in the note from there." Every figure below is drawn from
data/processed, model/ and outputs/, never from numbers typed by hand.

    fig1_history.png         dollarization since 2010, regime and shock months,
                             hold-out shaded
    fig2_constant_rate.png   headline vs constant-exchange-rate dollarization
    fig3_holdout.png         hold-out: actual, model nowcast, random walk
    fig4_diagnostics.png     residuals over time and the CUSUM test
    fig5_var_irf.png         VAR impulse responses in both directions
    fig6_signals.png         treasury decision rule: monthly changes and signals

Reads:  data/processed/monthly.csv, model/artifact.json,
        outputs/holdout_forecast.csv, outputs/feedback_irf.csv,
        outputs/decision_signals.csv, model/decision_rule.json
Writes: outputs/figures/*.png (200 dpi, 6.5 inches wide, for Word)

Run from the project folder (after the other scripts):
    python src/figures.py
"""

import json
import warnings

import matplotlib

matplotlib.use("Agg")                       # draw to files, no window

import matplotlib.dates                      # noqa: E402
import matplotlib.pyplot as plt             # noqa: E402
import numpy as np                          # noqa: E402
import pandas as pd                         # noqa: E402

import model as m                           # noqa: E402

OUT = m.OUT_DIR / "figures"
DPI = 200
WIDTH = 6.5                                 # inches, a Word page minus margins

# Colours: a validated categorical palette (first three slots pass the
# colour-blind separation checks) and a fixed status palette for signals.
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
GOOD, WARNING, CRITICAL = "#0ca30c", "#fab219", "#d03b3b"
INK, INK_2, MUTED = "#0b0b0b", "#52514e", "#898781"
GRID, AXIS = "#e1e0d9", "#c3c2b7"

plt.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["Segoe UI", "DejaVu Sans", "Arial"],
    "font.size": 9,
    "axes.edgecolor": AXIS,
    "axes.labelcolor": INK_2,
    "axes.titlecolor": INK,
    "axes.titlesize": 10,
    "axes.titleweight": "bold",
    "axes.titlelocation": "left",
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.grid": True,
    "axes.grid.axis": "y",
    "grid.color": GRID,
    "grid.linewidth": 0.6,
    "xtick.color": MUTED,
    "ytick.color": MUTED,
    "xtick.labelcolor": INK_2,
    "ytick.labelcolor": INK_2,
    "legend.frameon": False,
    "legend.labelcolor": INK_2,
    "lines.linewidth": 2,
    "figure.facecolor": "white",
    "axes.facecolor": "white",
    "savefig.facecolor": "white",
})


def months(index):
    return pd.PeriodIndex(index, freq="M").to_timestamp()


def source_note(fig, text, y=-0.03):
    fig.text(0.01, y, text, fontsize=7, color=MUTED, ha="left", va="top")


def save(fig, name):
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / name
    fig.savefig(path, dpi=DPI, bbox_inches="tight")
    plt.close(fig)
    return path


def holdout_start(artifact):
    return pd.Period(artifact["model"]["sample"]["holdout_start"], freq="M").to_timestamp()


# ---------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------

def fig_history(monthly, artifact):
    series = monthly["dollarization_pct"].dropna()
    x = months(series.index)
    fig, ax = plt.subplots(figsize=(WIDTH, 3.0))
    hold = holdout_start(artifact)
    ax.axvspan(hold, x[-1], color=GRID, alpha=0.6, lw=0)
    ax.text(hold, series.max(), "  hold-out", color=INK_2, fontsize=8, va="top")
    ax.plot(x, series.values, color=BLUE)
    events = [("2015-08", "Tenge floated\nAug 2015", 3),
              ("2020-03", "COVID, oil\nMar 2020", 13),
              ("2022-02", "War in Ukraine\nFeb 2022", 3)]
    for period, label, height in events:
        when = pd.Period(period, freq="M").to_timestamp()
        ax.axvline(when, color=AXIS, lw=1, ls=(0, (3, 3)))
        ax.text(when, height, " " + label, fontsize=7.5, color=INK_2,
                va="bottom")
    last = series.iloc[-1]
    ax.annotate(f"{last:.1f}%\n{series.index[-1]}", (x[-1], last),
                xytext=(6, 0), textcoords="offset points", fontsize=8,
                color=INK, va="center")
    ax.set_ylabel("Foreign-currency share, %")
    ax.set_title("Household deposit dollarization, Kazakhstan")
    ax.set_ylim(0, series.max() * 1.08)
    source_note(fig, "Source: National Bank of Kazakhstan; team calculations. "
                     "End-of-month stocks.")
    return save(fig, "fig1_history.png")


def fig_constant_rate(monthly):
    data = monthly.loc[str(m.SAMPLE_START):, ["dollarization_pct",
                                              "dollarization_const_pct"]].dropna()
    x = months(data.index)
    fig, ax = plt.subplots(figsize=(WIDTH, 3.0))
    ax.plot(x, data["dollarization_pct"], color=BLUE,
            label="Headline (current exchange rate)")
    ax.plot(x, data["dollarization_const_pct"], color=ORANGE, ls=(0, (5, 2)),
            label="At the January 2016 exchange rate")
    for col, colour in [("dollarization_pct", BLUE),
                        ("dollarization_const_pct", ORANGE)]:
        ax.annotate(f"{data[col].iloc[-1]:.1f}%", (x[-1], data[col].iloc[-1]),
                    xytext=(6, 0), textcoords="offset points", fontsize=8,
                    color=INK, va="center")
    ax.set_ylabel("Foreign-currency share, %")
    ax.set_title("Revaluation vs behaviour: dollarization at a constant exchange rate")
    ax.legend(loc="upper right")
    source_note(fig, "The gap between the lines is the pure revaluation effect "
                     "of exchange-rate moves since January 2016.")
    return save(fig, "fig2_constant_rate.png")


def fig_holdout(artifact):
    forecast = pd.read_csv(m.OUT_DIR / "holdout_forecast.csv")
    x = months(forecast["period"])
    bench = artifact["benchmark"]
    fig, ax = plt.subplots(figsize=(WIDTH, 3.0))
    ax.plot(x, forecast["actual"], color=INK, lw=2, label="Actual")
    ax.plot(x, forecast["model"], color=BLUE, marker="o", ms=4,
            label=f"Model nowcast (RMSE {bench['rmse_model']:.2f} pp)")
    ax.plot(x, forecast["benchmark"], color=ORANGE, ls=(0, (5, 2)),
            label=f"Random walk (RMSE {bench['rmse_benchmark']:.2f} pp)")
    ax.xaxis.set_major_locator(matplotlib.dates.MonthLocator(bymonth=(1, 7)))
    ax.xaxis.set_major_formatter(matplotlib.dates.DateFormatter("%b %Y"))
    ax.set_ylabel("Dollarization, %")
    ax.set_title(f"Hold-out, {forecast['period'].iloc[0]} to "
                 f"{forecast['period'].iloc[-1]}: the random walk wins "
                 f"(RMSE ratio {bench['rmse_ratio']:.2f})")
    ax.legend(loc="lower left")
    source_note(fig, "One-month-ahead nowcasts with coefficients estimated "
                     "on 2016-01 to 2024-06 only.")
    return save(fig, "fig3_holdout.png")


def fitted_model(monthly, artifact):
    table = m.build_model_table(monthly)
    estimation, _ = m.split_sample(table)
    est = m.add_regressors(table).loc[estimation.index]
    lags = artifact["model"]["lags"]
    order = tuple([lags[m.DEPENDENT]] + [lags[r] for r in m.REGRESSORS])
    uecm, result = m.fit_uecm(est, order)
    return uecm, result


def fig_diagnostics(monthly, artifact):
    uecm, _ = fitted_model(monthly, artifact)
    ols = m.ols_of(uecm)
    _, _, rows = m.design(uecm)
    resid = pd.Series(ols.resid, index=rows)
    sigma = np.sqrt(ols.scale)
    cusum = resid.cumsum() / (sigma * np.sqrt(len(resid)))
    bound = 1.358                         # 5% critical value, OLS-residual CUSUM
    x = months(resid.index)

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(WIDTH, 4.6), sharex=True)
    ax1.bar(x, resid.values, width=20, color=BLUE)
    for k in (2, -2):
        ax1.axhline(k * sigma, color=MUTED, lw=1, ls=(0, (3, 3)))
    ax1.text(x[0], 2 * sigma, "  ±2 s.d.", color=INK_2, fontsize=7.5, va="bottom")
    biggest = resid.abs().idxmax()
    ax1.annotate(f"{biggest}: {resid[biggest]:+.1f} pp",
                 (biggest.to_timestamp(), resid[biggest]),
                 xytext=(8, 0), textcoords="offset points", fontsize=7.5,
                 color=INK, va="center")
    ax1.set_ylabel("Residual, pp")
    ax1.set_title("Model residuals: no serial correlation, larger errors in crisis months")

    ax2.plot(x, cusum.values, color=BLUE)
    ax2.fill_between(x, -bound, bound, color=GRID, alpha=0.6, lw=0)
    ax2.axhline(0, color=AXIS, lw=1)
    ax2.text(x[0], bound, "  5% bounds", color=INK_2, fontsize=7.5, va="bottom")
    ax2.set_ylim(-2, 2)
    ax2.set_ylabel("CUSUM statistic")
    p = artifact["diagnostics"]["cusum_p"]
    ax2.set_title(f"CUSUM stays inside the 5% bounds (p = {p:.2f}): "
                  "coefficients stable")
    source_note(fig, "Residuals of the error-correction model, estimation "
                     "sample. Breusch-Godfrey p = "
                     f"{artifact['diagnostics']['breusch_godfrey_p']:.2f}; "
                     "Breusch-Pagan p < 0.001 (HAC standard errors used).")
    fig.tight_layout()
    return save(fig, "fig4_diagnostics.png")


def fig_var_irf():
    irf = pd.read_csv(m.OUT_DIR / "feedback_irf.csv")
    feedback = json.loads((m.ARTIFACT_FILE.parent / "feedback.json")
                          .read_text(encoding="utf-8"))
    g = feedback["granger"]
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(WIDTH, 2.9))
    panels = [
        (ax1, "fx", f"Dollarization → tenge\n(Granger p = {g['dollarization_to_fx_p']:.2f})",
         "Response of depreciation, %"),
        (ax2, "dollar", f"Tenge → dollarization\n(Granger p = {g['fx_to_dollarization_p']:.2f})",
         "Response of dollarization, pp"),
    ]
    for ax, key, title, ylabel in panels:
        ax.fill_between(irf["month"], irf[f"{key}_lower"], irf[f"{key}_upper"],
                        color=BLUE, alpha=0.18, lw=0, label="95% band")
        ax.plot(irf["month"], irf[f"{key}_response"], color=BLUE, marker="o",
                ms=3.5, label="Response")
        ax.axhline(0, color=AXIS, lw=1)
        ax.set_title(title, fontsize=9)
        ax.set_xlabel("Months after the shock")
        ax.set_ylabel(ylabel)
        ax.set_xlim(0, 12)
    ax1.legend(loc="upper right", fontsize=7.5)
    source_note(fig, "Four-variable VAR, 2016 onwards, one-standard-deviation "
                     "Cholesky shocks (oil, spread, depreciation, dollarization); "
                     "Monte Carlo bands, seed 2026.")
    fig.tight_layout()
    return save(fig, "fig5_var_irf.png")


def fig_signals():
    signals = pd.read_csv(m.OUT_DIR / "decision_signals.csv").dropna(subset=["signal"])
    rule = json.loads((m.ARTIFACT_FILE.parent / "decision_rule.json")
                      .read_text(encoding="utf-8"))
    x = months(signals["period"])
    colours = signals["signal"].map({"green": GOOD, "amber": WARNING, "red": CRITICAL})
    fig, ax = plt.subplots(figsize=(WIDTH, 3.0))
    ax.bar(x, signals["change_pp"], width=22, color=colours)
    ax.axhline(rule["threshold_pp"], color=INK_2, lw=1, ls=(0, (4, 3)))
    ax.text(pd.Timestamp("2022-11-01"), rule["threshold_pp"] + 0.1,
            f"threshold {rule['threshold_pp']:.2f} pp", color=INK_2,
            fontsize=7.5, va="bottom")
    hold = pd.Period(rule["holdout_period"].split(" to ")[0], freq="M").to_timestamp()
    ax.axvline(hold, color=AXIS, lw=1, ls=(0, (3, 3)))
    ax.text(hold, ax.get_ylim()[1], " hold-out →", color=INK_2, fontsize=7.5, va="top")
    ax.axhline(0, color=AXIS, lw=1)
    handles = [plt.Rectangle((0, 0), 1, 1, color=c) for c in (GOOD, WARNING, CRITICAL)]
    ax.legend(handles, ["Green: no signal", "Amber: watch (mostly revaluation)",
                        "Red: act (real conversion)"], loc="upper center",
              bbox_to_anchor=(0.5, -0.1), ncol=3, fontsize=7.5)
    ax.set_ylabel("Change in dollarization, pp per month")
    ax.set_title("Treasury decision rule: when the signal fired")
    source_note(fig, f"Threshold: 90th percentile of monthly changes, "
                     f"{rule['chosen_on']} only. Red also "
                     "needs a rise above "
                     f"{rule['threshold_const_pp']:.2f} pp at a constant exchange rate.",
                y=-0.12)
    return save(fig, "fig6_signals.png")


def main():
    warnings.simplefilter("ignore")
    monthly = m.read_monthly()
    artifact = json.loads(m.ARTIFACT_FILE.read_text(encoding="utf-8"))
    paths = [
        fig_history(monthly, artifact),
        fig_constant_rate(monthly),
        fig_holdout(artifact),
        fig_diagnostics(monthly, artifact),
        fig_var_irf(),
        fig_signals(),
    ]
    for path in paths:
        print(f"-> {path}")


if __name__ == "__main__":
    main()
