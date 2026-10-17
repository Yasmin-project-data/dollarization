"""Tests for the decision rule (src/decision_rule.py) and its website panels."""

import json
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import decision_rule as dr  # noqa: E402
import model  # noqa: E402

DATA = ROOT / "data/processed/monthly.csv"
needs_data = pytest.mark.skipif(not DATA.exists(),
                                reason="run python src/ingest.py first")
LIMITS = {"change_pp": 0.6, "change_const_pp": 0.4}


def test_classify():
    assert dr.classify(0.1, 0.9, LIMITS) == "green"      # small rise
    assert dr.classify(1.0, 0.1, LIMITS) == "amber"      # revaluation only
    assert dr.classify(1.0, 0.9, LIMITS) == "red"        # real buying
    assert dr.classify(float("nan"), 0.9, LIMITS) is None


@needs_data
def test_thresholds_use_estimation_months_only():
    monthly = model.read_monthly()
    changes = dr.monthly_changes(monthly)
    est, hold = dr.estimation_and_holdout_months(monthly)
    limits = dr.thresholds(changes, est)
    assert limits["change_pp"] == pytest.approx(
        changes.loc[est, "change_pp"].quantile(dr.PERCENTILE))
    # Changing hold-out values must not move the threshold.
    changed = changes.copy()
    changed.loc[hold, "change_pp"] = 100.0
    assert dr.thresholds(changed, est) == limits


@needs_data
def test_about_one_month_in_ten_signals_in_estimation():
    monthly = model.read_monthly()
    changes = dr.monthly_changes(monthly)
    est, _ = dr.estimation_and_holdout_months(monthly)
    signals = dr.add_signals(changes, dr.thresholds(changes, est))
    counts = dr.count_signals(signals, est)
    share = (counts["amber"] + counts["red"]) / len(est)
    assert 0.05 <= share <= 0.15


def test_panel_without_file_shows_notice(tmp_path):
    from streamlit.testing.v1 import AppTest

    def script(path):
        import sys
        sys.path.insert(0, "src")
        from decision_panel import show_decision_status
        show_decision_status(path)

    at = AppTest.from_function(script, args=(str(tmp_path / "missing.json"),))
    at.run()
    assert not at.exception
    assert "python src/decision_rule.py" in at.warning[0].value


@pytest.mark.skipif(not (ROOT / "model/decision_rule.json").exists(),
                    reason="run python src/decision_rule.py first")
def test_rule_file_is_consistent():
    rule = json.loads((ROOT / "model/decision_rule.json").read_text(encoding="utf-8"))
    assert rule["latest"]["signal"] in ("green", "amber", "red")
    assert rule["latest"]["label"] == rule["actions"][rule["latest"]["signal"]]["label"]
    assert len(rule["history"]["period"]) == len(rule["history"]["change_pp"])
