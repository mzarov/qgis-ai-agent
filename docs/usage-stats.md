# Usage statistics

AI Agent sends anonymous usage statistics. They are on by default; the plugin
says so the first time it loads and offers to turn them off. The switch is in
Settings → Privacy. This page shows the totals from every install that left
them on.

## What is sent

At most one report per install per day:

- a random install id, created on your computer and linked to nothing else;
- the date, without a time;
- the plugin and QGIS versions, the OS family and the interface language;
- whether the model server is local or remote, and its API format;
- whether a model is set up in Settings, as yes or no;
- the number of runs and applied batches (a day the plugin was loaded counts
  even with none);
- how often each of the plugin's tools was called and failed, each built-in
  skill loaded and each kind of failure happened. A name the model made up and
  the names of skills you wrote yourself are not sent.

A day without a connection is sent later; the last three such days wait.

Nothing from your project is sent: no layers, fields, values, coordinates or
file paths. Your requests, the model's answers, keys, addresses and model
names are not sent either.

## How it is stored

The collector keeps a SHA-256 hash of the install id, one row per install per
day. It stores no IP addresses and keeps no request logs; the address a report
comes from is used only to limit how many reports it can send a minute. Only
totals are published, and a value such as a version, a language or a tool
name is shown once at least 5 installs reported it. The code is in
[`telemetry/worker`](https://github.com/mzarov/qgis-ai-agent/tree/main/telemetry/worker).

## The numbers

Daily charts end with yesterday and weekly ones with last week; the last few
days may still grow. Hover a bar or point for its value; each chart also opens
as a table.

| Measure | Value |
| --- | --- |
| Installs, all time | <span data-usage-stat="installs_total">—</span> |
| Active installs, last 30 days | <span data-usage-stat="installs_30d">—</span> |
| Runs, last 30 days | <span data-usage-stat="runs_30d">—</span> |
| Applied batches, last 30 days | <span data-usage-stat="applies_30d">—</span> |
| Downloads from plugins.qgis.org, all time | <span data-usage-stat="downloads_total">—</span> |
| Downloads from plugins.qgis.org, last 30 days | <span data-usage-stat="downloads_30d" data-format="{0} since {1}">—</span> |
| Installs still active 7+ days after their first day | <span data-usage-stat="kept_7" data-format="{0} ({1} of {2})">—</span> |
| Installs still active 30+ days after their first day | <span data-usage-stat="kept_30" data-format="{0} ({1} of {2})">—</span> |

<div id="usage-stats" data-loading="Loading the statistics…" data-failed="The statistics could not be loaded. Try again later." data-empty="No data yet." data-table="Show as a table">
<p class="usage-stats-status" role="status">The charts need JavaScript.</p>
<figure class="usage-chart" data-chart="funnel" data-title="Funnel: installs active in the last 30 days" data-key="Step" data-value="Installs" data-share="Share of active" data-active="Active" data-configured="Set up a model" data-ran="Ran the agent" data-applied="Applied a batch"></figure>
<figure class="usage-chart" data-chart="installs" data-title="Daily active installs, last 90 days" data-key="Day" data-value="Installs"></figure>
<figure class="usage-chart" data-chart="runs" data-title="Runs per day, last 90 days" data-key="Day" data-value="Runs"></figure>
<figure class="usage-chart" data-chart="new" data-title="New installs per week, last 12 weeks" data-key="Week from" data-value="Installs"></figure>
<figure class="usage-chart" data-chart="returning" data-title="Returning installs per week, last 12 weeks" data-key="Week from" data-value="Installs"></figure>
<figure class="usage-chart" data-chart="plugin" data-title="Plugin versions, installs in the last 30 days" data-key="Version" data-value="Installs"></figure>
<figure class="usage-chart" data-chart="qgis" data-title="QGIS versions, installs in the last 30 days" data-key="Version" data-value="Installs"></figure>
<figure class="usage-chart" data-chart="tools" data-title="Top 15 tools by calls, last 30 days" data-key="Tool" data-value="Calls"></figure>
<figure class="usage-chart" data-chart="tool_errors" data-title="Top 15 tools by errors, with the error rate, last 30 days" data-key="Tool" data-value="Errors" data-calls="Calls" data-rate="Error rate"></figure>
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
days. An install that upgraded during the month counts under both versions.

Weeks start on Monday; a returning install was also active in an earlier week.
Plugin 0.4.0 does not report the model setting or failed calls, so the funnel
counts its installs that ran the agent as set up, and error rates leave its
calls out. Downloads include updates.
