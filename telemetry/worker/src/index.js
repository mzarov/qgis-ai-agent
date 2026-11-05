import {
  ACTIVATION_BUCKETS,
  ACTIVATION_STEPS,
  COUNTERS,
  DETAIL_COLUMNS,
  DETAIL_MAPS,
  DIMENSIONS,
  EXTRA_COLUMNS,
  MAX_BODY_BYTES,
  PING_COLUMNS,
  PingError,
  RETENTION_DAYS,
  detailsRow,
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
// While one request rebuilds, the rest serve the old snapshot; a failed rebuild is tried again after this.
const REBUILD_LEASE_SECONDS = 60;
const PREFLIGHT_MAX_AGE_SECONDS = 86400;
const UNKNOWN_ADDRESS = "unknown";

const INSERT_PING = `INSERT OR REPLACE INTO pings (${PING_COLUMNS.join(", ")})
  VALUES (${PING_COLUMNS.map(() => "?").join(", ")})`;

const INSERT_EXTRAS = `INSERT OR REPLACE INTO ping_extras (${EXTRA_COLUMNS.join(", ")})
  VALUES (${EXTRA_COLUMNS.map(() => "?").join(", ")})`;

const INSERT_DETAILS = `INSERT OR REPLACE INTO ping_details (${DETAIL_COLUMNS.join(", ")})
  VALUES (${DETAIL_COLUMNS.map(() => "?").join(", ")})`;

// An older resend replaces the pings row, so a newer row left beside it would describe another ping.
const DELETE_EXTRAS = "DELETE FROM ping_extras WHERE install_hash = ?1 AND day = ?2";
const DELETE_DETAILS = "DELETE FROM ping_details WHERE install_hash = ?1 AND day = ?2";

const READ_SNAPSHOT = "SELECT generated, body FROM stats_snapshot WHERE id = 1";
const WRITE_SNAPSHOT = "INSERT OR REPLACE INTO stats_snapshot (id, generated, body) VALUES (1, ?1, ?2)";
const CLAIM_SNAPSHOT = "UPDATE stats_snapshot SET generated = ?1 WHERE id = 1 AND generated = ?2";

const TOTALS = `SELECT
  (SELECT COUNT(DISTINCT install_hash) FROM pings) AS installs_total,
  (SELECT COUNT(DISTINCT install_hash) FROM pings WHERE day BETWEEN ?1 AND ?2) AS installs_30d`;

const DAYS = `SELECT ping.day, COUNT(*) AS installs, SUM(ping.runs) AS runs, SUM(ping.applies) AS applies,
    SUM(detail.sessions) AS sessions, SUM(json_extract(detail.outcomes, '$.failed')) AS failed
  FROM pings AS ping LEFT JOIN ping_details AS detail USING (install_hash, day)
  WHERE ping.day BETWEEN ?1 AND ?2 GROUP BY ping.day`;

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
  `SELECT 'family' AS facet, family AS value,
      COUNT(DISTINCT install_hash) AS n, COUNT(DISTINCT install_hash) AS installs
    FROM ping_details WHERE day BETWEEN ?1 AND ?2 GROUP BY family`,
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

// Only v2 rows report errors, so only their calls count; older rows may hold more errors than calls.
const TOOL_ERRORS = `WITH calls AS (
    SELECT ping.install_hash, entry.key AS tool, entry.value AS calls,
      MIN(COALESCE(json_extract(extra.tool_errors, '$.' || entry.key), 0), entry.value) AS errors
    FROM pings AS ping
      JOIN ping_extras AS extra USING (install_hash, day)
      JOIN json_each(ping.tools) AS entry
    WHERE ping.day BETWEEN ?1 AND ?2
  )
  SELECT tool, SUM(calls) AS calls, SUM(errors) AS errors,
    COUNT(DISTINCT CASE WHEN errors > 0 THEN install_hash END) AS installs
  FROM calls GROUP BY tool`;

const ACTIVITY = `SELECT COUNT(DISTINCT ping.install_hash) AS installs, SUM(ping.runs) AS requests,
    SUM(detail.retries) AS retries, SUM(detail.checks) AS checks, SUM(detail.sessions) AS sessions,
    SUM(ping.applies) AS applies
  FROM pings AS ping JOIN ping_details AS detail USING (install_hash, day)
  WHERE ping.day BETWEEN ?1 AND ?2`;

const DETAIL_SUMS = Object.keys(DETAIL_MAPS).map(
  (column) => `SELECT '${column}' AS map, entry.key AS key, SUM(entry.value) AS n
    FROM ping_details, json_each(ping_details.${column}) AS entry
    WHERE ping_details.day BETWEEN ?1 AND ?2 GROUP BY entry.key`,
);

const FAMILIES = `SELECT family, COUNT(DISTINCT install_hash) AS installs,
    SUM((SELECT SUM(entry.value) FROM json_each(outcomes) AS entry)) AS runs,
    SUM(json_extract(outcomes, '$.failed')) AS failed
  FROM ping_details WHERE day BETWEEN ?1 AND ?2 GROUP BY family`;

// The same steps as FUNNEL, timed from an install's first day.
const ACTIVATION_REACHED = {
  configured: "COALESCE(extra.configured, 0) OR ping.runs > 0 OR ping.applies > 0",
  ran: "ping.runs > 0 OR ping.applies > 0",
  applied: "ping.applies > 0",
};
const ACTIVATION_WAIT = { d0: "= 0", d1: "= 1", d2_7: "BETWEEN 2 AND 7", d8_plus: ">= 8", never: "IS NULL" };

const reachedDay = (step) => `MIN(CASE WHEN ${ACTIVATION_REACHED[step]} THEN ping.day END) AS ${step}_day`;
const waitCount = (step, bucket) =>
  `COUNT(CASE WHEN julianday(${step}_day) - julianday(first_day) ${ACTIVATION_WAIT[bucket]} THEN 1 END)`;

const ACTIVATION = `WITH firsts AS (
    SELECT MIN(ping.day) AS first_day, ${ACTIVATION_STEPS.map(reachedDay).join(", ")}
    FROM pings AS ping LEFT JOIN ping_extras AS extra USING (install_hash, day)
    WHERE ping.day <= ?2
    GROUP BY ping.install_hash
    HAVING MIN(ping.day) >= ?1
  )
  SELECT COUNT(*) AS installs,
    ${ACTIVATION_STEPS.flatMap((step) =>
      ACTIVATION_BUCKETS.map((bucket) => `${waitCount(step, bucket)} AS ${step}_${bucket}`),
    ).join(",\n    ")}
  FROM firsts`;

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

// The address only picks the limiter's counter: it is never stored or logged. Local runs have no limiter.
async function overLimit(request, env) {
  if (!env.PING_LIMITER) return false;
  const key = request.headers.get("cf-connecting-ip") || UNKNOWN_ADDRESS;
  const { success } = await env.PING_LIMITER.limit({ key });
  return !success;
}

async function handlePing(request, env, now) {
  if (await overLimit(request, env)) return jsonError(429, "too many pings from this address; try later");
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
  const details =
    ping.version >= 3
      ? env.DB.prepare(INSERT_DETAILS).bind(...detailsRow(ping, installHash))
      : env.DB.prepare(DELETE_DETAILS).bind(installHash, ping.day);
  await env.DB.batch([env.DB.prepare(INSERT_PING).bind(...pingRow(ping, installHash)), extras, details]);
  return new Response(null, { status: 204 });
}

async function computeStats(db, now) {
  const window = statsWindow(now);
  const recent = (sql) => db.prepare(sql).bind(window.recentSince, window.today);
  const [totals, days, funnel, weeks, retention, toolErrors, activity, families, activation, ...rest] =
    await db.batch([
      recent(TOTALS),
      db.prepare(DAYS).bind(window.seriesSince, window.today),
      recent(FUNNEL),
      db.prepare(WEEKS).bind(window.weeksSince, window.today),
      db.prepare(RETENTION).bind(window.today),
      recent(TOOL_ERRORS),
      recent(ACTIVITY),
      recent(FAMILIES),
      db.prepare(ACTIVATION).bind(window.seriesSince, window.today),
      ...DETAIL_SUMS.map(recent),
      ...FACETS.map(recent),
    ]);
  const detailSums = rest.slice(0, DETAIL_SUMS.length);
  const facets = rest.slice(DETAIL_SUMS.length);
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
    activity: activity.results[0],
    detailSums: detailSums.flatMap((sums) => sums.results),
    families: families.results,
    activation: activation.results[0],
  });
}

