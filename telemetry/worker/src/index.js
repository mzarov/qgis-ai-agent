// The usage statistics Worker: receives opt-in pings from the QGIS plugin and
// publishes daily aggregates. HTTP and D1 live here; the contract checks and
// the shaping of the public document live in payload.js.

import {
  COUNTERS,
  DIMENSIONS,
  MAX_BODY_BYTES,
  PING_COLUMNS,
  PingError,
  hashInstall,
  pingRow,
  shapeStats,
  statsWindow,
  validatePing,
} from "./payload.js";

const DASHBOARD_URL = "https://mzarov.github.io/qgis-ai-agent/usage-stats/";
const JSON_TYPE = "application/json";
const JSON_HEADERS = { "content-type": "application/json; charset=utf-8", "x-content-type-options": "nosniff" };
// The aggregates are recomputed at most once per this period. The snapshot
// lives in D1 because the Cache API is a no-op on workers.dev, and scanning a
// month of pings for every dashboard visit would eat the free read quota.
const STATS_TTL_SECONDS = 3600;
const PREFLIGHT_MAX_AGE_SECONDS = 86400;

// One row per install and day: a resend of the same day replaces the row.
const INSERT_PING = `INSERT OR REPLACE INTO pings (${PING_COLUMNS.join(", ")})
  VALUES (${PING_COLUMNS.map(() => "?").join(", ")})`;

const READ_SNAPSHOT = "SELECT generated, body FROM stats_snapshot WHERE id = 1";
const WRITE_SNAPSHOT = "INSERT OR REPLACE INTO stats_snapshot (id, generated, body) VALUES (1, ?1, ?2)";

// ?1 and ?2 are the first and last day of a window, both inclusive.
const TOTALS = `SELECT
  (SELECT COUNT(DISTINCT install_hash) FROM pings) AS installs_total,
  (SELECT COUNT(DISTINCT install_hash) FROM pings WHERE day BETWEEN ?1 AND ?2) AS installs_30d`;

// A row is one install on one day, so COUNT(*) per day counts distinct installs.
const DAYS = `SELECT day, COUNT(*) AS installs, SUM(runs) AS runs, SUM(applies) AS applies
  FROM pings WHERE day BETWEEN ?1 AND ?2 GROUP BY day`;

// One statement per facet: D1 refuses a compound SELECT this long. Column
// names are spliced in from the fixed DIMENSIONS and COUNTERS lists, never
// from a request; the values are bound.
const FACETS = [
  ...DIMENSIONS.map(
    (column) => `SELECT '${column}' AS facet, ${column} AS value, COUNT(DISTINCT install_hash) AS n
      FROM pings WHERE day BETWEEN ?1 AND ?2 GROUP BY ${column}`,
  ),
  ...COUNTERS.map(
    (column) => `SELECT '${column}' AS facet, entry.key AS value, SUM(entry.value) AS n
      FROM pings, json_each(pings.${column}) AS entry WHERE pings.day BETWEEN ?1 AND ?2 GROUP BY entry.key`,
  ),
];

function json(status, body, headers = {}) {
  return new Response(JSON.stringify(body), { status, headers: { ...JSON_HEADERS, ...headers } });
}

function jsonError(status, message, headers = {}) {
  return json(status, { error: message }, headers);
}

function isJsonType(header) {
  return (header ?? "").split(";")[0].trim().toLowerCase() === JSON_TYPE;
}

/** The request body, or null once it grows past `limit` bytes. */
async function readBody(request, limit) {
  if (Number(request.headers.get("content-length")) > limit) return null;
  if (!request.body) return new Uint8Array(0);
  const reader = request.body.getReader();
  const chunks = [];
  let size = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    size += value.byteLength;
    if (size > limit) {
      await reader.cancel();
      return null;
    }
    chunks.push(value);
  }
  const bytes = new Uint8Array(size);
  let offset = 0;
  for (const chunk of chunks) {
    bytes.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return bytes;
}

