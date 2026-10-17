# Usage statistics Worker

The server side of the plugin's anonymous usage statistics: a
Cloudflare Worker with a D1 database, both on the free plan. Everything it
publishes is public, on the [dashboard](https://mzarov.github.io/qgis-ai-agent/usage-stats/).
Plain JavaScript modules, no build step and no npm dependencies.

## What it stores

One row per install and day, in the `pings` table (`schema.sql`):

- the SHA-256 of the install's random UUID — never the UUID itself;
- the day the client reported, never a finer time;
- plugin and QGIS versions, OS family, UI locale, whether the model endpoint
  is local or remote, and the API dialect;
- counts for that day: runs, applied batches, and calls per tool, loads per
  skill and failures per kind.

A ping carries no project content, prompt, file path or key. The Worker stores
no IP address and keeps no request logs; Cloudflare, as the host, sees the
connection like any web server would. A resend for the same install and day
replaces the row, so retries are harmless.

## API

`POST /v1/ping` takes one JSON body of at most 4096 bytes with
`Content-Type: application/json`:

```json
{"v": 1, "install": "<uuid4>", "day": "YYYY-MM-DD",
 "plugin": "0.4.0", "qgis": "4.2.1", "os": "macos", "locale": "en",
 "provider": "remote", "dialect": "openai",
 "runs": 3, "applies": 2,
 "failures": {"timeout": 1}, "tools": {"inspect_project": 5}, "skills": {"style": 2}}
```

Validation is strict (`src/payload.js`): no unknown fields; `day` within two
days of the server's UTC date; versions up to 32 characters of
`[0-9A-Za-z._+-]`; `locale` up to 16 of `[A-Za-z_-]`; `os` one of `macos`,
`windows`, `linux`, `other`; `provider` `local` or `remote`; `dialect`
`openai` or `anthropic`; counts are integers from 0 to 100000; map keys match
`^[a-z][a-z0-9_]{0,48}$`, at most 150 per map. The three maps may be omitted.
The answer is `204` on success, `400` with `{"error": "..."}` for a ping that
breaks the contract, `413` for a larger body and `415` for another content
type.

`GET /v1/stats` returns the public aggregates, with `Access-Control-Allow-Origin: *`:

```json
{"generated": "2026-10-17T12:00:00.000Z", "installs_total": 120, "installs_30d": 64,
 "days": [{"day": "2026-07-20", "installs": 18, "runs": 41, "applies": 12}],
 "plugin": {"0.4.0": 51}, "qgis": {"4.2.1": 30}, "os": {"windows": 33},
 "locale": {"en": 40}, "provider": {"remote": 50}, "dialect": {"openai": 47},
 "tools": {"inspect_project": 900}, "skills": {"style": 120}, "failures": {"timeout": 7}}
```

- `installs_total` counts every install ever seen; `installs_30d` those seen in
  the last 30 days, today included.
- `days` has one entry per UTC day for the last 90 days, oldest first, zeros
  included; `installs` is the number of installs that sent that day.
- `plugin` to `dialect` count distinct installs per value over the last 30
  days; an install that upgraded counts under both versions.
- `tools`, `skills` and `failures` sum the counts over the last 30 days.
- Each object holds at most the 100 largest values, largest first.

The document is rebuilt at most once an hour and kept in the
`stats_snapshot` table, because the Cache API does nothing on `workers.dev`;
`Cache-Control` tells browsers how long the copy stays fresh.

`GET /` answers with one line pointing to the dashboard.

## Tests

```bash
node --test 'telemetry/worker/test/*.test.js'
```

`test/worker.test.js` runs `schema.sql` and every query on real SQLite through
`node:sqlite` (Node 22.13 or later).

## Deploy

`.github/workflows/usage-stats.yml` tests every pull request that touches
`telemetry/`, and on a push to `main` (or a manual run) deploys with a pinned
wrangler: it finds the `ai-agent-usage` D1 database by name or creates it,
renders `wrangler.toml` from `wrangler.toml.template` with the database id,
applies `schema.sql` (every statement is idempotent) and runs
`wrangler deploy`. The Worker URL appears in the job summary. The workflow
header lists the two secrets and the token permissions; without the secrets
the deploy is skipped with a notice.

A schema change must stay idempotent and additive: the same file is applied to
the live database on every deploy.
