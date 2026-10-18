"""
Self-check of the acceptance checks in the assignment guide (Section 11)
and the submission checklist (Annex C), as far as they can be automated.

    python src/acceptance.py

Each check prints PASS, FAIL or MANUAL. MANUAL checks need a person (a clean
machine, a stopwatch, a disconnected network); their step-by-step
instructions are in docs/acceptance_checks.md. The results are also written
to outputs/acceptance_report.md with the date and the machine name, to be
copied into the checklist.

Nothing in the project is changed: the "missing model" and "rebuild" checks
run on a temporary copy of the files.
"""

import json
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "src" / "app.py"
PRESENTATION = [APP] + sorted((ROOT / "src").glob("*_panel.py"))
MONTHLY = ROOT / "data" / "processed" / "monthly.csv"
ARTIFACT = ROOT / "model" / "artifact.json"
REPORT = ROOT / "outputs" / "acceptance_report.md"

SECRET_PATTERNS = [
    r"api[_-]?key\s*[=:]\s*['\"][A-Za-z0-9]{12,}",
    r"token\s*[=:]\s*['\"][A-Za-z0-9_\-]{12,}",
    r"password\s*[=:]\s*['\"][^'\"]{4,}",
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
    r"ghp_[A-Za-z0-9]{30,}",
    r"AKIA[0-9A-Z]{16}",
]
SKIP_DIRS = {".venv", ".git", "__pycache__", ".pytest_cache", "node_modules"}


def run_app(cwd=ROOT):
    from streamlit.testing.v1 import AppTest
    return AppTest.from_file(str(APP), default_timeout=60).run()


# ---------------------------------------------------------------------------
# Checks. Each returns (status, detail).
# ---------------------------------------------------------------------------

def check_3_headline():
    """Headline value, unit, reference period and latest change on top."""
    at = run_app()
    if at.exception:
        return "FAIL", f"the page raised an error: {at.exception[0].message}"
    head = at.metric[0]
    ok = (head.label.startswith("Dollarization, ") and head.value.endswith("%")
          and head.delta and "pp" in head.delta)
    detail = f"{head.label} = {head.value}, {head.delta}"
    return ("PASS" if ok else "FAIL"), detail


def check_4_speed():
    """Render time on cached data (headless proxy for the browser check)."""
    run_app()                                 # first run fills the cache
    start = time.perf_counter()
    run_app()
    seconds = time.perf_counter() - start
    status = "PASS" if seconds < 3 else "FAIL"
    return status, (f"{seconds:.2f} s to run the page script headless; "
                    "also time it in the browser (docs/acceptance_checks.md)")


def check_5_contributions():
    """Three driver contributions on screen equal the artifact."""
    artifact = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    at = run_app()
    table = at.dataframe[0].value
    shown = dict(zip(table["Driver"], table["Contribution, pp"]))
    labels = {f["name"]: f["label"] for f in artifact["factors"]}
    rows = []
    for name in list(labels)[:3]:
        saved = round(artifact["latest"]["contributions"][name], 2)
        rows.append((labels[name], saved, shown.get(labels[name])))
    ok = all(abs(saved - screen) < 0.005 for _, saved, screen in rows
             if screen is not None) and all(r[2] is not None for r in rows)
    detail = "; ".join(f"{l}: file {s:+.2f}, screen {v:+.2f}" for l, s, v in rows)
    return ("PASS" if ok else "FAIL"), detail


def check_6_scenario():
    """Moving the scenario slider changes the output and its band."""
    at = run_app()
    before = {m.label: m.value for m in at.metric}
    at.slider[0].set_value(at.slider[0].max).run()
    after = {m.label: m.value for m in at.metric}
    implied = [k for k in after if k.startswith("Implied")]
    band = "95% band (coefficient uncertainty)"
    ok = (implied and after[implied[0]] != before[implied[0]]
          and after[band] != before[band] and not at.exception)
    return ("PASS" if ok else "FAIL"), (
        f"{implied[0] if implied else 'output'}: {before.get(implied[0]) if implied else '?'}"
        f" -> {after.get(implied[0]) if implied else '?'}; band {before.get(band)} -> {after.get(band)}")


def check_7_cached_label():
    """The page says the data come from a cached snapshot."""
    at = run_app()
    text = " ".join(i.value for i in at.info)
    ok = "cached snapshot" in text
    return ("PASS" if ok else "FAIL"), (
        "label found; still disconnect the network and reload by hand"
        if ok else "no 'cached snapshot' label on the page")


