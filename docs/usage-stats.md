# Usage statistics

AI Agent sends anonymous usage statistics. They are on by default; the plugin
says so the first time it loads and offers to turn them off. The switch is in
Settings → Privacy. This page shows the totals from every install that left
them on.

## What is sent

The collector keeps one report per install per day. A minute after the counts
change, the plugin sends the day so far, and it replaces that day's earlier
report. A report holds:

- a random install id, created on your computer and linked to nothing else;
- the date, without a time;
- the plugin and QGIS versions, the OS family and the interface language;
- whether the model server is local or remote, and its API format;
- which known service the model server belongs to, from a fixed list (such
  as OpenAI, OpenRouter, Ollama or LM Studio), otherwise only "other local"
  or "other remote". The address and the model name are never sent;
- whether a model is set up in Settings, as yes or no;
- the number of requests, conversations, retries, checks after Apply and
  applied batches (a day the plugin was loaded counts even with none);
- how runs end: answered, failed, stopped or at a step or token limit; how
  many ran in Plan or Auto mode; and how plans end: shown, cancelled, undone or
  applied in Auto mode;
- the steps, active time and tokens of each run, the requests in each
  conversation and the requests until an Apply, all as counts in fixed ranges
  such as "3–5 requests" or "1–3 min";
- how often each of the plugin's tools was called and failed, and each
  built-in skill loaded. A name the model made up and the names of skills you
  wrote yourself are not sent;
- how many runs failed, by kind: a category such as a timeout or a refused
  key, otherwise the HTTP status code with the provider's short error code
  (such as `context_length_exceeded`), or the error's class name with the
  plugin file and line it came from. The error text is not sent.

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
as a table. Conversations, run ends, modes, plans, model services and the
ranges per run come from plugin 0.4.3 and later; until such installs report,
those charts have no data.

<div id="usage-stats" data-loading="Loading the statistics…" data-failed="The statistics could not be loaded. Try again later." data-empty="No data yet." data-table="Show as a table" data-other_local="Other local server" data-other_remote="Other remote service">
<p class="usage-stats-status" role="status">The charts need JavaScript.</p>
<div class="usage-tiles">
<div class="usage-tile"><span class="usage-tile-label">Active installs</span><span class="usage-tile-value" data-usage-stat="installs_30d">—</span><span class="usage-tile-note" data-usage-stat="installs_total" data-format="last 30 days, {0} all time">last 30 days</span></div>
<div class="usage-tile"><span class="usage-tile-label">Requests</span><span class="usage-tile-value" data-usage-stat="requests_30d">—</span><span class="usage-tile-note">last 30 days</span></div>
<div class="usage-tile"><span class="usage-tile-label">Conversations</span><span class="usage-tile-value" data-usage-stat="sessions_30d">—</span><span class="usage-tile-note">last 30 days, plugin 0.4.3+</span></div>
<div class="usage-tile"><span class="usage-tile-label">Requests per conversation</span><span class="usage-tile-value" data-usage-stat="requests_per_session">—</span><span class="usage-tile-note">on average, plugin 0.4.3+</span></div>
<div class="usage-tile"><span class="usage-tile-label">Runs that ended with an answer</span><span class="usage-tile-value" data-usage-stat="answered">—</span><span class="usage-tile-note" data-usage-stat="answered" data-format="{1} of {2} runs, plugin 0.4.3+">plugin 0.4.3+</span></div>
<div class="usage-tile"><span class="usage-tile-label">Applied batches</span><span class="usage-tile-value" data-usage-stat="applies_30d">—</span><span class="usage-tile-note">last 30 days</span></div>
<div class="usage-tile"><span class="usage-tile-label">Still active after 7 days</span><span class="usage-tile-value" data-usage-stat="kept_7">—</span><span class="usage-tile-note" data-usage-stat="kept_7" data-format="{1} of {2} installs">after their first day</span></div>
<div class="usage-tile"><span class="usage-tile-label">Downloads</span><span class="usage-tile-value" data-usage-stat="downloads_total">—</span><span class="usage-tile-note" data-usage-stat="downloads_30d" data-format="{0} since {1}">all time</span></div>
</div>
</div>

### Growth

<div class="usage-section">
<figure class="usage-chart" data-chart="installs" data-title="Daily active installs, last 90 days" data-key="Day" data-value="Installs"></figure>
<figure class="usage-chart" data-chart="weeks" data-title="New and returning installs per week, last 12 weeks" data-key="Week from" data-new="New" data-returning="Returning"></figure>
<figure class="usage-chart" data-chart="retention" data-title="Installs still active after their first day" data-key="After" data-kept="Still active" data-installs="Installs" data-share="Share" data-kept_7="7+ days" data-kept_30="30+ days" data-format="{0} ({1} of {2})"></figure>
<figure class="usage-chart" data-chart="downloads" data-title="Downloads per day from plugins.qgis.org" data-key="Day" data-downloads="Downloads"></figure>
</div>

### Activation

<div class="usage-section">
<figure class="usage-chart" data-chart="funnel" data-title="Funnel: installs active in the last 30 days" data-key="Step" data-value="Installs" data-share="Share of active" data-active="Active" data-configured="Set up a model" data-ran="Ran the agent" data-applied="Applied a batch"></figure>
<figure class="usage-chart" data-chart="activation" data-title="Days from the first day to each step, installs first seen in the last 90 days" data-key="Step" data-configured="Set up a model" data-ran="Ran the agent" data-applied="Applied a batch" data-d0="Same day" data-d1="Next day" data-d2_7="2–7 days" data-d8_plus="8+ days" data-never="Not yet"></figure>
</div>

