@echo off
REM ------------------------------------------------------------------------
REM One command: install, rebuild every number, check them, start the site.
REM
REM   run.bat          full run (install if needed, rebuild, check, site)
REM   run.bat build    rebuild and check only, do not start the site
REM   run.bat site     start the site only, from the files already built
REM
REM Uses the project's own Python environment in .venv (created on the
REM first run). It calls .venv\Scripts\python.exe directly, so PowerShell's
REM "activate" script is not needed.
REM ------------------------------------------------------------------------

chcp 65001 >nul
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
set PY=.venv\Scripts\python.exe

if not exist "%PY%" (
    echo [1/9] Creating the Python environment in .venv ...
    python -m venv .venv || goto :no_python
    "%PY%" -m pip install --upgrade pip >nul
    "%PY%" -m pip install -r requirements.txt || goto :failed
) else (
    echo [1/9] Python environment found in .venv
)

if /i "%1"=="site" goto :site

echo [2/9] Data: python src/ingest.py
"%PY%" src\ingest.py || goto :failed
echo [3/9] Model: python src/model.py
"%PY%" src\model.py || goto :failed
echo [4/9] Robustness checks (1-3 minutes): python src/robustness.py
"%PY%" src\robustness.py || goto :failed
echo [5/9] Feedback VAR: python src/feedback.py
"%PY%" src\feedback.py || goto :failed
echo [6/9] Decision rule: python src/decision_rule.py
"%PY%" src\decision_rule.py || goto :failed
echo [7/9] Report tables: python src/report_tables.py
"%PY%" src\report_tables.py || goto :failed
echo [8/9] Reproducibility check: python src/check.py
"%PY%" src\check.py || goto :failed

if /i "%1"=="build" (
    echo.
    echo Build finished. All numbers reproduce.
    goto :eof
)

:site
echo [9/9] Starting the website. Stop it with Ctrl+C.
"%PY%" -m streamlit run src\app.py
goto :eof

:no_python
echo.
echo Python was not found. Install Python 3.11 or newer from python.org
echo and tick "Add python.exe to PATH" during installation.
exit /b 1

:failed
echo.
echo The step above failed. Read the message above this line.
exit /b 1
