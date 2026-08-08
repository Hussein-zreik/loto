"""
Lebanese LOTO archive scraper
------------------------------
Backfills data.json with LOTO 6/42 draws from a start month through an end month,
pulled from yelleb.com's "Past Results" page (https://www.yelleb.com/lottery/results/history).

WHY SELENIUM: the month/game filters on that page are client-side (JS-driven) --
a plain requests.get() returns the same recent draws regardless of query params, so a
real browser is needed to select the dropdown and read the re-rendered table. (This is
also why the scraper only runs on a real computer, not on a phone.)

SETUP (run once):
    pip install selenium webdriver-manager beautifulsoup4

    You also need Google Chrome (or Chromium) installed. selenium 4.6+ ships Selenium
    Manager, which auto-fetches a matching chromedriver; webdriver-manager is used only
    as a fallback if that ever fails.

USAGE:
    python scrape_loto.py                       # scrapes 2020-03 -> current month (the gap)
    python scrape_loto.py --start 2020-03 --end 2026-08
    python scrape_loto.py --skip-existing       # skip months already present in data.json
    python scrape_loto.py --no-headless         # watch the browser (useful for debugging)
    python scrape_loto.py --dry-run             # scrape but DON'T write data.json

MERGE BEHAVIOR:
    Existing draws in data.json are PRESERVED (your verified recent draws win); only
    dates not already present are added. Use --overwrite to let scraped rows replace
    existing ones on the same date.

IF IT COMES BACK EMPTY:
    The dropdown selectors are best-effort. Run with --no-headless to watch what happens,
    and if the month/game <select> elements aren't found, open the page in Chrome, inspect
    them, and set --month-select / --game-select to the real name or id. The script also
    auto-scans every <select> on the page and picks the one whose options look like months
    (YYYY-MM) or game names, so it often works without any tuning.
"""

import argparse
import json
import re
import sys
import time
from datetime import date
from pathlib import Path

try:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import Select, WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.common.exceptions import NoSuchElementException, TimeoutException
    SELENIUM_OK = True
except ImportError:
    # Don't exit here — let --help still work. We check SELENIUM_OK in main().
    SELENIUM_OK = False

HISTORY_URL = "https://www.yelleb.com/lottery/results/history"
OUTPUT_FILE = Path(__file__).parent / "data.json"

# Row text looks like: "06 Aug 2026, Thu   Loto Libanais   3 7 8 11 36 40 + 4"
DATE_RE = re.compile(r"(\d{1,2})\s+([A-Za-z]{3})\s+(\d{4})")
MONTHS = {
    "Jan": "01", "Feb": "02", "Mar": "03", "Apr": "04", "May": "05", "Jun": "06",
    "Jul": "07", "Aug": "08", "Sep": "09", "Oct": "10", "Nov": "11", "Dec": "12",
}
DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def log(msg):
    print(msg, flush=True)


def month_range(start_yyyymm, end_yyyymm):
    """Yield 'YYYY-MM' strings from start through end (inclusive)."""
    y, m = int(start_yyyymm[:4]), int(start_yyyymm[5:7])
    ey, em = int(end_yyyymm[:4]), int(end_yyyymm[5:7])
    while (y, m) <= (ey, em):
        yield f"{y:04d}-{m:02d}"
        m += 1
        if m > 12:
            m, y = 1, y + 1


def parse_row_text(text):
    """
    Parse a results row into {date, day, numbers[6], bonus}, or None if it's not a
    valid Loto row. Works purely off the row's visible text, so it's resilient to
    markup changes. Only accepts rows explicitly tagged 'Loto' to avoid picking up
    Yawmiyeh/Zeed draws.
    """
    if "Loto" not in text and "loto" not in text:
        return None
    m = DATE_RE.search(text)
    if not m:
        return None
    dd, mon, yyyy = m.groups()
    mm = MONTHS.get(mon.title())
    if not mm:
        return None
    iso_date = f"{yyyy}-{mm}-{int(dd):02d}"

    # Numbers after the date. First 6 in 1..42 are the main draw, the next is the bonus.
    tail = text[m.end():]
    nums = [int(n) for n in re.findall(r"\b\d{1,2}\b", tail)]
    nums = [n for n in nums if 1 <= n <= 42]
    if len(nums) < 7:
        return None
    main_numbers, bonus = nums[:6], nums[6]

    # Prefer a day name printed in the row; else derive it from the date.
    day = next((d for d in DAY_NAMES if d in text[:m.end() + 6]), None)
    if not day:
        try:
            day = DAY_NAMES[date(int(yyyy), int(mm), int(dd)).weekday()]
        except ValueError:
            day = ""

    return {"date": iso_date, "day": day, "numbers": main_numbers, "bonus": bonus}


