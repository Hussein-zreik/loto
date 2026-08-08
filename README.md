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

## 1. Backfill the gap (do this in Claude Code)
```bash
pip install selenium webdriver-manager beautifulsoup4
python scrape_loto.py --start 2020-03      # targets just the missing window
```
This scrapes from the given month through today and merges into `data.json`
(existing dates are preserved; only missing ones are added — check the merge
logic in `scrape_loto.py`'s `main()` if you want to change that behavior).
The scraper's CSS/selector assumptions are best-effort (I couldn't test them
against the live site from this sandbox — my network access here is locked
to package registries, not lottery sites). If it comes back empty or errors
on the dropdown selection, open
https://www.yelleb.com/lottery/results/history in Chrome, inspect the
"Date by Month" and "Lottery name" `<select>` elements, and update
`MONTH_SELECT_NAME` / `GAME_SELECT_NAME` at the top of the script to match.

## 2. Run locally
Because `index.html` fetches `data.json` via `fetch()`, it needs to be served
over HTTP (not opened as a bare `file://` path, which browsers block for
security). From this folder:
```bash
python3 -m http.server 8000
```
Then open `http://localhost:8000`.

## 3. Deploy to GitHub Pages
1. Push `index.html` and `data.json` to a repo (root or a `/docs` folder).
2. Repo Settings → Pages → set source to that branch/folder.
3. Your app will be live at `https://<username>.github.io/<repo>/`.

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
