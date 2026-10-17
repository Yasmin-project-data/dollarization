"""
Presentation layer: the website.

Reads:  data/processed/monthly.csv     (built by src/ingest.py)
        data/processed/metadata.json   (built by src/ingest.py)
        model/artifact.json            (built by src/model.py, may not exist yet)
Never estimates anything and never downloads anything: it only shows what
the data and model layers have already saved.

Run from the project folder:
    streamlit run src/app.py
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

DATA_FILE = Path("data/processed/monthly.csv")
METADATA_FILE = Path("data/processed/metadata.json")
ARTIFACT_FILE = Path("model/artifact.json")

st.set_page_config(page_title="KZ Deposit Dollarization", layout="wide")


# ---------------------------------------------------------------------------
# Loading (cached, so the page renders fast)
# ---------------------------------------------------------------------------

@st.cache_data
def load_data(path, modified):
    data = pd.read_csv(path)
    data["date"] = pd.PeriodIndex(data["period"], freq="M").to_timestamp()
    return data


@st.cache_data
def load_json(path, modified):
    return json.loads(Path(path).read_text(encoding="utf-8"))


ARTIFACT_KEYS = ["model", "factors", "coefficients", "long_run", "latest",
                 "scenario", "diagnostics", "benchmark", "residual_std"]


@st.cache_data
def load_artifact(path, modified):
    artifact = json.loads(Path(path).read_text(encoding="utf-8"))
    missing = [key for key in ARTIFACT_KEYS if key not in artifact]
    if missing:
        raise ValueError(f"Model file lacks: {', '.join(missing)}")
    return artifact


def load_or_none(loader, path):
    """Return the loaded object, or None if the file is missing or broken.

    The file's modification time is part of the cache key, and a missing
    file is detected before the cache is consulted, so a renamed or edited
    file is noticed on the next reload.
    """
    try:
        modified = Path(path).stat().st_mtime
        return loader(str(path), modified)
    except (FileNotFoundError, ValueError, KeyError, json.JSONDecodeError):
        return None


data = load_or_none(load_data, DATA_FILE)
metadata = load_or_none(load_json, METADATA_FILE)
artifact = load_or_none(load_artifact, ARTIFACT_FILE)


# ---------------------------------------------------------------------------
# Error state: no data at all
# ---------------------------------------------------------------------------

if data is None or data.empty:
    st.title("Kazakhstan Household Deposit Dollarization Index")
    st.error(
        "The processed data file was not found or could not be read "
        f"(`{DATA_FILE}`). Rebuild it with: `python src/ingest.py`"
    )
    st.stop()


# ---------------------------------------------------------------------------
# Headline (visible without scrolling)
# ---------------------------------------------------------------------------

series = data.dropna(subset=["dollarization_pct"])
latest = series.iloc[-1]
previous = series.iloc[-2]
change = latest["dollarization_pct"] - previous["dollarization_pct"]
latest_month = pd.Period(latest["period"], freq="M").strftime("%B %Y")

st.title("Kazakhstan Household Deposit Dollarization Index")
st.caption(
    "Share of household bank deposits held in foreign currency. "
    "For bank treasury teams planning foreign-currency liquidity."
)

col1, col2, col3 = st.columns(3)
col1.metric(
    label=f"Dollarization, {latest_month}",
    value=f"{latest['dollarization_pct']:.1f}%",
    delta=f"{change:+.2f} pp vs previous month",
    delta_color="inverse",  # a rise in dollarization is shown in red
)
col2.metric(
    label="Foreign-currency deposits",
    value=f"{latest['fx_total'] / 1e6:.2f} trn KZT",
    delta=f"{latest['fx_total_usd_mn'] / 1e3:.1f} bn USD",
    delta_color="off",
)
col3.metric(
    label="Tenge deposits",
    value=f"{latest['kzt_total'] / 1e6:.2f} trn KZT",
)

retrieved = None
if metadata:
    retrieved = metadata["sources"]["deposits"]["retrieved"]
st.info(
    "Data shown from the cached snapshot in this repository"
    + (f" (retrieved {retrieved})." if retrieved else ".")
    + " The site does not download anything, so it works offline."
)


# ---------------------------------------------------------------------------
# History
# ---------------------------------------------------------------------------

st.subheader("History")
fig = go.Figure()
fig.add_trace(go.Scatter(
    x=series["date"], y=series["dollarization_pct"],
    mode="lines", name="Dollarization",
    hovertemplate="%{x|%b %Y}: %{y:.1f}%<extra></extra>",
))
fig.update_layout(
    yaxis_title="Foreign-currency share of household deposits, %",
    xaxis_title=None,
    height=420,
    margin=dict(l=10, r=10, t=10, b=60),
)
fig.add_annotation(
    text="Source: National Bank of Kazakhstan, household deposits by currency; "
         "team calculations.",
    xref="paper", yref="paper", x=0, y=-0.15, showarrow=False,
    font=dict(size=11), xanchor="left",
)
st.plotly_chart(fig, width="stretch")


# ---------------------------------------------------------------------------
# Model panels (need model/artifact.json)
# ---------------------------------------------------------------------------

GROUP_LABELS = {
    "own_dynamics": "Recent changes in the indicator itself",
    "error_correction": "Pull toward the long-run level",
    "residual": "Not explained by the model",
}
DIAGNOSTIC_LABELS = {
    "breusch_godfrey_p": "serial correlation (Breusch-Godfrey)",
    "breusch_pagan_p": "constant variance of residuals (Breusch-Pagan)",
    "jarque_bera_p": "normal residuals (Jarque-Bera)",
    "cusum_p": "stable coefficients (CUSUM)",
    "chow_2020_03_p": "no break in March 2020 (Chow)",
    "chow_2022_03_p": "no break in March 2022 (Chow)",
}
POSITIVE_COLOR, NEGATIVE_COLOR = "#2a6f97", "#d98324"


def month_name(period):
    return pd.Period(period, freq="M").strftime("%B %Y")


def contribution_labels(artifact):
    sample = artifact["model"]["sample"]
    labels = {f["name"]: f["label"] for f in artifact["factors"]}
    labels.update(GROUP_LABELS)
    labels["constant"] = (f"Average monthly change, {sample['estimation_start']}"
                          f" to {sample['estimation_end']}")
    return labels


def show_drivers(artifact):
    """Bar chart and table of the latest month's contributions."""
    latest = artifact["latest"]
    labels = contribution_labels(artifact)
    names = list(latest["contributions"])
    values = [latest["contributions"][n] for n in names]
    fig = go.Figure(go.Bar(
        x=values, y=[labels[n] for n in names], orientation="h",
        marker_color=[POSITIVE_COLOR if v >= 0 else NEGATIVE_COLOR for v in values],
        text=[f"{v:+.2f}" for v in values], textposition="outside",
        hovertemplate="%{y}: %{x:+.2f} pp<extra></extra>",
    ))
    fig.update_layout(
        xaxis_title="Contribution to the monthly change, percentage points",
        yaxis=dict(autorange="reversed"), height=380,
        margin=dict(l=10, r=10, t=10, b=50),
    )
    st.plotly_chart(fig, width="stretch")
    st.caption(
        f"Change in {month_name(latest['period'])}: {latest['change']:+.2f} pp, "
        "equal to the sum of the bars. Each driver is measured against its "
        "average in the estimation sample. These are conditional correlations "
        "from the model, not proven causes."
    )

    rows = []
    for factor in artifact["factors"]:
        long_run = artifact["long_run"][factor["name"]]
        estimated_sign = "+" if long_run > 0 else "-"
        rows.append({
            "Driver": factor["label"],
            "Contribution, pp": round(latest["contributions"][factor["name"]], 2),
            "Expected long-run sign": factor["expected_sign"],
            "Estimated long-run sign": estimated_sign,
            "As expected": "yes" if estimated_sign == factor["expected_sign"] else "no",
        })
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")


