"""
Download daily official USD/KZT exchange rates from the NBK public API.

API: https://nationalbank.kz/rss/get_rates.cfm?fdate=DD.MM.YYYY
     (free, no key; returns all official rates for one date as XML)

Writes: data/raw/usd_kzt_daily_nbk_api.csv
        columns: date, usd_kzt, quant

This file is raw data: it is written once and never edited by hand.
If the download is interrupted, run the script again: it continues
from where it stopped and does not download the same day twice.

Run from the project folder:
    python src/download_rates.py
"""

import csv
import time
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, timedelta
from pathlib import Path

API_URL = "https://nationalbank.kz/rss/get_rates.cfm?fdate={day}"
OUT_FILE = Path("data/raw/usd_kzt_daily_nbk_api.csv")
START = date(2010, 1, 1)
END = date(2026, 9, 30)
CURRENCY = "USD"
PAUSE_SECONDS = 0.1   # be polite to the NBK server
MAX_TRIES = 3


def all_days(start, end):
    """Every calendar day from start to end, inclusive."""
    day = start
    while day <= end:
        yield day
        day += timedelta(days=1)


def already_downloaded(path):
    """Dates already saved in the output file (so we can resume)."""
    if not path.exists():
        return set()
    with open(path, newline="", encoding="utf-8") as f:
        return {row["date"] for row in csv.DictReader(f)}


def fetch_xml(day):
    """Download the XML for one date, retrying a few times on errors."""
    url = API_URL.format(day=day.strftime("%d.%m.%Y"))
    for attempt in range(1, MAX_TRIES + 1):
        try:
            with urllib.request.urlopen(url, timeout=30) as response:
                return response.read()
        except Exception as error:
            if attempt == MAX_TRIES:
                raise RuntimeError(f"Could not download {url}: {error}")
            time.sleep(2 * attempt)


def parse_rate(xml_bytes, currency=CURRENCY):
    """Find one currency in the NBK XML and return (rate, quant)."""
    root = ET.fromstring(xml_bytes)
    for item in root.iter("item"):
        if item.findtext("title", "").strip() == currency:
            rate = float(item.findtext("description").strip())
            quant = int(item.findtext("quant", "1").strip())
            return rate, quant
    return None, None


def main():
    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    done = already_downloaded(OUT_FILE)
    todo = [d for d in all_days(START, END) if d.isoformat() not in done]

    if not todo:
        print(f"Nothing to do: {OUT_FILE} already covers {START} to {END}.")
        return

    print(f"Downloading {len(todo)} days ({len(done)} already saved)...")
    new_file = not OUT_FILE.exists()
    with open(OUT_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if new_file:
            writer.writerow(["date", "usd_kzt", "quant"])
        for i, day in enumerate(todo, start=1):
            rate, quant = parse_rate(fetch_xml(day))
            if rate is None:
                print(f"  {day}: no {CURRENCY} rate published, skipped")
            else:
                writer.writerow([day.isoformat(), rate, quant])
            if i % 100 == 0:
                f.flush()
                print(f"  {i}/{len(todo)} done (last: {day}, {rate})")
            time.sleep(PAUSE_SECONDS)

    print(f"Finished. Saved to {OUT_FILE}")


if __name__ == "__main__":
    main()
