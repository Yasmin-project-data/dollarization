"""Tests for src/feedback.py (VAR: does dollarization move the tenge?) and
the website panel that shows it."""

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import feedback  # noqa: E402
import model  # noqa: E402

DATA = ROOT / "data/processed/monthly.csv"
needs_data = pytest.mark.skipif(not DATA.exists(),
                                reason="run python src/ingest.py first")


@needs_data
def test_var_data_is_complete_and_ordered():
    data = feedback.build_var_data(model.read_monthly())
    assert list(data.columns) == feedback.ORDER
    assert not data.isna().any().any()
    assert str(data.index[0]) == "2016-01"      # changes from 2015-12


@needs_data
def test_var_is_stable_and_residuals_white():
    result = feedback.fit_var(feedback.build_var_data(model.read_monthly()))
    assert result.is_stable()
    assert result.test_whiteness(nlags=12).pvalue > 0.05


@needs_data
def test_dollarization_shock_cannot_move_rate_in_same_month():
    """Cholesky order puts dollarization last, so month-0 response is zero."""
    result = feedback.fit_var(feedback.build_var_data(model.read_monthly()))
    irf = feedback.irf_table(result)
    assert irf.loc[0, "fx_response"] == pytest.approx(0.0, abs=1e-12)
    assert (irf["fx_lower"] <= irf["fx_response"] + 1e-9).all()
    assert (irf["fx_upper"] >= irf["fx_response"] - 1e-9).all()


def test_verdict():
    assert feedback.verdict(0.01) == "significant"
    assert feedback.verdict(0.30) == "not significant"


def test_panel_without_file_shows_notice(tmp_path):
    from streamlit.testing.v1 import AppTest

    def script(path):
        import sys
        sys.path.insert(0, "src")
        from feedback_panel import show_feedback_panel
        show_feedback_panel(path)

    at = AppTest.from_function(script, args=(str(tmp_path / "missing.json"),))
    at.run()
    assert not at.exception
    assert "python src/feedback.py" in at.warning[0].value


@pytest.mark.skipif(not (ROOT / "model/feedback.json").exists(),
                    reason="run python src/feedback.py first")
def test_feedback_file_matches_csv():
    saved = json.loads((ROOT / "model/feedback.json").read_text(encoding="utf-8"))
    assert saved["granger"]["dollarization_to_fx"] in ("significant",
                                                        "not significant")
    assert len(saved["irf"]["month"]) == feedback.HORIZON + 1
    assert {v["id"] for v in saved["variants"]} == {"V1", "V2", "V3", "V4"}