def check_8_missing_model():
    """With the artifact missing the page explains it in plain language."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        shutil.copytree(ROOT / "data" / "processed", tmp / "data" / "processed")
        import os
        old = os.getcwd()
        os.chdir(tmp)
        try:
            at = run_app()
        finally:
            os.chdir(old)
    messages = [w.value for w in at.warning if "model/artifact.json" in w.value]
    ok = not at.exception and bool(messages) and bool(at.metric)
    return ("PASS" if ok else "FAIL"), (
        "shown: " + messages[0][:100] + "..." if messages
        else "no message about the missing model")


def check_9_no_literal():
    """The headline figure is not typed into the presentation layer."""
    monthly = pd.read_csv(MONTHLY).dropna(subset=["dollarization_pct"])
    value = float(monthly["dollarization_pct"].iloc[-1])
    literals = {f"{value:.1f}", f"{value:.2f}", f"{value:.4f}"}
    found = []
    for path in PRESENTATION:
        text = path.read_text(encoding="utf-8")
        for literal in literals:
            if re.search(rf"(?<![\d.]){re.escape(literal)}(?![\d])", text):
                found.append(f"{path.name}: {literal}")
    return ("FAIL", ", ".join(found)) if found else (
        "PASS", f"{', '.join(sorted(literals))} not found in "
                f"{', '.join(p.name for p in PRESENTATION)}")


def check_10_secrets():
    """No credentials in the files; history checked with git if available."""
    hits = []
    for path in ROOT.rglob("*"):
        if (not path.is_file() or SKIP_DIRS & set(path.parts)
                or path.suffix.lower() in {".xlsx", ".xls", ".png", ".pyc"}):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for pattern in SECRET_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                hits.append(path.relative_to(ROOT).as_posix())
                break
    history = "history: git not found, check on GitHub by hand"
    try:
        log = subprocess.run(["git", "log", "-p", "--all"], cwd=ROOT,
                             capture_output=True, text=True, encoding="utf-8",
                             errors="ignore", timeout=60)
        if log.returncode == 0:
            bad = [p for p in SECRET_PATTERNS
                   if re.search(p, log.stdout, re.IGNORECASE)]
            history = ("history: nothing found" if not bad
                       else "history: suspicious text found, check git log")
            if bad:
                hits.append("git history")
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    if hits:
        return "FAIL", "check: " + ", ".join(hits)
    return "PASS", f"files: nothing found; {history}"


def check_c4_rebuild():
    """Deleting data/processed and re-running ingest restores it exactly."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        for folder in ("data/raw", "src"):
            shutil.copytree(ROOT / folder, tmp / folder)
        result = subprocess.run([sys.executable, "src/ingest.py"], cwd=tmp,
                                capture_output=True, text=True)
        if result.returncode != 0:
            return "FAIL", "ingest.py failed on a clean copy"
        new = pd.read_csv(tmp / "data" / "processed" / "monthly.csv")
    old = pd.read_csv(MONTHLY)
    try:
        pd.testing.assert_frame_equal(old, new, check_exact=False, rtol=1e-9)
    except AssertionError as error:
        return "FAIL", f"monthly.csv differs: {str(error).splitlines()[0]}"
    return "PASS", f"monthly.csv rebuilt from data/raw: {len(new)} rows, identical"


CHECKS = [
    ("1", "Clean clone installs by following the README", None),
    ("2", "One command serves the site within ten minutes of the clone", None),
    ("3", "Headline value, unit, period and latest change without scrolling", check_3_headline),
    ("4", "Page renders in under three seconds on cached data", check_4_speed),
    ("5", "Three driver contributions match model/artifact.json", check_5_contributions),
    ("6", "Scenario control changes the output and its band", check_6_scenario),
    ("7", "Offline: loads from cache and says so", check_7_cached_label),
    ("8", "Missing artifact: plain-language message", check_8_missing_model),
    ("9", "Headline figure not typed into the presentation layer", check_9_no_literal),
    ("10", "No credentials or personal data in files or history", check_10_secrets),
    ("C4", "Deleting data/processed and re-running restores it exactly", check_c4_rebuild),
]
MANUAL_NOTE = {
    "1": "on the other laptop, from a fresh clone (docs/acceptance_checks.md)",
    "2": "time .\\run.bat from the clone (docs/acceptance_checks.md)",
}


def main():
    import warnings
    import logging
    warnings.simplefilter("ignore")
    logging.getLogger("streamlit").setLevel(logging.ERROR)
    rows = []
    for number, title, check in CHECKS:
        if check is None:
            status, detail = "MANUAL", MANUAL_NOTE[number]
        else:
            try:
                status, detail = check()
            except Exception as error:          # report, do not crash
                status, detail = "FAIL", f"{type(error).__name__}: {error}"
        rows.append((number, title, status, detail))
        print(f"{status:<6} {number:>3}. {title}\n           {detail}")

    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    machine = f"{platform.node()} ({platform.system()} {platform.release()}, Python {platform.python_version()})"
    lines = [
        "# Acceptance self-check (automated part)",
        "",
        f"Run: {stamp} on {machine}. Generated by `python src/acceptance.py`.",
        "",
        "| Check | Description | Result | Detail |",
        "|---|---|---|---|",
    ] + [f"| {n} | {t} | {s} | {d.replace('|', '/')} |" for n, t, s, d in rows]
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    failed = sum(r[2] == "FAIL" for r in rows)
    manual = sum(r[2] == "MANUAL" for r in rows)
    print(f"\n{len(rows) - failed - manual} passed, {failed} failed, "
          f"{manual} to do by hand -> {REPORT.relative_to(ROOT)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
