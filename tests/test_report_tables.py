"""Tests for src/report_tables.py: the report must contain every section and
agree with the numbers the model layer saves."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import report_tables  # noqa: E402

DATA = Path("data/processed/monthly.csv")
ARTIFACT = Path("model/artifact.json")

needs_data = pytest.mark.skipif(not DATA.exists(),
                                reason="run python src/ingest.py first")


def test_stars():
    assert report_tables.stars(0.001) == "***"
    assert report_tables.stars(0.03) == "**"
    assert report_tables.stars(0.07) == "*"
    assert report_tables.stars(0.5) == ""


def test_md_table_shape():
    import pandas as pd
    text = report_tables.md_table(pd.DataFrame({"a": [1, 2], "b": [3, 4]}))
    lines = text.splitlines()
    assert lines[0] == "| a | b |"
    assert len(lines) == 4


@needs_data
def test_report_has_every_section():
    report = report_tables.build_report()
    for heading in ["## 1.", "## 2.", "## 3.", "## 4.", "## 5.", "## 6.",
                    "## 7.", "## 8.", "## 9.", "## 10.", "## Annex"]:
        assert heading in report
    for word in ["R²", "Breusch-Godfrey", "Breusch-Pagan", "Jarque-Bera",
                 "CUSUM", "Chow", "VIF", "ADF", "KPSS", "RMSE"]:
        assert word in report


@needs_data
@pytest.mark.skipif(not ARTIFACT.exists(), reason="run python src/model.py first")
def test_report_matches_artifact():
    artifact = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    fit = report_tables.estimate()
    saved = dict(zip(artifact["coefficients"]["names"],
                     artifact["coefficients"]["values"]))
    for name, value in fit["result"].params.items():
        assert value == pytest.approx(saved[name], rel=1e-6)
