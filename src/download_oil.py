"""
Download the monthly Brent crude oil price from FRED.

Series: POILBREUSDM - Global price of Brent Crude, U.S. Dollars per Barrel,
        monthly, not seasonally adjusted (source: IMF, via FRED).
URL:    https://fred.stlouisfed.org/graph/fredgraph.csv?id=POILBREUSDM
        (free, no API key)

Writes: data/raw/brent_fred.csv, exactly as FRED returns it.

Raw data are written once: if the file already exists, nothing is
downloaded. To refresh the data on purpose, run:
    python src/download_oil.py --refresh

Run from the project folder:
    python src/download_oil.py
"""

import sys
import urllib.request
from pathlib import Path

SERIES_ID = "POILBREUSDM"
URL = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={SERIES_ID}"
OUT_FILE = Path("data/raw/brent_fred.csv")


def download(url):
    """Return the CSV text from FRED."""
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read().decode("utf-8")


def check(text):
    """Make sure FRED returned a CSV with the series we asked for."""
    first_line = text.splitlines()[0] if text else ""
    if SERIES_ID not in first_line:
        raise ValueError(
            f"Unexpected answer from FRED (first line: {first_line[:80]!r})."
        )


def main():
    refresh = "--refresh" in sys.argv
    if OUT_FILE.exists() and not refresh:
        print(f"{OUT_FILE} already exists; nothing downloaded. "
              "Use --refresh to download again.")
        return

    text = download(URL)
    check(text)
    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(text, encoding="utf-8")

    lines = text.strip().splitlines()
    print(f"Saved {len(lines) - 1} months to {OUT_FILE}")
    print(f"First: {lines[1]}")
    print(f"Last:  {lines[-1]}")


if __name__ == "__main__":
    main()
