"""Tests for src/figures.py: every figure is written and is a real image."""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

NEEDED = ["data/processed/monthly.csv", "model/artifact.json",
          "model/feedback.json", "model/decision_rule.json",
          "outputs/holdout_forecast.csv", "outputs/feedback_irf.csv",
          "outputs/decision_signals.csv"]


@pytest.mark.skipif(not all((ROOT / p).exists() for p in NEEDED),
                    reason="run the pipeline first (run.bat build)")
def test_all_six_figures_are_written(monkeypatch):
    import figures
    monkeypatch.chdir(ROOT)
    figures.main()
    names = ["fig1_history", "fig2_constant_rate", "fig3_holdout",
             "fig4_diagnostics", "fig5_var_irf", "fig6_signals"]
    for name in names:
        path = ROOT / "outputs" / "figures" / f"{name}.png"
        assert path.exists()
        assert path.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
        assert path.stat().st_size > 20_000