def scenario_point(artifact, control, shift):
    """Implied level next month and the half-width of its 95% band.

    Plain matrix arithmetic on numbers read from the artifact: the regressor
    vector x is moved by `shift`, then change = x'b and variance = x'Vx.
    """
    scenario, coef = artifact["scenario"], artifact["coefficients"]
    x = np.array(scenario["base_regressors"], dtype=float)
    for name, effect in control["regressor_effect"].items():
        x[coef["names"].index(name)] += shift * effect
    change = float(x @ np.array(coef["values"]))
    variance = float(x @ np.array(coef["covariance"]) @ x)
    return scenario["base_level"] + change, 1.96 * variance ** 0.5


def show_scenario(artifact):
    scenario = artifact["scenario"]
    st.markdown(f"**Scenario: {month_name(scenario['base_period'])}**")
    st.caption(
        "Next month's dollarization if every driver stays where it is, "
        "except the one you move below."
    )
    controls = scenario["controls"]
    control = st.selectbox("Driver to change", controls,
                           format_func=lambda c: c["label"])
    shift = st.slider(control["label"], float(control["min"]),
                      float(control["max"]), 0.0, float(control["step"]))
    level, half_width = scenario_point(artifact, control, shift)
    base_level, _ = scenario_point(artifact, control, 0.0)

    left, right = st.columns(2)
    left.metric(f"Implied dollarization, {month_name(scenario['base_period'])}",
                f"{level:.1f}%",
                delta=f"{level - base_level:+.2f} pp vs no change",
                delta_color="inverse")  # a rise in dollarization is shown in red
    right.metric("95% band (coefficient uncertainty)",
                 f"{level - half_width:.1f}% to {level + half_width:.1f}%")

    grid = np.linspace(control["min"], control["max"], 50)
    points = [scenario_point(artifact, control, s) for s in grid]
    centre = np.array([p[0] for p in points])
    width = np.array([p[1] for p in points])
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=grid, y=centre + width, mode="lines",
                             line=dict(width=0), showlegend=False,
                             hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=grid, y=centre - width, mode="lines",
                             line=dict(width=0), fill="tonexty",
                             fillcolor="rgba(42,111,151,0.2)",
                             name="95% band", hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=grid, y=centre, mode="lines", name="Implied level",
                             line=dict(color=POSITIVE_COLOR),
                             hovertemplate="%{x}: %{y:.2f}%<extra></extra>"))
    fig.add_vline(x=shift, line_dash="dot")
    fig.update_layout(xaxis_title=control["label"],
                      yaxis_title="Dollarization, %", height=320,
                      margin=dict(l=10, r=10, t=10, b=50), showlegend=False)
    st.plotly_chart(fig, width="stretch")
    st.caption(
        "The band comes from the covariance matrix of the estimated "
        "coefficients. A typical monthly surprise on top of it is about "
        f"{artifact['residual_std']:.1f} pp."
    )


