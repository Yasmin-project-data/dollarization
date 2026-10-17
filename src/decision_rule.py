"""
Decision rule for the user (a bank treasury planning foreign-currency
liquidity): turn the monthly reading into green / amber / red.

    green  normal month: no action
    amber  dollarization rose unusually fast, but mostly through
           revaluation (the constant-rate measure barely moved): watch
    red    dollarization rose unusually fast AND the constant-rate measure
           rose too: households are really converting tenge into foreign
           currency, so raise the foreign-currency liquidity buffer

"Unusually fast" is read from the data, not chosen by hand: the threshold
is the 90th percentile of monthly changes over the ESTIMATION months only
(2016-01 to 2024-06), i.e. a rise that happens in about one month in ten.
The constant-rate threshold is the 90th percentile of the constant-rate
measure over the same months. The hold-out months (2024-07 onwards) are then
used only to check how the rule would have behaved on data it never saw.
The 85th and 95th percentiles are reported as a sensitivity check.

Reads:  data/processed/monthly.csv
Writes: outputs/decision_signals.csv   (every month with its signal)
        outputs/decision_sensitivity.csv
        model/decision_rule.json       (read by the website)

Run from the project folder:
    python src/decision_rule.py
"""

import json

import numpy as np
import pandas as pd

import model as m

OUT_SIGNALS = m.OUT_DIR / "decision_signals.csv"
OUT_SENSITIVITY = m.OUT_DIR / "decision_sensitivity.csv"
OUT_JSON = m.ARTIFACT_FILE.parent / "decision_rule.json"

PERCENTILE = 0.90
SENSITIVITY = [0.85, 0.90, 0.95]

ACTIONS = {
    "green": ("No signal",
              "Normal month. No change to the foreign-currency liquidity "
              "buffer is needed."),
    "amber": ("Watch",
              "Dollarization rose faster than usual, but mostly because the "
              "tenge weakened and existing dollar deposits were revalued. "
              "Monitor closely; no extra buffer yet."),
    "red": ("Act",
            "Dollarization rose faster than usual even at a constant exchange "
            "rate: households are converting tenge into foreign currency. "
            "Raise the foreign-currency liquidity buffer."),
}


# ---------------------------------------------------------------------------
# Rule
# ---------------------------------------------------------------------------

def monthly_changes(monthly):
    """Change of the headline and constant-rate measures, pp per month."""
    return pd.DataFrame({
        "dollarization_pct": monthly["dollarization_pct"],
        "change_pp": monthly["dollarization_pct"].diff(),
        "change_const_pp": monthly["dollarization_const_pct"].diff(),
        "depreciation_eom_pct": 100 * np.log(monthly["usd_kzt_eom"]).diff(),
    })


def estimation_and_holdout_months(monthly):
    """The main model's split, so the rule never looks at the hold-out."""
    estimation, holdout = m.split_sample(m.build_model_table(monthly))
    return estimation.index, holdout.index


def thresholds(changes, months, percentile=PERCENTILE):
    est = changes.loc[months]
    return {
        "change_pp": float(est["change_pp"].quantile(percentile)),
        "change_const_pp": float(est["change_const_pp"].quantile(percentile)),
    }


def classify(change, change_const, limits):
    """green / amber / red for one month."""
    if pd.isna(change):
        return None
    if change <= limits["change_pp"]:
        return "green"
    if pd.notna(change_const) and change_const > limits["change_const_pp"]:
        return "red"
    return "amber"


def add_signals(changes, limits):
    out = changes.copy()
    out["signal"] = [classify(c, k, limits) for c, k in
                     zip(out["change_pp"], out["change_const_pp"])]
    return out


def count_signals(signals, months):
    part = signals.loc[months, "signal"]
    return {s: int((part == s).sum()) for s in ("green", "amber", "red")}