def find_select(driver, preferred_name, kind):
    """
    Locate a <select>. Tries the preferred name/id first, then scans every <select>
    and returns the first whose options look like the target ('month' -> YYYY-MM
    values, 'game' -> option text mentioning Loto).
    """
    if preferred_name:
        for how in (By.NAME, By.ID):
            try:
                return Select(driver.find_element(how, preferred_name))
            except NoSuchElementException:
                pass

    for el in driver.find_elements(By.TAG_NAME, "select"):
        try:
            sel = Select(el)
            values = [(o.get_attribute("value") or "") for o in sel.options]
            texts = [(o.text or "") for o in sel.options]
            if kind == "month" and any(re.fullmatch(r"\d{4}-\d{2}", v) for v in values):
                return sel
            if kind == "game" and any("loto" in t.lower() for t in texts):
                return sel
        except Exception:
            continue
    return None


def scrape_month(driver, yyyymm, month_select_name, game_select_name, wait_secs):
    driver.get(HISTORY_URL)
    wait = WebDriverWait(driver, wait_secs)
    try:
        wait.until(EC.presence_of_element_located((By.TAG_NAME, "select")))
    except TimeoutException:
        log(f"  ! {yyyymm}: no <select> appeared within {wait_secs}s")
        return []

    game_sel = find_select(driver, game_select_name, "game")
    if game_sel:
        for label in ("Loto", "Loto Libanais", "LOTO"):
            try:
                game_sel.select_by_visible_text(label)
                break
            except Exception:
                continue

    month_sel = find_select(driver, month_select_name, "month")
    if not month_sel:
        log(f"  ! {yyyymm}: couldn't find the month dropdown (try --no-headless to inspect)")
        return []
    try:
        month_sel.select_by_value(yyyymm)
    except Exception:
        # Some sites label months as "August 2026" rather than "2026-08".
        y, mth = yyyymm.split("-")
        label = f"{list(MONTHS.keys())[int(mth) - 1]}"  # short month name
        matched = False
        for opt in month_sel.options:
            if y in opt.text and (label in opt.text or f"-{mth}" in (opt.get_attribute("value") or "")):
                opt.click()
                matched = True
                break
        if not matched:
            log(f"  ! {yyyymm}: no matching month option")
            return []

    time.sleep(1.5)  # let the AJAX table re-render

    draws, seen = [], set()
    for row in driver.find_elements(By.CSS_SELECTOR, "table tr, tr"):
        parsed = parse_row_text(row.text or "")
        if parsed and parsed["date"] not in seen:
            # Keep only draws that actually fall in the requested month.
            if parsed["date"].startswith(yyyymm):
                draws.append(parsed)
                seen.add(parsed["date"])
    return draws


def load_existing():
    if not OUTPUT_FILE.exists():
        return {}, {}
    try:
        data = json.loads(OUTPUT_FILE.read_text())
    except Exception:
        return {}, {}
    by_date = {d["date"]: d for d in data.get("draws", [])}
    return by_date, data.get("meta", {})


def build_driver(headless):
    options = webdriver.ChromeOptions()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1280,1600")
    try:
        return webdriver.Chrome(options=options)  # Selenium Manager handles the driver
    except Exception as e:
        log(f"Selenium Manager failed ({e}); falling back to webdriver-manager...")
        from selenium.webdriver.chrome.service import Service
        from webdriver_manager.chrome import ChromeDriverManager
        return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)