function statsResponse(body, maxAge) {
  return new Response(body, {
    headers: {
      ...JSON_HEADERS,
      "access-control-allow-origin": "*",
      "cache-control": `public, max-age=${maxAge}`,
    },
  });
}

// Moving the stale snapshot's time to a lease's end claims the rebuild: only one UPDATE matches the old time.
async function claimRebuild(db, snapshot, now) {
  const leaseEnd = new Date(now.getTime() - (STATS_TTL_SECONDS - REBUILD_LEASE_SECONDS) * 1000).toISOString();
  const claimed = await db.prepare(CLAIM_SNAPSHOT).bind(leaseEnd, snapshot.generated).run();
  return claimed.meta?.changes === 1;
}

async function handleStats(request, env, now) {
  const snapshot = await env.DB.prepare(READ_SNAPSHOT).first();
  const age = snapshot ? (now.getTime() - Date.parse(snapshot.generated)) / 1000 : Number.NaN;
  if (age >= 0 && age < STATS_TTL_SECONDS) return statsResponse(snapshot.body, Math.floor(STATS_TTL_SECONDS - age));
  let stats;
  try {
    if (snapshot && !(await claimRebuild(env.DB, snapshot, now))) {
      return statsResponse(snapshot.body, REBUILD_LEASE_SECONDS);
    }
    stats = await computeStats(env.DB, now);
  } catch (error) {
    if (!snapshot) throw error;
    console.error("usage stats were not rebuilt; the last snapshot is served:", error?.message);
    return statsResponse(snapshot.body, REBUILD_LEASE_SECONDS);
  }
  const body = JSON.stringify(stats);
  try {
    await env.DB.prepare(WRITE_SNAPSHOT).bind(stats.generated, body).run();
  } catch (error) {
    console.error("usage stats snapshot was not saved:", error?.message);
  }
  return statsResponse(body, STATS_TTL_SECONDS);
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
