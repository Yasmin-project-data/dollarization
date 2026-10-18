"""Tests for src/acceptance.py: the automated acceptance checks run and
report a status for every check."""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import acceptance  # noqa: E402

needs_build = pytest.mark.skipif(
    not (ROOT / "model/artifact.json").exists()
    or not (ROOT / "data/processed/monthly.csv").exists(),
    reason="run the pipeline first (run.bat build)")


def test_every_check_is_listed_once():
    numbers = [c[0] for c in acceptance.CHECKS]
    assert numbers == [str(i) for i in range(1, 11)] + ["C4"]


@needs_build
def test_no_headline_literal_in_presentation_layer():
    status, _ = acceptance.check_9_no_literal()
    assert status == "PASS"


def test_secret_patterns_catch_a_key(tmp_path):
    import re
    text = "api_" + 'key = "' + "a" * 16 + '"'
    assert any(re.search(p, text, re.IGNORECASE) for p in acceptance.SECRET_PATTERNS)
