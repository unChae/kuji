# LiveKuji Dashboard

This repository contains a lightweight static HTML dashboard for monitoring `livekuji` product-card snapshots over time.

## Setup

1. Keep CSV snapshots in `data/*.csv`
2. Add file names to `data/manifest.json`
3. Push to GitHub
4. In GitHub repo settings, enable **GitHub Pages** from the root branch

## Hourly collection

GitHub Actions runs `livekuji_scraper.py` hourly on the `main` branch. Each run
adds a timestamped CSV snapshot, updates `data/manifest.json`, and commits and
pushes those data changes. The workflow can also be started manually from the
Actions tab with **Run workflow**.

For the workflow to push snapshots, make sure repository settings allow
Actions to have **Read and write permissions** under **Settings → Actions →
General → Workflow permissions**. The workflow uses its built-in `GITHUB_TOKEN`;
no separate secret is needed. GitHub schedules use UTC, and a scheduled run can
start a little later than its nominal time.

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