def show_model_check(artifact):
    """Say plainly whether the model beat the benchmark, and what failed."""
    bench = artifact["benchmark"]
    message = (
        f"On the {bench['n_holdout']} months held out from estimation, the "
        f"model's one-month-ahead error ({bench['rmse_model']:.2f} pp RMSE) was "
        f"{bench['rmse_ratio']:.2f} times that of a no-change forecast "
        f"({bench['rmse_benchmark']:.2f} pp)."
    )
    if bench["winner"] == "model":
        st.success(message + " The model beats the benchmark.")
    else:
        st.warning(message + " The model does not beat the benchmark, so read "
                   "the split above as a description of the past, not as a "
                   "forecasting tool.")
    diagnostics = artifact["diagnostics"]
    failed = [label for key, label in DIAGNOSTIC_LABELS.items()
              if diagnostics.get(key) is not None and diagnostics[key] < 0.05]
    if failed:
        st.caption("Diagnostic tests failed (5% level): " + "; ".join(failed) + ".")


st.subheader("What moved the indicator")
if artifact is None:
    st.warning(
        "The model file `model/artifact.json` is missing or could not be read, "
        "so driver contributions and the scenario tool are not available. "
        "The data panels still work. Rebuild the model with: `python src/model.py`"
    )
else:
    show_drivers(artifact)
    st.subheader("Scenario")
    show_scenario(artifact)
    show_model_check(artifact)


# ---------------------------------------------------------------------------
# Provenance
# ---------------------------------------------------------------------------

with st.expander("Data sources and model details", expanded=False):
    if metadata is None:
        st.warning(f"Source information not found (`{METADATA_FILE}`). "
                   "Rebuild it with: `python src/ingest.py`")
    else:
        rows = [
            {
                "Series": s["label"],
                "Publisher": s["publisher"],
                "Identifier": s["series"],
                "Coverage": f"{s['first_period']} to {s['last_period']}",
                "Retrieved": s["retrieved"],
                "Link": s["url"],
            }
            for s in metadata["sources"].values()
        ]
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    if artifact is not None:
        sample = artifact["model"]["sample"]
        st.write(
            f"Model estimated on {sample['estimation_start']} to "
            f"{sample['estimation_end']} ({sample['n_months']} months, "
            f"{sample['n_obs']} observations after lags); tested on "
            f"{sample['holdout_start']} to {sample['holdout_end']}. "
            f"Last estimated {artifact['model']['estimated_at']}. "
            f"{artifact['model']['specifications_estimated']} lag combinations "
            "were compared."
        )
        bounds = artifact["diagnostics"]["bounds_test"]
        st.write(
            f"Long-run relationship (bounds test): F = {bounds['f_stat']:.2f} "
            f"against 5% bounds {bounds['crit_5pct_lower']:.2f} to "
            f"{bounds['crit_5pct_upper']:.2f}: {bounds['conclusion']}."
        )


# ---------------------------------------------------------------------------
# Honesty
# ---------------------------------------------------------------------------

st.subheader("What this indicator cannot tell you")
st.markdown(
    "- When the tenge weakens, foreign-currency deposits rise in tenge terms "
    "even if nobody buys dollars, so part of any rise is pure revaluation.\n"
    "- Cash dollars kept outside banks are not counted, and the index covers "
    "households only, not companies.\n"
    "- Most of the long fall since 2016 comes from growing tenge deposits, not "
    "from households selling dollars: a low reading does not mean dollar "
    "savings have disappeared.\n"
    "- The scenario tool shows mostly an accounting effect. When dollarization "
    "is measured at a constant exchange rate, the depreciation effect "
    "disappears (robustness check R3): a weaker tenge revalues existing dollar "
    "deposits rather than making households buy more dollars.\n"
    "- The effect of depreciation depends on how dollarized deposits already "
    "are (robustness check L2). At today's level it is close to zero; it was "
    "larger when dollarization was higher."
)
