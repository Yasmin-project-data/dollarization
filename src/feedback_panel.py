"""
Website panel: "Does dollarization move the tenge?"

Kept in its own file so that src/app.py only needs two lines:

    from feedback_panel import show_feedback_panel
    show_feedback_panel()

Reads model/feedback.json (built by src/feedback.py). Never estimates
anything. If the file is missing, shows a plain-language notice instead.
"""

import json
from pathlib import Path

import plotly.graph_objects as go
import streamlit as st

FEEDBACK_FILE = Path("model/feedback.json")


def load_feedback(path=FEEDBACK_FILE):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError, KeyError):
        return None


def fmt_p(p):
    return "<0.001" if p < 0.001 else f"{p:.3f}"


def response_chart(irf, shock_pp):
    months = irf["month"]
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=months + months[::-1],
        y=irf["fx_upper"] + irf["fx_lower"][::-1],
        fill="toself", line=dict(width=0), opacity=0.25,
        name="95% band", hoverinfo="skip",
    ))
    fig.add_trace(go.Scatter(
        x=months, y=irf["fx_response"], mode="lines+markers",
        name="Tenge depreciation, %",
        hovertemplate="Month %{x}: %{y:+.2f}%<extra></extra>",
    ))
    fig.add_hline(y=0, line_width=1, line_dash="dot")
    fig.update_layout(
        height=340, margin=dict(l=10, r=10, t=10, b=10),
        xaxis_title="Months after the dollarization shock",
        yaxis_title="Response of monthly depreciation, %",
        legend=dict(orientation="h", y=1.08),
    )
    return fig


def show_feedback_panel(path=FEEDBACK_FILE):
    st.subheader("Does dollarization move the tenge?")
    feedback = load_feedback(path)
    if feedback is None:
        st.warning(
            "The feedback analysis has not been run yet, or "
            f"`{FEEDBACK_FILE}` is missing. Build it with: "
            "`python src/feedback.py`"
        )
        return

    granger = feedback["granger"]
    sample = feedback["sample"]
    shock = feedback["shock_size_dollarization_pp"]

    col1, col2, col3 = st.columns(3)
    col1.metric("Dollarization → exchange rate",
                granger["dollarization_to_fx"],
                f"Granger p = {fmt_p(granger['dollarization_to_fx_p'])}",
                delta_color="off")
    col2.metric("Exchange rate → dollarization",
                granger["fx_to_dollarization"],
                f"Granger p = {fmt_p(granger['fx_to_dollarization_p'])}",
                delta_color="off")
    col3.metric("Share of exchange-rate swings explained",
                f"{100 * feedback['fevd_fx_from_dollar_12m']:.1f}%",
                "by dollarization shocks, 12 months", delta_color="off")

    st.plotly_chart(response_chart(feedback["irf"], shock), width="stretch")
    st.caption(
        f"What happens to the tenge after dollarization rises unexpectedly by "
        f"{shock:.1f} pp in a month. The shaded band is the 95% interval: "
        "where it covers zero, the effect cannot be told apart from no effect. "
        f"Vector autoregression, {sample['start']} to {sample['end']} "
        f"({sample['n_obs']} months, {sample['lags']} lag chosen by AIC)."
    )
    predicts = granger["dollarization_to_fx"] == "significant"
    st.markdown(
        "- In the same month the two move together strongly "
        f"(correlation {feedback['same_month_corr']:.2f}), but that is mostly "
        "revaluation: a weaker tenge raises the tenge value of existing dollar "
        "deposits.\n"
        + ("- Looking only at what happens *afterwards*, past dollarization "
           "does help predict the exchange rate at the 5% level.\n"
           if predicts else
           "- Looking only at what happens *afterwards*, past dollarization "
           "does not help predict the exchange rate at the 5% level.\n")
        + "- With the monthly average rate instead of the end-of-month rate "
        "the result can look different; that is a timing difference between "
        "the two measures. All variants: `outputs/feedback_granger.csv`.\n"
        "- A monthly average over 2016-2026 cannot rule out effects in a "
        "panic, when many households buy dollars at once."
    )
