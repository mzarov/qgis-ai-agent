# Metrics

The plugin collects nothing about its users. What it has is public:
plugins.qgis.org counts the downloads of each version, and GitHub counts the
traffic of the repository. Neither keeps a history — the plugin page shows
running totals, GitHub forgets traffic after 14 days — so a daily snapshot is
the only way to see a trend.

## The daily snapshot

The `metrics` workflow runs once a day (and by hand from the Actions tab).
`tools/collect_metrics.py` appends that day's numbers to the `metrics` branch
and rewrites its README:

- `downloads.csv` — the running download total of every version, per day;
- `traffic.csv` — GitHub's views and clones per day, unique visitors beside them;
- `daily_downloads.svg` — new downloads per day, the difference between two
  snapshots;
- `README.md` — the totals by version, the last two weeks and the chart.

A version's count includes updates, so the first days after a release roughly
show how many installs are in use: everyone whose QGIS offers the update and
who takes it.

## Settings

Downloads need nothing. Traffic needs a token that may read the repository's
administration data: a fine-grained token for this repository with
**Administration: read**, saved as the `METRICS_TOKEN` secret. Without it the
run collects downloads only and says so.

The branch holds data only; pushing to it starts no other workflow.
