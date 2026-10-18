# Usage statistics Worker

The server side of the plugin's anonymous usage statistics: a Cloudflare
Worker with a D1 database. Its aggregates are public on the
[dashboard](https://mzarov.github.io/qgis-ai-agent/usage-stats/). Plain
JavaScript modules, no build step, no npm dependencies.

## What it stores

One row per install and day in the `pings` table (`schema.sql`): the SHA-256 of
the install's random UUID, the day, the plugin and QGIS versions, the OS
family, the UI locale, a local or remote model, the API dialect, and that day's
counts of runs, applies, tool calls, skill loads and failures. It stores no IP
addresses and keeps no request logs. A resend for the same install and day
replaces the row.

## API

`POST /v1/ping` takes one JSON body of at most 4096 bytes:

```json
{"v": 1, "install": "<uuid4>", "day": "YYYY-MM-DD",
 "plugin": "0.4.0", "qgis": "4.2.1", "os": "macos", "locale": "en",
 "provider": "remote", "dialect": "openai",
 "runs": 3, "applies": 2,
 "failures": {"timeout": 1}, "tools": {"inspect_project": 5}, "skills": {"style": 2}}
```

`src/payload.js` validates it strictly: no unknown fields, `day` within two
days of the server's UTC date, counts from 0 to 100000, map keys matching
`^[a-z][a-z0-9_]{0,48}$`, at most 150 per map. It answers `204`, or `400`,
`413` or `415` for a bad body, size or content type.

`GET /v1/stats` returns the public aggregates with
`Access-Control-Allow-Origin: *`: install totals, one entry per day for the
last 90 days, and per-value counts for the last 30 days (at most 100 values
each). The document is rebuilt at most once an hour and kept in the
`stats_snapshot` table. `GET /` points to the dashboard.

## Tests

```bash
node --test 'telemetry/worker/test/*.test.js'
```

The tests run `schema.sql` and every query on real SQLite through
`node:sqlite` (Node 22.13 or later).

## Deploy

`.github/workflows/usage-stats.yml` tests every pull request that touches
`telemetry/`. On a push to `main` it finds or creates the `ai-agent-usage` D1
database, renders `wrangler.toml` from `wrangler.toml.template`, applies
`schema.sql` and runs `wrangler deploy`. The workflow header lists the secrets
it needs; without them the deploy is skipped. Keep `schema.sql` idempotent and
additive: it is applied to the live database on every deploy.
