export const PING_VERSIONS = [1, 2, 3];
export const MAX_BODY_BYTES = 8192;
export const MAX_COUNT = 100000;
export const MAX_MAP_KEYS = 150;
// A day waits up to a week of local days for QGIS to start, and a local date is at most a day off UTC.
export const MAX_DAYS_BACK = 8;
export const MAX_DAYS_AHEAD = 1;
export const SERIES_DAYS = 90;
export const RECENT_DAYS = 30;
export const SERIES_WEEKS = 13;
export const RETENTION_DAYS = [7, 30];
export const MAX_VALUES_PER_FACET = 100;
// A value fewer installs reported could single one out, so it stays unpublished.
export const MIN_INSTALLS = 5;

export const OS_VALUES = ["macos", "windows", "linux", "other"];
export const PROVIDER_VALUES = ["local", "remote"];
export const DIALECT_VALUES = ["openai", "anthropic"];
export const FAMILY_VALUES = ["openai", "openrouter", "anthropic", "gemini", "deepseek", "mistral", "groq", "xai", "together", "fireworks", "moonshot", "qwen", "zhipu", "yandex", "nvidia", "huggingface", "cerebras", "perplexity", "azure", "ollama", "lmstudio", "other_local", "other_remote"];

const REQUEST_BUCKETS = ["r1", "r2", "r3_5", "r6_10", "r11_plus"];
// A v3 map may hold only these keys, and the stats list every one of them in this order.
export const DETAIL_MAPS = {
  outcomes: ["answered", "failed", "stopped", "limit"],
  modes: ["plan", "auto"],
  plans: ["shown", "cancelled", "undone", "auto"],
  session_requests: REQUEST_BUCKETS,
  to_apply: REQUEST_BUCKETS,
  steps: ["s0", "s1", "s2_3", "s4_7", "s8_15", "s16_plus"],
  durations: ["t0_10", "t10_30", "t30_60", "t60_180", "t180_plus"],
  tokens: ["k0_5", "k5_20", "k20_50", "k50_200", "k200_plus"],
};
export const DETAIL_COUNTS = ["retries", "checks", "sessions"];
export const ACTIVATION_STEPS = ["configured", "ran", "applied"];
export const ACTIVATION_BUCKETS = ["d0", "d1", "d2_7", "d8_plus", "never"];

export const DIMENSIONS = ["plugin", "qgis", "os", "locale", "provider", "dialect"];
export const COUNTERS = ["tools", "skills", "failures"];
export const EXTRA_COLUMNS = ["install_hash", "day", "configured", "tool_errors"];
export const DETAIL_COLUMNS = ["install_hash", "day", "family", ...DETAIL_COUNTS, ...Object.keys(DETAIL_MAPS)];

export const PING_COLUMNS = [
  "install_hash",
  "day",
  ...DIMENSIONS,
  "runs",
  "applies",
  ...COUNTERS,
];

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const DAY = /^(\d{4})-(\d{2})-(\d{2})$/;
const VERSION = /^[0-9A-Za-z._+-]{1,32}$/;
const LOCALE = /^[A-Za-z_-]{1,16}$/;
const MAP_KEY = /^[a-z][a-z0-9_]{0,48}$/;
const MS_PER_DAY = 86_400_000;
const ECHOED_KEY_CHARS = 40;

const V1_FIELDS = ["v", "install", "day", ...DIMENSIONS, "runs", "applies"];
const V2_FIELDS = [...V1_FIELDS, "configured"];
const V3_FIELDS = [...V2_FIELDS, "family", ...DETAIL_COUNTS];
const FIELDS = {
  1: { required: V1_FIELDS, known: new Set([...V1_FIELDS, ...COUNTERS]) },
  2: { required: V2_FIELDS, known: new Set([...V2_FIELDS, ...COUNTERS, "tool_errors"]) },
  3: { required: V3_FIELDS, known: new Set([...V3_FIELDS, ...COUNTERS, "tool_errors", ...Object.keys(DETAIL_MAPS)]) },
};

export class PingError extends Error {}

function fail(message) {
  throw new PingError(message);
}

