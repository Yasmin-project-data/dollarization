"""
Reproducibility check: are the numbers the pipeline just produced the same
as the numbers we report?

The reported numbers, each with its tolerance, are kept in
docs/expected_numbers.json. This script reads the files the pipeline
writes (data/processed, model/, outputs/) and compares every number with
the expected value. It prints PASS or FAIL for each and exits with an
error code if anything fails, so run.bat stops.

    python src/check.py            compare with docs/expected_numbers.json
    python src/check.py --record   write the current numbers as expected
                                   (only after a deliberate change, and say
                                   so in the commit message)

Headline tolerance: the latest dollarization value must reproduce within
±0.01 percentage points. Tolerances for the other numbers are in the file.
"""

import json
import sys
from pathlib import Path

import pandas as pd

EXPECTED_FILE = Path("docs/expected_numbers.json")
MONTHLY = Path("data/processed/monthly.csv")
ARTIFACT = Path("model/artifact.json")
FEEDBACK = Path("model/feedback.json")
RULE = Path("model/decision_rule.json")
ROBUSTNESS = Path("outputs/robustness.csv")

# name: (description, tolerance); a tolerance of None means "must be equal"
TOLERANCES = {
    "headline_dollarization_pct": ("Latest dollarization, % (headline)", 0.01),
    "headline_change_pp": ("Latest monthly change, pp", 0.01),
    "headline_period": ("Latest month", None),
    "ect_coef": ("Speed of adjustment (ECT)", 0.001),
    "depreciation_sr_coef": ("Short-run depreciation coefficient", 0.001),
    "bounds_f": ("Bounds-test F statistic", 0.01),
    "bounds_conclusion": ("Bounds-test conclusion", None),
    "rmse_ratio": ("RMSE ratio, model / random walk", 0.001),
    "benchmark_winner": ("Hold-out winner", None),
    "r3_depreciation_sr_coef": ("R3 depreciation coefficient (constant rate)", 0.001),
    "var_dollar_to_fx_p": ("VAR: dollarization -> exchange rate, Granger p", 0.01),
    "rule_threshold_pp": ("Decision rule threshold, pp", 0.01),
    "rule_latest_signal": ("Decision rule, latest signal", None),
}


def current_numbers():
    """Read every reported number from the files the pipeline wrote."""
    monthly = pd.read_csv(MONTHLY).dropna(subset=["dollarization_pct"])
    artifact = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    feedback = json.loads(FEEDBACK.read_text(encoding="utf-8"))
    rule = json.loads(RULE.read_text(encoding="utf-8"))
    robustness = pd.read_csv(ROBUSTNESS).set_index("id")
    coef = dict(zip(artifact["coefficients"]["names"],
                    artifact["coefficients"]["values"]))
    last, prev = monthly.iloc[-1], monthly.iloc[-2]
    return {
        "headline_dollarization_pct": float(last["dollarization_pct"]),
        "headline_change_pp": float(last["dollarization_pct"] - prev["dollarization_pct"]),
        "headline_period": str(last["period"]),
        "ect_coef": coef["dollarization_pct.L1"],
        "depreciation_sr_coef": coef["D.depreciation_1m.L0"],
        "bounds_f": artifact["diagnostics"]["bounds_test"]["f_stat"],
        "bounds_conclusion": artifact["diagnostics"]["bounds_test"]["conclusion"],
        "rmse_ratio": artifact["benchmark"]["rmse_ratio"],
        "benchmark_winner": artifact["benchmark"]["winner"],
        "r3_depreciation_sr_coef": float(robustness.loc["R3", "depreciation_sr_coef"]),
        "var_dollar_to_fx_p": feedback["granger"]["dollarization_to_fx_p"],
        "rule_threshold_pp": rule["threshold_pp"],
        "rule_latest_signal": rule["latest"]["signal"],
    }


def compare(current, expected):
    """List of (name, description, expected, current, ok)."""
    rows = []
    for name, (description, tolerance) in TOLERANCES.items():
        want = expected[name]["value"]
        have = current[name]
        if tolerance is None:
            ok = have == want
        else:
            ok = abs(float(have) - float(want)) <= tolerance
        rows.append((name, description, want, have, tolerance, ok))
    return rows


def record(current):
    expected = {name: {"value": current[name], "tolerance": tol,
                       "description": desc}
                for name, (desc, tol) in TOLERANCES.items()}
    EXPECTED_FILE.write_text(json.dumps(expected, indent=2), encoding="utf-8")
    print(f"Recorded {len(expected)} expected numbers -> {EXPECTED_FILE}")


def fmt(value):
    return f"{value:.4f}" if isinstance(value, float) else str(value)


def main(argv):
    try:
        current = current_numbers()
    except FileNotFoundError as error:
        print(f"FAIL: {error.filename} is missing. Run the pipeline first (run.bat).")
        return 1
    if "--record" in argv:
        record(current)
        return 0
    if not EXPECTED_FILE.exists():
        print(f"FAIL: {EXPECTED_FILE} not found. Create it with: "
              "python src/check.py --record")
        return 1
    expected = json.loads(EXPECTED_FILE.read_text(encoding="utf-8"))
    rows = compare(current, expected)
    for _, description, want, have, tolerance, ok in rows:
        tol = "exact" if tolerance is None else f"+/-{tolerance}"
        print(f"{'PASS' if ok else 'FAIL'}  {description:<48} "
              f"expected {fmt(want):<16} got {fmt(have):<16} ({tol})")
    failed = sum(not r[-1] for r in rows)
    if failed:
        print(f"\n{failed} of {len(rows)} numbers did NOT reproduce.")
        return 1
    print(f"\nAll {len(rows)} reported numbers reproduce within tolerance.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