async function handlePing(request, env, now) {
  if (!isJsonType(request.headers.get("content-type"))) {
    return jsonError(415, "content type must be application/json");
  }
  const bytes = await readBody(request, MAX_BODY_BYTES);
  if (bytes === null) return jsonError(413, `body is larger than ${MAX_BODY_BYTES} bytes`);
  let body;
  try {
    body = JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(bytes));
  } catch {
    return jsonError(400, "body is not valid JSON");
  }
  let ping;
  try {
    ping = validatePing(body, now);
  } catch (error) {
    if (error instanceof PingError) return jsonError(400, error.message);
    throw error;
  }
  const row = pingRow(ping, await hashInstall(ping.install));
  await env.DB.prepare(INSERT_PING)
    .bind(...row)
    .run();
  return new Response(null, { status: 204 });
}

async function computeStats(db, now) {
  const window = statsWindow(now);
  const [totals, days, ...facets] = await db.batch([
    db.prepare(TOTALS).bind(window.recentSince, window.today),
    db.prepare(DAYS).bind(window.seriesSince, window.today),
    ...FACETS.map((sql) => db.prepare(sql).bind(window.recentSince, window.today)),
  ]);
  return shapeStats({
    generated: now.toISOString(),
    window,
    totals: totals.results[0],
    days: days.results,
    facets: facets.flatMap((facet) => facet.results),
  });
}

async function handleStats(request, env, now) {
  const snapshot = await env.DB.prepare(READ_SNAPSHOT).first();
  const age = snapshot ? (now.getTime() - Date.parse(snapshot.generated)) / 1000 : Number.NaN;
  let body = snapshot?.body;
  let maxAge = Math.floor(STATS_TTL_SECONDS - age);
  if (!(age >= 0 && age < STATS_TTL_SECONDS)) {
    const stats = await computeStats(env.DB, now);
    body = JSON.stringify(stats);
    maxAge = STATS_TTL_SECONDS;
    try {
      await env.DB.prepare(WRITE_SNAPSHOT).bind(stats.generated, body).run();
    } catch (error) {
      // A lost snapshot only means the next visitor recomputes it.
      console.error("usage stats snapshot was not saved:", error?.message);
    }
  }
  return new Response(body, {
    headers: {
      ...JSON_HEADERS,
      "access-control-allow-origin": "*",
      "cache-control": `public, max-age=${maxAge}`,
    },
  });
}

function handleStatsPreflight() {
  return new Response(null, {
    status: 204,
    headers: {
      "access-control-allow-origin": "*",
      "access-control-allow-methods": "GET",
      "access-control-max-age": String(PREFLIGHT_MAX_AGE_SECONDS),
    },
  });
}

function handleRoot() {
  return new Response(`AI Agent for QGIS usage statistics: ${DASHBOARD_URL}\n`, {
    headers: { "content-type": "text/plain; charset=utf-8" },
  });
}

const ROUTES = new Map([
  ["/v1/ping", { POST: handlePing }],
  ["/v1/stats", { GET: handleStats, OPTIONS: handleStatsPreflight }],
  ["/", { GET: handleRoot }],
]);

/** Routes one request; `now` is injectable so tests can pin the server date. */
export async function handle(request, env, now = new Date()) {
  const methods = ROUTES.get(new URL(request.url).pathname);
  if (!methods) return jsonError(404, "not found");
  if (!Object.hasOwn(methods, request.method)) {
    return jsonError(405, "method not allowed", { allow: Object.keys(methods).join(", ") });
  }
  return methods[request.method](request, env, now);
}

export default {
  async fetch(request, env) {
    try {
      return await handle(request, env);
    } catch (error) {
      // Never log the request body: it carries the raw install id.
      console.error("usage worker failed:", error?.message);
      return jsonError(500, "internal error");
    }
  },
};
