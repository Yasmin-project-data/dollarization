"""
Website panels for the decision rule (built by src/decision_rule.py).

Kept in its own file so that src/app.py only needs a few lines:

    from decision_panel import show_decision_status, show_decision_history
    show_decision_status()      # under the headline numbers
    show_decision_history()     # after the History chart

Reads model/decision_rule.json. Never estimates anything. If the file is
missing, shows a plain-language notice instead.
"""

import json
from pathlib import Path

import plotly.graph_objects as go
import streamlit as st

RULE_FILE = Path("model/decision_rule.json")

COLOURS = {"green": "#2e7d32", "amber": "#f9a825", "red": "#c62828"}
ICONS = {"green": "🟢", "amber": "🟡", "red": "🔴"}


def load_rule(path=RULE_FILE):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError, KeyError):
        return None


def missing_notice():
    st.warning(
        "The decision rule has not been built yet, or "
        f"`{RULE_FILE}` is missing. Build it with: "
        "`python src/decision_rule.py`"
    )


def show_decision_status(path=RULE_FILE):
    """One coloured box: this month's signal and what the treasury should do."""
    rule = load_rule(path)
    if rule is None:
        missing_notice()
        return
    latest = rule["latest"]
    text = (
        f"**{ICONS[latest['signal']]} Treasury signal for {latest['period']}: "
        f"{latest['label']}.** {latest['action']}  \n"
        f"Change this month: {latest['change_pp']:+.2f} pp "
        f"(at a constant exchange rate {latest['change_const_pp']:+.2f} pp). "
        f"Signal threshold: a rise above {rule['threshold_pp']:.2f} pp, "
        "which happens in about one month in ten."
    )
    box = {"green": st.success, "amber": st.warning, "red": st.error}
    box[latest["signal"]](text)


def history_chart(rule):
    history = rule["history"]
    colours = [COLOURS.get(s, "#9e9e9e") for s in history["signal"]]
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=history["period"], y=history["change_pp"], marker_color=colours,
        name="Monthly change",
        hovertemplate="%{x}: %{y:+.2f} pp<extra></extra>",
    ))
    fig.add_hline(
        y=rule["threshold_pp"], line_dash="dash", line_width=1,
        annotation_text=f"Signal threshold {rule['threshold_pp']:.2f} pp",
        annotation_position="top left",
    )
    holdout_start = rule["holdout_period"].split(" to ")[0]
    fig.add_vline(x=holdout_start, line_dash="dot", line_width=1)
    fig.add_annotation(x=holdout_start, y=1, yref="paper", showarrow=False,
                       text="hold-out →", xanchor="left", yanchor="top")
    fig.update_layout(
        height=320, margin=dict(l=10, r=10, t=10, b=10), showlegend=False,
        yaxis_title="Change in dollarization, pp per month", xaxis_title=None,
    )
    return fig


def show_decision_history(path=RULE_FILE):
    """When the rule would have fired in the past, and how it was chosen."""
    st.subheader("When the treasury signal fired")
    rule = load_rule(path)
    if rule is None:
        missing_notice()
        return
    st.plotly_chart(history_chart(rule), width="stretch")
    est, hold = rule["estimation_counts"], rule["holdout_counts"]
    st.caption(
        "Bars are monthly changes: green no signal, amber watch, red act. "
        f"The threshold is the {rule['percentile']}th percentile of monthly "
        f"changes over {rule['chosen_on']} only; months after the dotted line "
        "were not used to choose it. "
        f"Estimation months: {est['amber']} amber, {est['red']} red. "
        f"Hold-out ({rule['holdout_period']}): {hold['amber']} amber, "
        f"{hold['red']} red."
    )
    st.markdown(
        f"- **Amber (watch):** a rise above {rule['threshold_pp']:.2f} pp in a "
        "month, but the constant-rate measure did not rise much, so it is "
        "mostly revaluation of existing dollar deposits.\n"
        f"- **Red (act):** a rise above {rule['threshold_pp']:.2f} pp *and* "
        f"above {rule['threshold_const_pp']:.2f} pp at a constant exchange "
        "rate, so households are actually buying foreign currency.\n"
        "- A lower threshold gives more false alarms, a higher one can miss a "
        "crisis; the 85th and 95th percentiles are compared in "
        "`outputs/decision_sensitivity.csv`."
    )
