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
def load_data(path):
    data = pd.read_csv(path)
    data["date"] = pd.PeriodIndex(data["period"], freq="M").to_timestamp()
    return data


@st.cache_data
def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_or_none(loader, path):
    """Return the loaded object, or None if the file is missing or broken."""
    try:
        return loader(str(path))
    except (FileNotFoundError, ValueError, KeyError, json.JSONDecodeError):
        return None


data = load_or_none(load_data, DATA_FILE)
metadata = load_or_none(load_json, METADATA_FILE)
artifact = load_or_none(load_json, ARTIFACT_FILE)


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

st.subheader("What moved the indicator")
if artifact is None:
    st.warning(
        "The model has not been estimated yet, or `model/artifact.json` is "
        "missing. Driver contributions and the scenario tool will appear once "
        "the model is built with: `python src/model.py`"
    )
else:
    st.write("TODO: driver panel and scenario control (see docs/artifact_schema.md).")


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
            f"{sample['estimation_end']} ({sample['n_obs']} months); "
            f"last estimated {artifact['model']['estimated_at']}."
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
    "savings have disappeared."
)
