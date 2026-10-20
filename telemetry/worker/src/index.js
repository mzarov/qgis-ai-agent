import {
  COUNTERS,
  DIMENSIONS,
  EXTRA_COLUMNS,
  MAX_BODY_BYTES,
  PING_COLUMNS,
  PingError,
  RETENTION_DAYS,
  extrasRow,
  hashInstall,
  pingRow,
  shapeStats,
  statsWindow,
  validatePing,
} from "./payload.js";

const DASHBOARD_URL = "https://mzarov.github.io/qgis-ai-agent/usage-stats/";
const JSON_TYPE = "application/json";
const JSON_HEADERS = { "content-type": "application/json; charset=utf-8", "x-content-type-options": "nosniff" };
// Snapshot in D1: the Cache API is a no-op on workers.dev, and rescans would eat the free read quota.
const STATS_TTL_SECONDS = 3600;
const PREFLIGHT_MAX_AGE_SECONDS = 86400;

const INSERT_PING = `INSERT OR REPLACE INTO pings (${PING_COLUMNS.join(", ")})
  VALUES (${PING_COLUMNS.map(() => "?").join(", ")})`;

const INSERT_EXTRAS = `INSERT OR REPLACE INTO ping_extras (${EXTRA_COLUMNS.join(", ")})
  VALUES (${EXTRA_COLUMNS.map(() => "?").join(", ")})`;

// A v1 resend replaces the pings row, so a v2 row left beside it would describe another ping.
const DELETE_EXTRAS = "DELETE FROM ping_extras WHERE install_hash = ?1 AND day = ?2";

const READ_SNAPSHOT = "SELECT generated, body FROM stats_snapshot WHERE id = 1";
const WRITE_SNAPSHOT = "INSERT OR REPLACE INTO stats_snapshot (id, generated, body) VALUES (1, ?1, ?2)";

const TOTALS = `SELECT
  (SELECT COUNT(DISTINCT install_hash) FROM pings) AS installs_total,
  (SELECT COUNT(DISTINCT install_hash) FROM pings WHERE day BETWEEN ?1 AND ?2) AS installs_30d`;

const DAYS = `SELECT day, COUNT(*) AS installs, SUM(runs) AS runs, SUM(applies) AS applies
  FROM pings WHERE day BETWEEN ?1 AND ?2 GROUP BY day`;

// One SELECT per facet (D1 refuses a long compound one); columns come from fixed lists, never a request.
const FACETS = [
  ...DIMENSIONS.map(
    (column) => `SELECT '${column}' AS facet, ${column} AS value,
        COUNT(DISTINCT install_hash) AS n, COUNT(DISTINCT install_hash) AS installs
      FROM pings WHERE day BETWEEN ?1 AND ?2 GROUP BY ${column}`,
  ),
  ...COUNTERS.map(
    (column) => `SELECT '${column}' AS facet, entry.key AS value, SUM(entry.value) AS n,
        COUNT(DISTINCT CASE WHEN entry.value > 0 THEN pings.install_hash END) AS installs
      FROM pings, json_each(pings.${column}) AS entry WHERE pings.day BETWEEN ?1 AND ?2 GROUP BY entry.key`,
  ),
];

// v1 rows carry no configured flag; a run needs a configured model, so a run counts as one.
const FUNNEL = `SELECT COUNT(*) AS active, SUM(configured) AS configured, SUM(ran) AS ran, SUM(applied) AS applied
  FROM (
    SELECT MAX(COALESCE(extra.configured, 0) OR ping.runs > 0 OR ping.applies > 0) AS configured,
      MAX(ping.runs > 0 OR ping.applies > 0) AS ran,
      MAX(ping.applies > 0) AS applied
    FROM pings AS ping LEFT JOIN ping_extras AS extra USING (install_hash, day)
    WHERE ping.day BETWEEN ?1 AND ?2
    GROUP BY ping.install_hash
  )`;

const WEEK_OF = (column) => `date(${column}, 'weekday 0', '-6 days')`;

const WEEKS = `WITH firsts AS (
    SELECT install_hash, ${WEEK_OF("MIN(day)")} AS first_week FROM pings GROUP BY install_hash
  ), weekly AS (
    SELECT DISTINCT install_hash, ${WEEK_OF("day")} AS week FROM pings WHERE day BETWEEN ?1 AND ?2
  )
  SELECT week, SUM(first_week = week) AS new_installs, SUM(first_week < week) AS returning_installs
  FROM weekly JOIN firsts USING (install_hash) GROUP BY week`;

const RETENTION = `SELECT ${RETENTION_DAYS.map(
  (days) => `SUM(first_day <= date(?1, '-${days} days')) AS installs_${days},
    SUM(first_day <= date(?1, '-${days} days') AND last_day >= date(first_day, '+${days} days')) AS kept_${days}`,
).join(",\n    ")}
  FROM (SELECT MIN(day) AS first_day, MAX(day) AS last_day FROM pings GROUP BY install_hash)`;

// Only v2 rows report errors, so only their calls count towards the rate.
const TOOL_ERRORS = `WITH calls AS (
    SELECT ping.install_hash, entry.key AS tool, entry.value AS calls,
      COALESCE(json_extract(extra.tool_errors, '$.' || entry.key), 0) AS errors
    FROM pings AS ping
      JOIN ping_extras AS extra USING (install_hash, day)
      JOIN json_each(ping.tools) AS entry
    WHERE ping.day BETWEEN ?1 AND ?2
  )
  SELECT tool, SUM(calls) AS calls, SUM(errors) AS errors,
    COUNT(DISTINCT CASE WHEN errors > 0 THEN install_hash END) AS installs
  FROM calls GROUP BY tool`;

function json(status, body, headers = {}) {
  return new Response(JSON.stringify(body), { status, headers: { ...JSON_HEADERS, ...headers } });
}

function jsonError(status, message, headers = {}) {
  return json(status, { error: message }, headers);
}

function isJsonType(header) {
  return (header ?? "").split(";")[0].trim().toLowerCase() === JSON_TYPE;
}

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
  const installHash = await hashInstall(ping.install);
  const extras =
    ping.version >= 2
      ? env.DB.prepare(INSERT_EXTRAS).bind(...extrasRow(ping, installHash))
      : env.DB.prepare(DELETE_EXTRAS).bind(installHash, ping.day);
  await env.DB.batch([env.DB.prepare(INSERT_PING).bind(...pingRow(ping, installHash)), extras]);
  return new Response(null, { status: 204 });
}

async function computeStats(db, now) {
  const window = statsWindow(now);
  const [totals, days, funnel, weeks, retention, toolErrors, ...facets] = await db.batch([
    db.prepare(TOTALS).bind(window.recentSince, window.today),
    db.prepare(DAYS).bind(window.seriesSince, window.today),
    db.prepare(FUNNEL).bind(window.recentSince, window.today),
    db.prepare(WEEKS).bind(window.weeksSince, window.today),
    db.prepare(RETENTION).bind(window.today),
    db.prepare(TOOL_ERRORS).bind(window.recentSince, window.today),
    ...FACETS.map((sql) => db.prepare(sql).bind(window.recentSince, window.today)),
  ]);
  return shapeStats({
    generated: now.toISOString(),
    window,
    totals: totals.results[0],
    days: days.results,
    facets: facets.flatMap((facet) => facet.results),
    funnel: funnel.results[0],
    weeks: weeks.results,
    retention: retention.results[0],
    toolErrors: toolErrors.results,
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
