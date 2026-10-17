"""Tests for the reproducibility check (src/check.py)."""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import check  # noqa: E402


def fake_expected(values):
    return {k: {"value": v} for k, v in values.items()}


def sample_numbers():
    return {name: (0.5 if tol is not None else "x")
            for name, (_, tol) in check.TOLERANCES.items()}


def test_within_tolerance_passes():
    current = sample_numbers()
    expected = fake_expected(current)
    current["headline_dollarization_pct"] += 0.009      # inside ±0.01
    assert all(row[-1] for row in check.compare(current, expected))


def test_outside_tolerance_fails():
    current = sample_numbers()
    expected = fake_expected(current)
    current["headline_dollarization_pct"] += 0.02       # outside ±0.01
    rows = {row[0]: row[-1] for row in check.compare(current, expected)}
    assert rows["headline_dollarization_pct"] is False


def test_text_values_must_match_exactly():
    current = sample_numbers()
    expected = fake_expected(current)
    current["rule_latest_signal"] = "red"
    rows = {row[0]: row[-1] for row in check.compare(current, expected)}
    assert rows["rule_latest_signal"] is False


@pytest.mark.skipif(not (ROOT / "model/decision_rule.json").exists()
                    or not (ROOT / "docs/expected_numbers.json").exists(),
                    reason="run the pipeline first (run.bat build)")
def test_current_build_reproduces():
    assert check.main([]) == 0
