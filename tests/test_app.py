"""Tests of the website, run headless with Streamlit's AppTest.

These cover the acceptance checks that can be automated: the page renders
without an exception, shows the headline, reacts to the scenario control,
and reports a missing model in plain language.

Run from the project folder:
    python -m pytest
"""

import json
import shutil
from pathlib import Path

from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
APP = str(ROOT / "src" / "app.py")


def run_app(timeout=60):
    return AppTest.from_file(APP, default_timeout=timeout).run()


def test_page_renders_without_exception():
    at = run_app()
    assert not at.exception


def test_headline_matches_the_data():
    at = run_app()
    headline = at.metric[0]
    assert headline.label.startswith("Dollarization, ")
    latest = [line for line in
              (ROOT / "data/processed/monthly.csv").read_text().splitlines()
              if line][-1].split(",")
    columns = (ROOT / "data/processed/monthly.csv").read_text().splitlines()[0].split(",")
    value = float(latest[columns.index("dollarization_pct")])
    assert headline.value == f"{value:.1f}%"


def test_driver_contributions_on_screen_match_the_artifact():
    at = run_app()
    artifact = json.loads((ROOT / "model/artifact.json").read_text(encoding="utf-8"))
    text = " ".join(m.value for m in at.markdown) + " ".join(
        c.value for c in at.caption)
    assert f"{artifact['latest']['change']:+.2f} pp" in text


def test_scenario_slider_changes_output_and_band():
    at = run_app()
    before = {m.label: m.value for m in at.metric}
    at.slider[0].set_value(6.0).run()
    after = {m.label: m.value for m in at.metric}
    assert not at.exception
    scenario_value = [v for k, v in after.items() if k.startswith("Implied")][0]
    scenario_before = [v for k, v in before.items() if k.startswith("Implied")][0]
    assert scenario_value != scenario_before
    assert after["95% band (coefficient uncertainty)"] != \
        before["95% band (coefficient uncertainty)"]


def test_missing_artifact_gives_plain_message(tmp_path, monkeypatch):
    (tmp_path / "data" / "processed").mkdir(parents=True)
    for name in ("monthly.csv", "metadata.json"):
        shutil.copy(ROOT / "data" / "processed" / name,
                    tmp_path / "data" / "processed" / name)
    monkeypatch.chdir(tmp_path)
    at = run_app()
    assert not at.exception
    assert any("missing or could not be read" in w.value for w in at.warning)
    assert at.metric  # the data panels still work


def test_missing_data_gives_plain_message(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    at = run_app()
    assert not at.exception
    assert any("not found or could not be read" in e.value for e in at.error)
