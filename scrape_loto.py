"""
Lebanese LOTO archive scraper
------------------------------
Backfills data.json with every LOTO draw from a start month to the current month,
pulled from yelleb.com's "Past Results" page (https://www.yelleb.com/lottery/results/history).

WHY SELENIUM: the month/game filters on that page are client-side (JS-driven) --
a plain requests.get() always returns the same "last 30 draws" regardless of query
params, so a real browser is needed to select the dropdown and read the re-rendered table.

SETUP (run once):
    pip install selenium webdriver-manager beautifulsoup4

    You'll also need Google Chrome installed. webdriver-manager will fetch a matching
    chromedriver automatically the first time you run this.

USAGE:
    python scrape_loto.py                # scrapes 2021-01 through the current month
    python scrape_loto.py --start 2023-01 # scrape from a specific month instead

NOTE ON SELECTORS:
    The dropdown/element selectors below (MONTH_SELECT_NAME, GAME_SELECT_NAME) are
    best-effort based on the page's visible structure. If the script can't find them,
    open the page in Chrome, right-click the "Date by Month" dropdown -> Inspect, and
    update the SELECT_* constants below to match the real `name` or `id` attribute.
"""

import argparse
import json
import re
import time
from datetime import date
from pathlib import Path

from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select, WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

HISTORY_URL = "https://www.yelleb.com/lottery/results/history"
OUTPUT_FILE = Path(__file__).parent / "data.json"

# --- Adjust these if the site's markup differs from what's assumed here ---
MONTH_SELECT_NAME = "month"   # <select> for "Date by Month"
GAME_SELECT_NAME = "game"     # <select> for "Lottery name" (All/Loto/Zeed/Yawmiyeh)
GAME_OPTION_VALUE = "Loto"
ROW_SELECTOR = "table tr"     # each result row
# ---------------------------------------------------------------------------

DATE_RE = re.compile(r"(\d{2}) (\w{3}) (\d{4})")
MONTHS = {
    "Jan": "01", "Feb": "02", "Mar": "03", "Apr": "04", "May": "05", "Jun": "06",
    "Jul": "07", "Aug": "08", "Sep": "09", "Oct": "10", "Nov": "11", "Dec": "12",
}


def month_range(start_yyyymm: str):
    """Yield 'YYYY-MM' strings from start month through the current month."""
    y, m = int(start_yyyymm[:4]), int(start_yyyymm[5:7])
    today = date.today()
    while (y, m) <= (today.year, today.month):
        yield f"{y:04d}-{m:02d}"
        m += 1
        if m > 12:
            m = 1
            y += 1


def parse_row_text(text: str):
    """
    Parse a row like:
    '06 Aug 2026, Thu   Loto Libanais   3  7  8  11  36  40  +  4'
    into a draw dict, or return None if it's not a Loto row.
    """
    if "Loto" not in text:
        return None
    m = DATE_RE.search(text)
    if not m:
        return None
    dd, mon, yyyy = m.groups()
    mm = MONTHS.get(mon)
    if not mm:
        return None
    iso_date = f"{yyyy}-{mm}-{dd}"

    # Pull all the standalone numbers in the row (after the date), then split
    # into main numbers (first 6) and bonus (the one after a "+")
    nums = [int(n) for n in re.findall(r"\b\d{1,2}\b", text[m.end():])]
    if len(nums) < 7:
        return None
    main_numbers, bonus = nums[:6], nums[6]

    day_name = text[m.start():m.end() + 5].split(",")[-1].strip()[:3]

    return {"date": iso_date, "day": day_name, "numbers": main_numbers, "bonus": bonus}


def scrape_month(driver, yyyymm: str):
    driver.get(HISTORY_URL)
    wait = WebDriverWait(driver, 15)

    # Select the game filter -> Loto
    try:
        game_select = Select(wait.until(EC.presence_of_element_located((By.NAME, GAME_SELECT_NAME))))
        game_select.select_by_visible_text("Loto")
    except Exception:
        pass  # if this fails, we just filter Loto rows manually below

    # Select the target month
    try:
        month_select = Select(wait.until(EC.presence_of_element_located((By.NAME, MONTH_SELECT_NAME))))
        month_select.select_by_value(yyyymm)
    except Exception as e:
        print(f"  ! couldn't select month {yyyymm}: {e}")
        return []

    time.sleep(1.5)  # let the AJAX table re-render

    soup = BeautifulSoup(driver.page_source, "html.parser")
    draws = []
    for row in soup.select(ROW_SELECTOR):
        parsed = parse_row_text(row.get_text(" ", strip=True))
        if parsed:
            draws.append(parsed)
    return draws


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2021-01", help="YYYY-MM to start from")
    ap.add_argument("--headless", action="store_true", default=True)
    args = ap.parse_args()

    options = webdriver.ChromeOptions()
    if args.headless:
        options.add_argument("--headless=new")
    options.add_argument("--window-size=1280,1600")

    driver = webdriver.Chrome(options=options)

    all_draws = {}
    try:
        for yyyymm in month_range(args.start):
            print(f"Scraping {yyyymm} ...")
            draws = scrape_month(driver, yyyymm)
            for d in draws:
                all_draws[d["date"]] = d  # de-dupe by date
            print(f"  -> {len(draws)} draws found")
    finally:
        driver.quit()

    sorted_draws = sorted(all_draws.values(), key=lambda d: d["date"], reverse=True)

    output = {
        "meta": {
            "game": "Lebanese LOTO 6/42",
            "source": "yelleb.com (unofficial archive)",
            "lastUpdated": date.today().isoformat(),
            "note": f"Scraped {args.start} through {date.today().strftime('%Y-%m')}",
        },
        "draws": sorted_draws,
    }

    OUTPUT_FILE.write_text(json.dumps(output, indent=2))
    print(f"\nWrote {len(sorted_draws)} draws to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
