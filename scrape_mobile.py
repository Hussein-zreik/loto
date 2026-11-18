"""
Lebanese LOTO — phone-friendly catch-up scraper
------------------------------------------------
Fetches recent LOTO draws WITHOUT a browser. No Selenium, no Chrome, and no
third-party packages — Python's standard library only — so it runs on a phone.

WHY THIS WORKS WITHOUT A BROWSER
    yelleb.com's filter is an ordinary HTML form submitted by POST:
        data[Lottery][name] = Loto
        data[Lottery][date] = YYYY-MM
    URL query parameters are ignored (that was verified), but a real POST is
    exactly what the browser sends when you press "Search Numbers". This script
    does that directly. It first GETs the page to collect cookies and any hidden
    form fields (CakePHP CSRF tokens), then POSTs them back.

WHERE TO RUN IT
    iPhone/iPad : a-Shell (free, App Store) — or Pythonista / Pyto
    Android     : Termux (pkg install python) — or Pydroid 3
    Laptop      : works there too (python3 scrape_mobile.py)

USAGE
    python3 scrape_mobile.py                 # catch up since the newest known draw
    python3 scrape_mobile.py --months 4      # last 4 months regardless
    python3 scrape_mobile.py --start 2026-08 --end 2026-11
    python3 scrape_mobile.py --diagnose      # show what the site returned, for debugging

OUTPUT
    Prints any NEW draws as a copy-paste block. Paste that back to Claude and it
    will merge, validate and publish them. If data.json is in the same folder it
    is merged locally too.
"""

import argparse
import json
import re
import sys
import urllib.parse
import urllib.request
import http.cookiejar
from datetime import date

HISTORY_URL = "https://www.yelleb.com/lottery/results/history"
RAW_DATA_URL = "https://raw.githubusercontent.com/Hussein-zreik/loto/main/data.json"
UA = "Mozilla/5.0 (compatible; loto-archive-script)"

