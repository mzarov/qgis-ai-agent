# Usage statistics Worker

The server side of the plugin's anonymous usage statistics: a Cloudflare
Worker with a D1 database. Its aggregates are public on the
[dashboard](https://mzarov.github.io/qgis-ai-agent/usage-stats/). Plain
JavaScript modules, no build step, no npm dependencies.

## What it stores

One row per install and day in the `pings` table (`schema.sql`): the SHA-256 of
the install's random UUID, the day, the plugin and QGIS versions, the OS
family, the UI locale, a local or remote model, the API dialect, and that day's
counts of runs, applies, tool calls, skill loads and failures. A v2 ping adds
a row to `ping_extras`: whether a model is set up and the failed calls per
tool. A v3 ping adds a row to `ping_details`: the model family, the `retries`,
`checks` and `sessions` counts, and bucketed counts of run outcomes, modes,
plans, requests per session and before an apply, steps, durations and tokens.
It stores no IP addresses and keeps no request logs. A resend for the same
install and day replaces the rows, and an older version's resend drops the
newer tables' row for that day.

The `PING_LIMITER` rate limiting binding (`wrangler.toml.template`) allows 5
pings a minute per `CF-Connecting-IP`; the address keys the limiter's counter
and nothing else. Without the binding, as in the tests, pings are not limited.

## API

`POST /v1/ping` takes one JSON body of at most 8192 bytes:

```json
{"v": 3, "install": "<uuid4>", "day": "YYYY-MM-DD",
 "plugin": "0.4.3", "qgis": "4.2.1", "os": "macos", "locale": "en",
 "provider": "remote", "dialect": "openai", "family": "deepseek",
 "configured": true, "runs": 3, "applies": 2,
 "retries": 1, "checks": 1, "sessions": 2,
 "failures": {"timeout": 1}, "tools": {"inspect_project": 5},
 "tool_errors": {"inspect_project": 1}, "skills": {"style": 2},
 "outcomes": {"answered": 2, "failed": 1}, "modes": {"plan": 1},
 "session_requests": {"r1": 1, "r2": 1}, "steps": {"s2_3": 3},
 "durations": {"t10_30": 3}, "tokens": {"k5_20": 3}}
```

A v1 ping (plugin 0.4.0) has no `configured` or `tool_errors`, a v2 ping
(0.4.1 and 0.4.2) none of the v3 fields; all three versions are accepted.

`src/payload.js` validates it strictly: no unknown fields, `day` at most eight
days before and one day after the server's UTC date, counts from 0 to 100000,
map keys matching
`^[a-z][a-z0-9_]{0,48}$`, at most 150 per map, no more errors for a tool than
calls of it. `family` and the keys of the v3 maps come from the fixed lists in
`payload.js`. It answers `204`, or `400`, `413` or `415` for a bad body, size or
content type, and `429` to an address over its limit.

`GET /v1/stats` returns the public aggregates with
`Access-Control-Allow-Origin: *`: install totals, one entry per day for the
last 90 days, one entry per ISO week (new and returning installs) for the last
13, the 30-day funnel (active, set up, ran, applied), the share of installs
still active 7 and 30 days after their first day, failed calls per tool, and
per-value counts for the last 30 days (at most 100 values each, and only
values at least 5 installs reported). From v3 pings it adds sessions and
failed runs per day, 30-day activity totals and bucket sums, runs and failures
per model family, and how many days new installs took to set up a model, run
and apply. The document
is rebuilt at most once an hour and kept in the `stats_snapshot` table. One
request claims the rebuild while the others get the previous document, which
is also served when a rebuild fails.
`GET /` points to the dashboard.

## Tests

```bash
node --test 'telemetry/worker/test/*.test.js'
```

The tests run `schema.sql` and every query on real SQLite through
`node:sqlite` (Node 22.13 or later). `test/dashboard.test.js` draws
`docs/assets/usage-stats.js` into a minimal DOM.

## Deploy

`.github/workflows/usage-stats.yml` tests every pull request that touches
`telemetry/`. On a push to `main` it finds or creates the `ai-agent-usage` D1
database, renders `wrangler.toml` from `wrangler.toml.template`, applies
`schema.sql` and runs `wrangler deploy`. The workflow header lists the secrets
it needs; without them the deploy is skipped. Keep `schema.sql` idempotent and
additive: it is applied to the live database on every deploy.
