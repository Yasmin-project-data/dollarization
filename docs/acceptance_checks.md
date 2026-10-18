# Acceptance checks: self-check record

The ten acceptance checks of Section 11 of the assignment guide and the submission checklist (Annex C), with how we ran each one and the result. Fill in the **Result**, **Checked by** and **Date** columns as you go.

Two kinds of check:

- **Automated:** `python src/acceptance.py` runs checks 3-10 and C4 and writes `outputs/acceptance_report.md`. Copy its results here.
- **By hand:** checks 1, 2, 4 (in the browser) and 7 (with the network off) need a person. Steps are below.

"The other laptop" means the laptop of the team member who did not write the code being checked, starting from a fresh clone.

## Results

| Check | What the examiner does | How we checked | Result | Checked by | Date |
|---|---|---|---|---|---|
| 1 | Clone, follow the README, environment installs without repair | By hand, other laptop, steps A | PASS: no manual repair | Gulzat | 2026-10-18 |
| 2 | One command serves the site within 10 minutes of the clone | By hand, other laptop, steps A (stopwatch) | PASS: 1 min 23 s for run.bat, about 4.5 min from clone | Gulzat  | 2026-10-18 |
| 3 | Headline value, unit, period, latest change without scrolling | `acceptance.py` + look at the page | PASS (acceptance.py): 19.2%, August 2026, -0.09 pp | Yasmin | 2026-10-18 |
| 4 | Page renders in under 3 s on cached data | `acceptance.py` + browser, steps B | PASS: about 1 s in the browser, 0.5 s headless | Yasmin | 2026-10-18 |
| 5 | Three driver contributions match `model/artifact.json` | `acceptance.py` + steps C | PASS: -0.39, -0.58, +0.09 pp in the file and on scree | Yasmin | 2026-10-18 |
| 6 | Scenario control changes output and band coherently | `acceptance.py` + move the slider | PASS (acceptance.py) | Yasmin | 2026-10-18 |
| 7 | Network off: loads from cache and says so | By hand, steps D | PASS: page loads with Wi-Fi off and shows the cached-snapshot notice | Yasmin | 2026-10-18 |
| 8 | Artifact renamed: plain-language message | `acceptance.py` + steps E | PASS: plain-language notice, headline and history still shown | Yasmin | 2026-10-18 |
| 9 | Headline figure not a literal in the presentation layer | `acceptance.py` | PASS (acceptance.py) | Yasmin | 2026-10-18 |
| 10 | No credentials or personal data in files or history | `acceptance.py` + GitHub, steps F | PASS (acceptance.py): files and git history | Yasmin | 2026-10-18 |

## Submission checklist (Annex C)

| Item | Status | Evidence |
|---|---|---|
| C1 Indicator registered, approved, unchanged since Week 2 | done | `docs/indicator_card.md` |
| C2 Indicator card covers every row of Table 1 | done | `docs/indicator_card.md` |
| C3 `data/raw` untouched since download, `SOURCES.md` complete | done | GitHub history of `data/raw` |
| C4 Deleting `data/processed` and re-running restores it exactly | done | `acceptance.py` (check C4) |
| C5 `model/artifact.json` committed with coefficients, covariance, sample, timestamp, diagnostics, benchmark | done | `model/artifact.json` |
| C6 No regression call and no hard-coded headline in the presentation layer | done | `acceptance.py` (check 9) |
| C7 All ten checks pass on a machine that is not ours | done | Table above, "other laptop" |
| C8 Offline and missing-artifact paths show a clear message | done | Checks 7 and 8 |
| C9 Environment pinned, seeds fixed, tolerance stated | done | `requirements.txt`, `README.md` (Reproducibility and tolerance) |
| C10 Week 6 replication receipt from another team | to confirm with the instructor | No exchange between teams this term; to confirm with the instructor |

## Steps

### A. Fresh clone on the other laptop (checks 1 and 2)

1. Make sure the latest version is pushed to GitHub.
2. On the other laptop, in GitHub Desktop: **File → Clone repository → URL**, paste the repository address, choose an **empty** folder such as `C:\projects\clone_test`, click **Clone**.
3. Start a stopwatch.
4. Open the cloned folder in VS Code (**File → Open Folder**), open the terminal (**Ctrl+`**) and type `.\run.bat`.
5. Stop the stopwatch when the site opens in the browser. Write the time in the table. It must be under 10 minutes.
6. Check 1 passes if nothing had to be fixed by hand on the way. If something had to be fixed, write what.
7. Delete `C:\projects\clone_test` afterwards.

### B. Speed in the browser (check 4)

1. Start the site: `.\run.bat site`.
2. In the browser, press **F5** to reload and count how long until the headline numbers and charts are shown. Repeat three times; write the slowest.

### C. Contributions against the file (check 5)

1. Open `model/artifact.json` in VS Code and search (**Ctrl+F**) for `"contributions"`.
2. Compare three values (for example `depreciation_1m`, `rate_spread`, `inflation_yoy_pct`, rounded to two decimals) with the table under "What moved the indicator" on the page.

### D. Offline (check 7)

1. Start the site: `.\run.bat site`.
2. Turn off the internet: Wi-Fi icon at the bottom right of the screen → switch Wi-Fi off (or airplane mode).
3. In the browser press **F5**. The page must load and show "Data shown from the cached snapshot... The site does not download anything, so it works offline."
4. Turn the internet back on.

### E. Missing model (check 8)

1. Stop the site (**Ctrl+C** in the terminal).
2. In VS Code, in the `model` folder, right-click `artifact.json` → **Rename** → `artifact_backup.json`.
3. Start the site: `.\run.bat site`. The page must say in plain words that `model/artifact.json` is missing; the headline and history must still show.
4. Stop the site and **rename the file back to `artifact.json`**. Do not commit the renamed file.

### F. Credentials in the history (check 10)

1. `acceptance.py` searches every file and, if Git is installed, the full history.
2. If it says "git not found", open the repository on github.com, click **Commits**, and look through the commits that touched `src/download_*.py` and `data/raw/SOURCES.md` for keys, tokens or passwords. There should be none: the NBK API and FRED downloads need no key.