MONTHS = {m: f"{i+1:02d}" for i, m in enumerate(
    ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"])}
DAY_NAMES = ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"]
DATE_RE = re.compile(r"(\d{1,2})\s+([A-Za-z]{3})\s+(\d{4})")


def opener():
    jar = http.cookiejar.CookieJar()
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    op.addheaders = [("User-Agent", UA),
                     ("Accept", "text/html,application/xhtml+xml"),
                     ("Referer", HISTORY_URL)]
    return op


def strip_tags(html):
    html = re.sub(r"(?is)<(script|style).*?</\1>", " ", html)
    html = re.sub(r"<[^>]+>", " ", html)
    html = (html.replace("&nbsp;", " ").replace("&amp;", "&")
                .replace("&lt;", "<").replace("&gt;", ">").replace("&#43;", "+"))
    return re.sub(r"\s+", " ", html).strip()


def hidden_fields(html):
    """Collect every hidden input so CSRF tokens survive the round trip."""
    out = {}
    for tag in re.findall(r"(?is)<input[^>]*>", html):
        if not re.search(r'type\s*=\s*["\']?hidden', tag, re.I):
            continue
        n = re.search(r'name\s*=\s*"([^"]*)"', tag) or re.search(r"name\s*=\s*'([^']*)'", tag)
        v = re.search(r'value\s*=\s*"([^"]*)"', tag) or re.search(r"value\s*=\s*'([^']*)'", tag)
        if n:
            out[n.group(1)] = v.group(1) if v else ""
    return out


def parse_rows(html):
    """Pull Loto draws out of the results table, row by row."""
    draws, seen = [], set()
    for chunk in re.split(r"(?i)<tr[\s>]", html)[1:]:
        text = strip_tags(chunk)
        if "Loto" not in text:
            continue
        m = DATE_RE.search(text)
        if not m:
            continue
        dd, mon, yyyy = m.groups()
        mm = MONTHS.get(mon.title())
        if not mm:
            continue
        iso = f"{yyyy}-{mm}-{int(dd):02d}"
        nums = [int(n) for n in re.findall(r"\b\d{1,2}\b", text[m.end():])]
        nums = [n for n in nums if 1 <= n <= 42]
        if len(nums) < 7 or iso in seen:
            continue
        day = next((d for d in DAY_NAMES if d in text[:m.end() + 6]), "")
        if not day:
            try:
                day = DAY_NAMES[date(int(yyyy), int(mm), int(dd)).weekday()]
            except ValueError:
                day = ""
        draws.append({"date": iso, "day": day, "numbers": nums[:6], "bonus": nums[6]})
        seen.add(iso)
    return draws


def fetch_month(op, yyyymm, diagnose=False):
    html = op.open(HISTORY_URL, timeout=30).read().decode("utf-8", "replace")
    fields = hidden_fields(html)
    fields["data[Lottery][name]"] = "Loto"
    fields["data[Lottery][date]"] = yyyymm
    body = urllib.parse.urlencode(fields).encode()
    req = urllib.request.Request(HISTORY_URL, data=body,
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
    page = op.open(req, timeout=30).read().decode("utf-8", "replace")
    rows = parse_rows(page)
    if diagnose:
        print(f"\n--- DIAGNOSE {yyyymm} ---")
        print(f"hidden fields posted: {list(fields)}")
        print(f"rows parsed: {len(rows)}")
        for r in rows[:5]:
            print("   ", r)
        if not rows:
            print("first 400 chars of page text:")
            print("   ", strip_tags(page)[:400])
    return [d for d in rows if d["date"].startswith(yyyymm)]


def month_range(start, end):
    y, m = int(start[:4]), int(start[5:7])
    ey, em = int(end[:4]), int(end[5:7])
    while (y, m) <= (ey, em):
        yield f"{y:04d}-{m:02d}"
        m += 1
        if m > 12:
            m, y = 1, y + 1


def newest_known():
    """Latest draw date: local data.json if present, else the published copy."""
    try:
        with open("data.json") as fh:
            return max(d["date"] for d in json.load(fh)["draws"]), "data.json"
    except Exception:
        pass
    try:
        op = opener()
        data = json.loads(op.open(RAW_DATA_URL, timeout=30).read().decode())
        return max(d["date"] for d in data["draws"]), "github"
    except Exception as e:
        print(f"Couldn't read any existing data ({e}); defaulting to the last 4 months.")
        return None, None


def main():
    ap = argparse.ArgumentParser(description="Phone-friendly LOTO catch-up (no browser needed).")
    ap.add_argument("--start", help="YYYY-MM")
    ap.add_argument("--end", default=date.today().strftime("%Y-%m"), help="YYYY-MM")
    ap.add_argument("--months", type=int, help="just scrape the last N months")
    ap.add_argument("--diagnose", action="store_true", help="print what the site returned")
    a = ap.parse_args()

    known, src = newest_known()
    if a.start:
        start = a.start
    elif a.months:
        y, m = date.today().year, date.today().month - a.months + 1
        while m <= 0:
            m += 12; y -= 1
        start = f"{y:04d}-{m:02d}"
    elif known:
        start = known[:7]
        print(f"Newest draw on record: {known} (from {src}). Catching up from {start}.")
    else:
        y, m = date.today().year, date.today().month - 3
        while m <= 0:
            m += 12; y -= 1
        start = f"{y:04d}-{m:02d}"

    op = opener()
    found = {}
    for ym in month_range(start, a.end):
        try:
            rows = fetch_month(op, ym, a.diagnose)
        except Exception as e:
            print(f"{ym}: FAILED ({e})")
            continue
        for r in rows:
            found[r["date"]] = r
        print(f"{ym}: {len(rows)} draw(s)")

    if not found:
        print("\nNothing came back. Run again with --diagnose and send Claude the output.")
        return

    new = sorted(found.values(), key=lambda d: d["date"])
    if known:
        new = [d for d in new if d["date"] > known]

    if not new:
        print(f"\nAlready up to date — nothing newer than {known}.")
        return

    print(f"\n{len(new)} NEW draw(s) since {known or 'the start of the range'}:\n")
    for d in new:
        print(f"  {d['date']}  {d['day']}  {' '.join(f'{n:2d}' for n in d['numbers'])}  + {d['bonus']}")

    print("\n" + "=" * 58)
    print("COPY EVERYTHING BELOW AND PASTE IT TO CLAUDE")
    print("=" * 58)
    print(json.dumps(new, separators=(",", ":")))
    print("=" * 58)

    try:
        with open("data.json") as fh:
            data = json.load(fh)
        by_date = {d["date"]: d for d in data["draws"]}
        for d in new:
            by_date.setdefault(d["date"], d)
        data["draws"] = sorted(by_date.values(), key=lambda d: d["date"], reverse=True)
        data.setdefault("meta", {})["lastUpdated"] = date.today().isoformat()
        data["meta"]["totalDraws"] = len(data["draws"])
        with open("data.json", "w") as fh:
            json.dump(data, fh, indent=2)
        print(f"\nAlso merged into local data.json — now {len(data['draws'])} draws.")
    except FileNotFoundError:
        print("\n(No local data.json here — just paste the block above to Claude.)")


if __name__ == "__main__":
    main()
