# Lebanese LOTO Archive — Setup Notes

## Files
- `index.html` — the app (calendar range picker, results table, hot/cold + frequency stats, manual draw entry)
- `data.json` — **1,811 real draws**, draw #1 (2002-09-12) through 2020-03-12, sourced from
  a user-provided historical CSV, plus 10 verified recent draws (6 Jul – 6 Aug 2026).
- `scrape_loto.py` — Selenium scraper to backfill the remaining gap.

## ⚠️ Known gap: 2020-03-12 → 2026-07-06
The historical CSV ends in March 2020 and the verified recent draws only start
in July 2026 — about 6 years / ~500 draws are missing in between (LOTO draws
were also suspended for stretches of this period due to COVID and the
economic crisis, so the true gap may be smaller than the raw date math
suggests). Any date range you pick that falls inside this window will show
incomplete or empty results.

## 1. Backfill the gap (run this on your laptop, NOT a phone)

The scraper drives a real Chrome browser via Selenium — that needs a desktop/laptop
with Chrome installed. It cannot run on iOS/Android (no Chrome binary + chromedriver
on a phone).

```bash
# one-time setup
pip install selenium webdriver-manager beautifulsoup4

# fill the gap: scrapes 2020-03 through the current month, merges into data.json
python scrape_loto.py

# see all options
python scrape_loto.py --help
```

What it does:
- Defaults to `--start 2020-03 --end <current month>` (exactly the missing window).
- **Merges safely**: existing draws in `data.json` are preserved (your verified recent
  draws win); only dates not already present are added. Pass `--overwrite` to let
  scraped rows replace same-date entries.
- Auto-detects the month/game dropdowns by scanning every `<select>` on the page, so it
  usually works without tuning. Retries each month, and writes partial progress if you
  Ctrl-C or it's interrupted.

Useful flags:
- `--no-headless` — show the browser window so you can watch what it's doing (best first
  run / for debugging).
- `--dry-run` — scrape and report counts **without** writing `data.json`.
- `--skip-existing` — skip months already present (faster re-syncs).
- `--start YYYY-MM --end YYYY-MM` — scrape a specific window.
- `--month-select NAME --game-select NAME` — only needed if auto-detection fails; set
  these to the real `name`/`id` of the dropdowns (inspect them in Chrome).

If it comes back empty: run `python scrape_loto.py --no-headless --start 2026-07` (a month
you know has draws) and watch the browser. If the dropdowns aren't being found, inspect the
"Date by Month" / "Lottery name" `<select>` elements on
https://www.yelleb.com/lottery/results/history and pass their names via
`--month-select` / `--game-select`.

## 1b. Deploy the backfilled data
After a successful scrape, commit and push — GitHub Actions auto-deploys to Pages:
```bash
git add data.json && git commit -m "Backfill 2020-2026 draws" && git push
```
Your site updates at https://<username>.github.io/loto/ within a minute or two.

## 2. Run locally
Because `index.html` fetches `data.json` via `fetch()`, it needs to be served
over HTTP (not opened as a bare `file://` path, which browsers block for
security). From this folder:
```bash
python3 -m http.server 8000
```
Then open `http://localhost:8000`.

## 3. Deploy to GitHub Pages
Already set up. `.github/workflows/deploy-pages.yml` auto-deploys the repo root to
GitHub Pages on every push to `main`, so you just commit and push — no manual steps.
Live at `https://<username>.github.io/loto/`. (First-time setup only: Settings → Pages →
Source → "GitHub Actions", which has already been done for this repo.)

## 4. Keeping it updated
- **New draws**: use the "Add a draw manually" form in the app — it saves to
  the browser's `localStorage`, no redeploy needed. Click "Export merged
  dataset" any time to download an updated `data.json` you can commit back,
  making those draws permanent/shared with anyone else who visits the site.
- **Full re-sync**: re-run `scrape_loto.py` periodically and redeploy.

## Known limitations
- `localStorage` additions are per-browser/device — they won't show up for
  other visitors until you export and redeploy `data.json`.
- The scraper depends on yelleb.com's current page structure; if they change
  their markup, selectors will need updating.
