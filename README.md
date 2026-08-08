# Lebanese LOTO Archive — Setup Notes

Live site: **https://hussein-zreik.github.io/loto/**

## Files
- `index.html` — the app (calendar range picker, results table, hot/cold + frequency stats, manual draw entry)
- `data.json` — **2,421 real draws**, continuous from draw #1 (2002-09-12) through 2026-08-06.
  Sources: a historical CSV (2002-09-12 → 2020-03-12) + a yelleb.com backfill of
  2020-03 → 2026-08. Validated: no duplicate dates, every draw has 6 unique numbers in 1–42
  plus a bonus.
- `scrape_loto.py` — Selenium scraper used to build/refresh `data.json`.
- `.github/workflows/deploy-pages.yml` — auto-deploys to GitHub Pages on every push to `main`.

## Data coverage
Roughly 104 draws per year (twice weekly) across the whole range. Two dips are **real
history, not missing data**: 2020 (91 draws) and 2021 (95 draws), when LOTO was suspended
for stretches due to COVID and the economic crisis — including a 46-day break after
2020-03-12 and a 35-day break after 2021-01-11.

## 1. Refresh the data (run this on your laptop, NOT a phone)

The scraper drives a real Chrome browser via Selenium — that needs a desktop/laptop
with Chrome installed. It cannot run on iOS/Android (no Chrome binary + chromedriver
on a phone).

```bash
# one-time setup
pip install selenium webdriver-manager beautifulsoup4

# grab only what's new (recommended for routine refreshes)
python scrape_loto.py --skip-existing

# see all options
python scrape_loto.py --help
```

What it does:
- Defaults to `--start 2020-03 --end <current month>`.
- **Merges safely**: existing draws in `data.json` are preserved; only dates not already
  present are added. Pass `--overwrite` to let scraped rows replace same-date entries.
- Retries each month, and writes partial progress if you Ctrl-C or it's interrupted.

Useful flags:
- `--skip-existing` — skip months already present (fastest re-sync).
- `--dry-run` — scrape and report counts **without** writing `data.json`.
- `--no-headless` — show the browser window so you can watch what it's doing.
- `--start YYYY-MM --end YYYY-MM` — scrape a specific window.
- `--debug` — dump the live page's structure (dropdowns, options, table rows) to
  `loto_debug.txt`.
- `--probe` — try every known way of filtering the page and report which one works,
  writing `loto_probe.txt`. **This is the tool to reach for if the scraper ever returns
  0 draws for every month.**

### How the site's filter actually works (hard-won notes)
If yelleb.com changes and the scraper breaks, start here — these are the things that
cost the most time to discover:
- The filters are `#LotteryName` (values `Loto` / `Zeed` / `Yawmiyeh`) and `#LotteryDate`
  (values like `2021-01`, going back to `2012-06`).
- The form is **`method="post"`** — URL query params like `?date=2021-01` are ignored and
  silently return the default "Last 30 draws" view.
- **Selecting the dropdown does nothing on its own.** The form must be submitted.
- The page has several buttons and the **first one in the DOM is the header's "Sign in"** —
  clicking that instead of the form's `input[type=submit]` ("Search Numbers") looks like a
  successful run but silently leaves the results unfiltered. Always submit the form that
  *contains* the month dropdown.
- Non-Loto rows (Zeed, Yawmiyeh) share the same table; the parser filters to `Loto` rows.

Debugging order if it returns 0 draws everywhere:
```bash
python scrape_loto.py --probe --start 2021-01   # identifies the working filter method
python scrape_loto.py --debug                   # dumps the page structure
```

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
  their markup, selectors will need updating (see the filter notes in section 1,
  and use `--probe`).
- This is an unofficial archive. Data comes from a public results tracker, not
  La Libanaise des Jeux — verify anything that matters against the official source.
- Frequency/hot/cold stats describe what already happened. Each draw is an
  independent random event, so past frequency has no predictive power.
