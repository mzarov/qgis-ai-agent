# Metrics

plugins.qgis.org counts downloads per version, and GitHub counts repository
traffic. Neither keeps a history: the plugin page shows running totals, and
GitHub forgets traffic after 14 days. A daily snapshot keeps the trend. The
plugin's own anonymous usage counts are a separate thing, described on the
[usage statistics](usage-stats.md) page.

## The daily snapshot

The `metrics` workflow runs once a day and by hand from the Actions tab.
`tools/collect_metrics.py` appends the day's numbers to the `metrics` branch:

- `downloads.csv`: the download total of every version, per day;
- `traffic.csv`: views, clones and unique visitors per day;
- `daily_downloads.svg`: new downloads per day;
- `README.md`: totals by version, the last two weeks and the chart.

Download counts include updates, so the first days after a release roughly
show how many installs are in use.

## Settings

Downloads need nothing. Traffic needs a fine-grained token for this repository
with **Administration: read**, saved as the `METRICS_TOKEN` secret. Without it,
or when GitHub does not answer, the run collects downloads only. When
plugins.qgis.org returns no list of versions, the run fails and saves nothing.
