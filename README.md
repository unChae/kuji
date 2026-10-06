# LiveKuji Dashboard

This repository contains a lightweight static HTML dashboard for monitoring `livekuji` product-card snapshots over time.

## Setup

1. Keep CSV snapshots in `data/*.csv`
2. Add file names to `data/manifest.json`
3. Push to GitHub
4. In GitHub repo settings, enable **GitHub Pages** from the root branch

## Open dashboard

After pushing, the page is available at:

`https://<your-username>.github.io/<repo-name>/`

## Dashboard behavior

- Summary cards for latest snapshot
- New item list compared to previous snapshot
- Changed item list (`remaining_count` or `sold_out` changed)
- Latest items table

## Files

- `index.html` — dashboard UI
- `data/*.csv` — collected snapshots
- `data/manifest.json` — ordered snapshot list