function isPlainObject(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function matching(name, value, pattern) {
  if (typeof value !== "string" || !pattern.test(value)) fail(`${name} is malformed`);
  return value;
}

function oneOf(name, value, allowed) {
  if (!allowed.includes(value)) fail(`${name} must be one of ${allowed.join(", ")}`);
  return value;
}

function count(name, value) {
  if (!Number.isInteger(value) || value < 0 || value > MAX_COUNT) {
    fail(`${name} must be an integer from 0 to ${MAX_COUNT}`);
  }
  return value;
}

function counts(name, value) {
  if (value === undefined) return {};
  if (!isPlainObject(value)) fail(`${name} must be an object`);
  const entries = Object.entries(value);
  if (entries.length > MAX_MAP_KEYS) fail(`${name} has more than ${MAX_MAP_KEYS} keys`);
  for (const [key, number] of entries) {
    if (!MAP_KEY.test(key)) fail(`${name} has a malformed key`);
    count(`${name}.${key}`, number);
  }
  return Object.fromEntries(entries.sort(([a], [b]) => (a < b ? -1 : 1)));
}

function listed(name, value, keys) {
  if (value === undefined) return {};
  if (!isPlainObject(value)) fail(`${name} must be an object`);
  for (const [key, number] of Object.entries(value)) {
    if (!keys.includes(key)) fail(`${name} has an unknown key`);
    count(`${name}.${key}`, number);
  }
  return Object.fromEntries(keys.filter((key) => Object.hasOwn(value, key)).map((key) => [key, value[key]]));
}

function details(body) {
  const result = { family: oneOf("family", body.family, FAMILY_VALUES) };
  for (const name of DETAIL_COUNTS) result[name] = count(name, body[name]);
  for (const [name, keys] of Object.entries(DETAIL_MAPS)) result[name] = listed(name, body[name], keys);
  return result;
}

function dayStart(year, month, day) {
  const time = Date.UTC(year, month - 1, day);
  const date = new Date(time);
  const real = date.getUTCFullYear() === year && date.getUTCMonth() === month - 1 && date.getUTCDate() === day;
  return real ? time : null;
}

function reportedDay(value, now) {
  const match = typeof value === "string" ? DAY.exec(value) : null;
  if (!match) fail("day must be YYYY-MM-DD");
  const time = dayStart(Number(match[1]), Number(match[2]), Number(match[3]));
  if (time === null) fail("day is not a real date");
  const today = dayStart(now.getUTCFullYear(), now.getUTCMonth() + 1, now.getUTCDate());
  if (time < today - MAX_DAYS_BACK * MS_PER_DAY || time > today + MAX_DAYS_AHEAD * MS_PER_DAY) {
    fail("day is too far from the current date");
  }
  return value;
}

function flag(name, value) {
  if (typeof value !== "boolean") fail(`${name} must be true or false`);
  return value;
}

export function validatePing(body, now = new Date()) {
  if (!isPlainObject(body)) fail("body must be a JSON object");
  if (!Object.hasOwn(body, "v")) fail("missing field v");
  if (!PING_VERSIONS.includes(body.v)) fail(`v must be one of ${PING_VERSIONS.join(", ")}`);
  const fields = FIELDS[body.v];
  for (const key of Object.keys(body)) {
    if (!fields.known.has(key)) fail(`unknown field ${JSON.stringify(key.slice(0, ECHOED_KEY_CHARS))}`);
  }
  for (const key of fields.required) {
    if (!Object.hasOwn(body, key)) fail(`missing field ${key}`);
  }
  const ping = {
    version: body.v,
    install: matching("install", body.install, UUID).toLowerCase(),
    day: reportedDay(body.day, now),
    plugin: matching("plugin", body.plugin, VERSION),
    qgis: matching("qgis", body.qgis, VERSION),
    os: oneOf("os", body.os, OS_VALUES),
    locale: matching("locale", body.locale, LOCALE),
    provider: oneOf("provider", body.provider, PROVIDER_VALUES),
    dialect: oneOf("dialect", body.dialect, DIALECT_VALUES),
    runs: count("runs", body.runs),
    applies: count("applies", body.applies),
    tools: counts("tools", body.tools),
    skills: counts("skills", body.skills),
    failures: counts("failures", body.failures),
    configured: body.v >= 2 ? flag("configured", body.configured) : null,
    tool_errors: counts("tool_errors", body.tool_errors),
    details: body.v >= 3 ? details(body) : null,
  };
  for (const [tool, errors] of Object.entries(ping.tool_errors)) {
    if (errors > (Object.hasOwn(ping.tools, tool) ? ping.tools[tool] : 0)) fail(`tool_errors.${tool} is more than its calls`);
  }
  return ping;
}

// SHA-256 hex of the install id: the only form of it that is ever stored.
export async function hashInstall(install) {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(install));
  return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("");
}

export function pingRow(ping, installHash) {
  return PING_COLUMNS.map((column) => {
    if (column === "install_hash") return installHash;
    return COUNTERS.includes(column) ? JSON.stringify(ping[column]) : ping[column];
  });
}

export function extrasRow(ping, installHash) {
  return [installHash, ping.day, ping.configured ? 1 : 0, JSON.stringify(ping.tool_errors)];
}

export function detailsRow(ping, installHash) {
  return DETAIL_COLUMNS.map((column) => {
    if (column === "install_hash") return installHash;
    if (column === "day") return ping.day;
    return Object.hasOwn(DETAIL_MAPS, column) ? JSON.stringify(ping.details[column]) : ping.details[column];
  });
}

export function utcDay(date) {
  return date.toISOString().slice(0, 10);
}

export function shiftDay(day, offset) {
  return utcDay(new Date(Date.parse(`${day}T00:00:00Z`) + offset * MS_PER_DAY));
}

export function weekStart(day) {
  const weekday = (new Date(`${day}T00:00:00Z`).getUTCDay() + 6) % 7;
  return shiftDay(day, -weekday);
}

