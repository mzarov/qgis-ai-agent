# Usage statistics

AI Agent sends anonymous usage statistics. It is on by default, and the plugin
says so the first time it loads, with a button to turn it off; the switch stays
in Settings → Privacy. The numbers below are what every install that left it on
has sent, and they are public — anyone sees the same aggregates the developers
do. They show which QGIS and plugin versions to
keep supporting, which tools earn their place, and where runs fail.

## What is sent

The service keeps at most one short report per install per day. A report holds:

- a random install id, created on your computer and tied to nothing else — not
  your name, account, machine or network;
- the date, without a time;
- the plugin and QGIS versions, the operating system family (macOS, Windows,
  Linux or other) and the interface language;
- whether the model server is local or remote, and which API dialect it speaks
  — never its address, model name or key;
- how many runs started that day and how many batches were applied;
- how many times each tool was called, each skill was loaded and each kind of
  failure happened — names and counts only.

## What is never sent

Nothing from your project — layers, fields, attribute values, coordinates, file
paths — and none of your requests, the model's replies, keys or addresses.

## How it is stored

The service keeps a SHA-256 hash of the install id, never the id itself: one
row per install per day, and a repeat for the same day replaces the row. It
stores no IP addresses and keeps no request logs. Only daily totals are
published — never a single install's row, its hash or a time finer than a day.
The service is short and open: see
[`telemetry/worker`](https://github.com/mzarov/qgis-ai-agent/tree/main/telemetry/worker)
in the repository.

## The numbers

The daily charts end with yesterday, since today is still being counted, and
the last few days may still grow as installs report. Hover over a bar or a
point to see its value; every chart also opens as a table.

| Measure | Value |
| --- | --- |
| Installs, all time | <span data-usage-stat="installs_total">—</span> |
| Active installs, last 30 days | <span data-usage-stat="installs_30d">—</span> |
| Runs, last 30 days | <span data-usage-stat="runs_30d">—</span> |
| Applied batches, last 30 days | <span data-usage-stat="applies_30d">—</span> |

<div id="usage-stats" data-loading="Loading the statistics…" data-failed="The statistics could not be loaded. Try again later." data-empty="No data yet." data-table="Show as a table">
<p class="usage-stats-status" role="status">The charts need JavaScript.</p>
<figure class="usage-chart" data-chart="installs" data-title="Daily active installs, last 90 days" data-key="Day" data-value="Installs"></figure>
<figure class="usage-chart" data-chart="runs" data-title="Runs per day, last 90 days" data-key="Day" data-value="Runs"></figure>
<figure class="usage-chart" data-chart="plugin" data-title="Plugin versions, installs in the last 30 days" data-key="Version" data-value="Installs"></figure>
<figure class="usage-chart" data-chart="qgis" data-title="QGIS versions, installs in the last 30 days" data-key="Version" data-value="Installs"></figure>
<figure class="usage-chart" data-chart="tools" data-title="Top 15 tools by calls, last 30 days" data-key="Tool" data-value="Calls"></figure>
<figure class="usage-chart" data-chart="skills" data-title="Top 15 skills by loads, last 30 days" data-key="Skill" data-value="Loads"></figure>
<figure class="usage-chart" data-chart="failures" data-title="Top 15 failure kinds, last 30 days" data-key="Kind" data-value="Failures"></figure>
<div class="usage-chart-row">
<figure class="usage-chart" data-chart="os" data-title="Operating systems" data-key="System" data-value="Installs"></figure>
<figure class="usage-chart" data-chart="provider" data-title="Model servers" data-key="Server" data-value="Installs"></figure>
<figure class="usage-chart" data-chart="dialect" data-title="API dialects" data-key="Dialect" data-value="Installs"></figure>
</div>
<figure class="usage-chart" data-chart="locale" data-title="Interface languages, installs in the last 30 days" data-key="Language" data-value="Installs"></figure>
</div>

Operating systems, model servers and API dialects count installs in the last 30
days. An install counts once per value: one that upgraded during the month
appears under both versions.