def sensitivity(changes, est_months, hold_months):
    rows = []
    for q in SENSITIVITY:
        limits = thresholds(changes, est_months, q)
        signals = add_signals(changes, limits)
        est = count_signals(signals, est_months)
        hold = count_signals(signals, hold_months)
        flagged = signals.loc[hold_months]
        flagged = flagged[flagged["signal"].isin(["amber", "red"])]
        rows.append({
            "percentile": int(round(100 * q)),
            "threshold_pp": limits["change_pp"],
            "threshold_const_pp": limits["change_const_pp"],
            "estimation_amber": est["amber"],
            "estimation_red": est["red"],
            "holdout_amber": hold["amber"],
            "holdout_red": hold["red"],
            "holdout_signal_months": " ".join(str(p) for p in flagged.index),
        })
    return pd.DataFrame(rows)


def build_rule(signals, limits, est_months, hold_months):
    latest = signals.dropna(subset=["signal"]).iloc[-1]
    period = signals.dropna(subset=["signal"]).index[-1]
    label, action = ACTIONS[latest["signal"]]
    flagged = signals[signals["signal"].isin(["amber", "red"])]
    return {
        "percentile": int(round(100 * PERCENTILE)),
        "threshold_pp": limits["change_pp"],
        "threshold_const_pp": limits["change_const_pp"],
        "chosen_on": f"{est_months[0]} to {est_months[-1]}",
        "latest": {
            "period": str(period),
            "change_pp": float(latest["change_pp"]),
            "change_const_pp": float(latest["change_const_pp"]),
            "signal": latest["signal"],
            "label": label,
            "action": action,
        },
        "estimation_counts": count_signals(signals, est_months),
        "holdout_counts": count_signals(signals, hold_months),
        "holdout_period": f"{hold_months[0]} to {hold_months[-1]}",
        "signal_months": [
            {"period": str(p), "signal": r["signal"],
             "change_pp": float(r["change_pp"]),
             "change_const_pp": float(r["change_const_pp"]),
             "in_holdout": p in hold_months}
            for p, r in flagged.iterrows()
            if p >= est_months[0]
        ],
        "history": {
            "period": [str(p) for p in signals.index if p >= est_months[0]],
            "change_pp": [None if pd.isna(v) else float(v) for v in
                          signals.loc[est_months[0]:, "change_pp"]],
            "signal": [s for s in signals.loc[est_months[0]:, "signal"]],
        },
        "actions": {k: {"label": v[0], "action": v[1]} for k, v in ACTIONS.items()},
    }


def main():
    monthly = m.read_monthly()
    changes = monthly_changes(monthly)
    est_months, hold_months = estimation_and_holdout_months(monthly)
    limits = thresholds(changes, est_months)
    signals = add_signals(changes, limits)

    m.OUT_DIR.mkdir(parents=True, exist_ok=True)
    signals.loc[est_months[0]:].to_csv(OUT_SIGNALS, float_format="%.4f")
    sens = sensitivity(changes, est_months, hold_months)
    sens.to_csv(OUT_SENSITIVITY, index=False, float_format="%.4f")
    rule = build_rule(signals, limits, est_months, hold_months)
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(rule, indent=2), encoding="utf-8")

    print(f"Thresholds (90th percentile, {rule['chosen_on']}): "
          f"change > {limits['change_pp']:.2f} pp; constant-rate change > "
          f"{limits['change_const_pp']:.2f} pp")
    print(f"Estimation months: {rule['estimation_counts']}")
    print(f"Hold-out months:   {rule['holdout_counts']}")
    for s in rule["signal_months"]:
        print(f"  {s['period']}  {s['signal']:<5}  {s['change_pp']:+.2f} pp "
              f"(constant rate {s['change_const_pp']:+.2f})"
              + ("  [hold-out]" if s["in_holdout"] else ""))
    print(f"Latest {rule['latest']['period']}: {rule['latest']['signal']} "
          f"-> {OUT_JSON}")
    print(sens.to_string(index=False))


if __name__ == "__main__":
    main()