export function statsWindow(now) {
  const today = utcDay(now);
  const thisWeek = weekStart(today);
  return {
    today,
    recentSince: shiftDay(today, 1 - RECENT_DAYS),
    seriesSince: shiftDay(today, 1 - SERIES_DAYS),
    thisWeek,
    weeksSince: shiftDay(thisWeek, -7 * (SERIES_WEEKS - 1)),
  };
}

function number(value) {
  return Number(value) || 0;
}

export function fillDays(rows, window) {
  const byDay = new Map(rows.map((row) => [row.day, row]));
  const days = [];
  for (let day = window.seriesSince; day <= window.today; day = shiftDay(day, 1)) {
    const row = byDay.get(day);
    days.push({
      day,
      installs: number(row?.installs),
      runs: number(row?.runs),
      applies: number(row?.applies),
      sessions: number(row?.sessions),
      failed: number(row?.failed),
    });
  }
  return days;
}

function widelyReported(row) {
  return number(row.installs) >= MIN_INSTALLS;
}

export function rankFacet(rows, facet, field = "n") {
  const entries = rows
    .filter((row) => row.facet === facet && row.value !== null && row.value !== undefined && widelyReported(row))
    .map((row) => [String(row.value), number(row[field])])
    .sort(([a, x], [b, y]) => y - x || (a < b ? -1 : 1))
    .slice(0, MAX_VALUES_PER_FACET);
  // fromEntries defines own properties, so a value such as "__proto__" stays data.
  return Object.fromEntries(entries);
}

export function fillWeeks(rows, window) {
  const byWeek = new Map(rows.map((row) => [row.week, row]));
  const weeks = [];
  for (let week = window.weeksSince; week <= window.thisWeek; week = shiftDay(week, 7)) {
    const row = byWeek.get(week);
    weeks.push({ week, new: number(row?.new_installs), returning: number(row?.returning_installs) });
  }
  return weeks;
}

export function shapeFunnel(row) {
  return {
    active: number(row?.active),
    configured: number(row?.configured),
    ran: number(row?.ran),
    applied: number(row?.applied),
  };
}

export function shapeRetention(row) {
  return RETENTION_DAYS.map((days) => ({
    days,
    installs: number(row?.[`installs_${days}`]),
    kept: number(row?.[`kept_${days}`]),
  }));
}

export function rankToolErrors(rows) {
  const entries = rows
    .filter(widelyReported)
    .map((row) => [String(row.tool), { errors: number(row.errors), calls: number(row.calls) }])
    .filter(([, counts]) => counts.errors > 0)
    .sort(([a, x], [b, y]) => y.errors - x.errors || (a < b ? -1 : 1))
    .slice(0, MAX_VALUES_PER_FACET);
  return Object.fromEntries(entries);
}

export function shapeActivity(row) {
  return {
    installs: number(row?.installs),
    requests: number(row?.requests),
    ...Object.fromEntries(DETAIL_COUNTS.map((name) => [name, number(row?.[name])])),
    applies: number(row?.applies),
  };
}

export function shapeDetailSums(rows) {
  const sums = new Map(rows.map((row) => [`${row.map}.${row.key}`, number(row.n)]));
  return Object.fromEntries(
    Object.entries(DETAIL_MAPS).map(([name, keys]) => [
      name,
      Object.fromEntries(keys.map((key) => [key, sums.get(`${name}.${key}`) ?? 0])),
    ]),
  );
}

export function shapeFamilies(rows) {
  const entries = rows
    .filter((row) => row.family !== null && row.family !== undefined && widelyReported(row))
    .sort((a, b) => number(b.installs) - number(a.installs) || (a.family < b.family ? -1 : 1))
    .map((row) => [
      String(row.family),
      { installs: number(row.installs), runs: number(row.runs), failed: number(row.failed) },
    ]);
  return Object.fromEntries(entries);
}

export function shapeActivation(row) {
  const activation = { installs: number(row?.installs) };
  for (const step of ACTIVATION_STEPS) {
    activation[step] = Object.fromEntries(
      ACTIVATION_BUCKETS.map((bucket) => [bucket, number(row?.[`${step}_${bucket}`])]),
    );
  }
  return activation;
}

export function shapeStats({
  generated,
  window,
  totals,
  days,
  facets,
  funnel,
  weeks,
  retention,
  toolErrors,
  activity,
  detailSums,
  families,
  activation,
}) {
  const stats = {
    generated,
    installs_total: number(totals?.installs_total),
    installs_30d: number(totals?.installs_30d),
    days: fillDays(days, window),
    funnel: shapeFunnel(funnel),
    weeks: fillWeeks(weeks ?? [], window),
    retention: shapeRetention(retention),
    tool_errors: rankToolErrors(toolErrors ?? []),
  };
  for (const facet of [...DIMENSIONS, ...COUNTERS, "family"]) stats[facet] = rankFacet(facets, facet);
  stats.activity = shapeActivity(activity);
  Object.assign(stats, shapeDetailSums(detailSums ?? []));
  stats.families = shapeFamilies(families ?? []);
  stats.failure_installs = rankFacet(facets, "failures", "installs");
  stats.activation = shapeActivation(activation);
  return stats;
}