def main():
    ap = argparse.ArgumentParser(description="Backfill data.json with Lebanese LOTO draws.")
    ap.add_argument("--start", default="2020-03", help="YYYY-MM to start from (default: 2020-03, the gap start)")
    ap.add_argument("--end", default=date.today().strftime("%Y-%m"), help="YYYY-MM to end at (default: current month)")
    ap.add_argument("--month-select", default="month", help="name/id of the month <select> (auto-detected if wrong)")
    ap.add_argument("--game-select", default="game", help="name/id of the game <select> (auto-detected if wrong)")
    ap.add_argument("--wait", type=int, default=15, help="seconds to wait for page elements")
    ap.add_argument("--retries", type=int, default=2, help="retries per month on error")
    ap.add_argument("--skip-existing", action="store_true", help="skip months that already have draws in data.json")
    ap.add_argument("--overwrite", action="store_true", help="let scraped rows replace existing same-date draws")
    ap.add_argument("--no-headless", dest="headless", action="store_false", help="show the browser window")
    ap.add_argument("--dry-run", action="store_true", help="scrape but don't write data.json")
    ap.set_defaults(headless=True)
    args = ap.parse_args()

    if not SELENIUM_OK:
        sys.exit(
            "Selenium isn't installed. Run:\n"
            "    pip install selenium webdriver-manager beautifulsoup4"
        )

    if not re.fullmatch(r"\d{4}-\d{2}", args.start) or not re.fullmatch(r"\d{4}-\d{2}", args.end):
        sys.exit("--start and --end must be YYYY-MM (e.g. 2020-03)")

    existing, meta = load_existing()
    existing_months = {d[:7] for d in existing}
    log(f"Loaded {len(existing)} existing draws from {OUTPUT_FILE.name}"
        if existing else f"No existing {OUTPUT_FILE.name}; starting fresh.")

    driver = build_driver(args.headless)
    scraped = {}
    try:
        for yyyymm in month_range(args.start, args.end):
            if args.skip_existing and yyyymm in existing_months:
                log(f"{yyyymm}: skipped (already in data.json)")
                continue
            draws = []
            for attempt in range(1, args.retries + 2):
                try:
                    draws = scrape_month(driver, yyyymm, args.month_select, args.game_select, args.wait)
                    break
                except Exception as e:
                    log(f"  ! {yyyymm}: error on attempt {attempt}: {e}")
                    time.sleep(2 * attempt)
            for d in draws:
                scraped[d["date"]] = d
            log(f"{yyyymm}: {len(draws)} draw(s)")
    except KeyboardInterrupt:
        log("\nInterrupted — writing whatever was scraped so far...")
    finally:
        driver.quit()

    # Merge: existing wins unless --overwrite.
    added, updated = 0, 0
    for dt, d in scraped.items():
        if dt not in existing:
            existing[dt] = d
            added += 1
        elif args.overwrite:
            existing[dt] = d
            updated += 1

    merged = sorted(existing.values(), key=lambda d: d["date"], reverse=True)
    log(f"\nScraped {len(scraped)} row(s) across the range.")
    log(f"Added {added} new draw(s)" + (f", updated {updated}" if args.overwrite else "") + ".")
    log(f"data.json would now hold {len(merged)} draws "
        f"({merged[-1]['date']} .. {merged[0]['date']})." if merged else "No draws.")

    if args.dry_run:
        log("--dry-run: not writing data.json.")
        return

    output = {
        "meta": {
            "game": "Lebanese LOTO 6/42",
            "source": (meta.get("source") or "yelleb.com (unofficial archive)") + " + scrape backfill",
            "lastUpdated": date.today().isoformat(),
            "note": f"Backfilled {args.start}..{args.end} from yelleb.com on {date.today().isoformat()}.",
            "totalDraws": len(merged),
        },
        "draws": merged,
    }
    OUTPUT_FILE.write_text(json.dumps(output, indent=2))
    log(f"Wrote {len(merged)} draws to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
