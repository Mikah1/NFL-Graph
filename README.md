# Fieldvision

NFL scatter plots with real nflverse play-by-play and player statistics, ESPN team identity, historical seasons, filters, draggable axes, logos/headshots, reference lines, saved views, and CSV/SVG exports.

## GitHub Pages

Published address: **https://mikah1.github.io/NFL-Graph/** (available after Pages is enabled and deployment succeeds).

In repository **Settings → Pages → Source**, select **GitHub Actions**. The `Publish Fieldvision` workflow builds and deploys the site on pushes to `main`, manual runs, and every six hours. Public data imports need no API keys or secrets. If a run happened before Pages was enabled, run the workflow again under Actions.

Pages serves the static app and compressed weekly season datasets. A browser worker decompresses data and computes filtered stats outside the UI thread. The published site does not require a Python server or the local preview. Current-season imports refresh during deployment; historical datasets are reused from the Actions cache. Refresh data reloads the most recently published snapshot, rather than starting a server import. Provider updates can lag games; unavailable seasons are omitted from the season selector.

Build locally:

```bash
python3 scripts/build_pages.py
python3 -m http.server 3001 --directory dist
```

The first build downloads seasons from 1999 through the current season. To build a smaller set, supply `--seasons` followed by the current year and any historical years. Add `--refresh` to refresh the current-season imports.

## Local Python preview

```bash
python3 server.py
```

Open http://localhost:3000. Set `PORT` to change the port. The preview uses Python APIs and downloads historical data on selection. Cached files open immediately; files older than six hours refresh in the background. Cached data remains usable offline; stale cache is labeled. Raw season data in memory is limited to three seasons.

## Metrics and performance

Team efficiency includes run/pass plays with valid EPA and yards gained. Success means positive EPA. Defensive measures describe opposing offenses; lower efficiency allowed is better. Player EPA per attempt uses pass attempts, not sacks. Player percentages are calculated from aggregated counts; share metrics are opportunity-weighted weekly values. Published weekly snapshots are rounded to four decimals; combined season totals can differ from the Python preview by small rounding amounts.

Charts draw points in batches, reuse number formatters and tooltips, and limit featured headshots. Stats are grouped into searchable sections with eight-item pages. Data tables display 100 rows per page. Saved views stay in the browser where they were created.

Checks: `python3 -m unittest discover -s tests` and `node --check static/app.js`.

## Offensive and defensive line statistics

ESPN Analytics publishes pass-block, run-block, pass-rush, and run-stop win rates using NFL Next Gen Stats. The app automatically imports the public ESPN article content feed, joins player identities to nflverse rosters, and caches separate line-play snapshots for 2023–2026. Wins, eligible plays, double-team percentages, and position-group rankings are included where published. Team leaderboards cover all 32 teams; player leaderboards contain qualifying leaders only, so missing players have unavailable metrics, never zeroes.

[Current source leaderboard](https://www.espn.com/nfl/story/_/id/49742016/2026-win-rates-team-player-rankings-pass-rush-run-stop-blocking). Import endpoint: `https://cdn.espn.com/core/nfl/story/_/id/49742016?xhr=1`. Source IDs and historical articles are maintained in `line_stats.py`. ESPN changed its pass-game methodology in 2026.

Choose the Offensive line or Defensive line stat section and assign metrics to either axis. Line-play minimum samples use eligible plays. These metrics are cumulative regular-season snapshots, not weekly splits: select weeks starting at 1 and ending at or beyond the source's reported week. Incompatible filters show a notice and omit line metrics. Player averages describe the plotted qualifying subset. GitHub Pages fetches each season's small supplemental file in its existing worker; line imports never inflate weekly play-by-play snapshots.