### Usage

<div class="usage-section">
<figure class="usage-chart" data-chart="daily_use" data-title="Requests and conversations per day, last 90 days" data-key="Day" data-runs="Requests" data-sessions="Conversations"></figure>
<figure class="usage-chart" data-chart="run_kinds" data-title="Runs by kind, last 30 days" data-key="Kind" data-value="Runs" data-requests="Requests" data-retries="Retries" data-checks="Checks after Apply"></figure>
<div class="usage-chart-row">
<figure class="usage-chart" data-chart="session_requests" data-title="Conversations by number of requests" data-key="Requests" data-value="Conversations" data-share="Share" data-r1="1" data-r2="2" data-r3_5="3–5" data-r6_10="6–10" data-r11_plus="11+"></figure>
<figure class="usage-chart" data-chart="to_apply" data-title="Requests until an Apply" data-key="Requests" data-value="Applies" data-share="Share" data-r1="1" data-r2="2" data-r3_5="3–5" data-r6_10="6–10" data-r11_plus="11+"></figure>
</div>
<figure class="usage-chart" data-chart="modes" data-title="Runs in Plan and Auto mode, last 30 days" data-key="Mode" data-value="Runs" data-share="Share of all runs" data-plan="Plan" data-auto="Auto"></figure>
</div>

### Quality

<div class="usage-section">
<figure class="usage-chart" data-chart="outcomes" data-title="How runs end, last 30 days" data-key="End" data-value="Runs" data-share="Share" data-answered="Answered" data-failed="Failed" data-stopped="Stopped by the user" data-limit="Hit a step or token limit"></figure>
<figure class="usage-chart" data-chart="failures" data-title="Top 15 failure kinds, last 30 days" data-key="Kind" data-value="Failures" data-installs="Installs"></figure>
<figure class="usage-chart" data-chart="families" data-title="Failed runs by model service, last 30 days" data-key="Service" data-installs="Installs" data-runs="Runs" data-failed="Failed" data-rate="Failure rate" data-format="{0} ({1} of {2})"></figure>
<figure class="usage-chart" data-chart="tool_errors" data-title="Top 15 tools by errors, with the error rate, last 30 days" data-key="Tool" data-value="Errors" data-calls="Calls" data-rate="Error rate"></figure>
<div class="usage-chart-row">
<figure class="usage-chart" data-chart="steps" data-title="Steps per run" data-key="Steps" data-value="Runs" data-share="Share" data-s0="None" data-s1="1" data-s2_3="2–3" data-s4_7="4–7" data-s8_15="8–15" data-s16_plus="16+"></figure>
<figure class="usage-chart" data-chart="durations" data-title="Active time per run" data-key="Time" data-value="Runs" data-share="Share" data-t0_10="Up to 10 s" data-t10_30="10–30 s" data-t30_60="30–60 s" data-t60_180="1–3 min" data-t180_plus="Over 3 min"></figure>
<figure class="usage-chart" data-chart="tokens" data-title="Tokens per run" data-key="Tokens" data-value="Runs" data-share="Share" data-k0_5="Up to 5k" data-k5_20="5k–20k" data-k20_50="20k–50k" data-k50_200="50k–200k" data-k200_plus="Over 200k"></figure>
</div>
<figure class="usage-chart" data-chart="plans" data-title="Plans, last 30 days" data-key="Outcome" data-value="Plans" data-shown="Shown" data-applied="Applied" data-cancelled="Cancelled" data-undone="Undone" data-auto="Applied in Auto mode"></figure>
</div>

### Environment

<div class="usage-section">
<figure class="usage-chart" data-chart="plugin" data-title="Plugin versions, installs in the last 30 days" data-key="Version" data-value="Installs"></figure>
<figure class="usage-chart" data-chart="qgis" data-title="QGIS versions, installs in the last 30 days" data-key="Version" data-value="Installs"></figure>
<div class="usage-chart-row">
<figure class="usage-chart" data-chart="os" data-title="Operating systems" data-key="System" data-value="Installs"></figure>
<figure class="usage-chart" data-chart="provider" data-title="Model servers" data-key="Server" data-value="Installs"></figure>
<figure class="usage-chart" data-chart="dialect" data-title="API dialects" data-key="Dialect" data-value="Installs"></figure>
</div>
<figure class="usage-chart" data-chart="family" data-title="Model services, installs in the last 30 days" data-key="Service" data-value="Installs"></figure>
<figure class="usage-chart" data-chart="locale" data-title="Interface languages, installs in the last 30 days" data-key="Language" data-value="Installs"></figure>
<figure class="usage-chart" data-chart="tools" data-title="Top 15 tools by calls, last 30 days" data-key="Tool" data-value="Calls"></figure>
<figure class="usage-chart" data-chart="skills" data-title="Top 15 skills by loads, last 30 days" data-key="Skill" data-value="Loads"></figure>
</div>

Operating systems, model servers and API dialects count installs in the last 30
days, and the ranges per run and per conversation cover the same days. An
install that upgraded during the month counts under both versions.

Weeks start on Monday; a returning install was also active in an earlier week.
The activation chart times each step from an install's first day; "Not yet"
also holds installs too new to have got there. A run is one request, retry or
check after Apply. Active time counts the model and the tools, not the time a
run waits for you, and the requests until an Apply count from the
conversation's previous Apply.

Plugin 0.4.0 does not report the model setting or failed calls, so the funnel
counts its installs that ran the agent as set up, and error rates leave its
calls out. Downloads include updates.
