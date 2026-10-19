export const PING_VERSION = 1;
export const MAX_BODY_BYTES = 4096;
export const MAX_COUNT = 100000;
export const MAX_MAP_KEYS = 150;
// A client's local day may sit a day off UTC, and it may resend yesterday's ping after a restart.
export const MAX_DAY_SKEW = 2;
export const SERIES_DAYS = 90;
export const RECENT_DAYS = 30;
export const MAX_VALUES_PER_FACET = 100;

export const OS_VALUES = ["macos", "windows", "linux", "other"];
export const PROVIDER_VALUES = ["local", "remote"];
export const DIALECT_VALUES = ["openai", "anthropic"];

export const DIMENSIONS = ["plugin", "qgis", "os", "locale", "provider", "dialect"];
export const COUNTERS = ["tools", "skills", "failures"];

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

const REQUIRED_FIELDS = ["v", "install", "day", ...DIMENSIONS, "runs", "applies"];
const KNOWN_FIELDS = new Set([...REQUIRED_FIELDS, ...COUNTERS]);

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
  if (Math.abs(time - today) > MAX_DAY_SKEW * MS_PER_DAY) fail("day is too far from the current date");
  return value;
}

export function validatePing(body, now = new Date()) {
  if (!isPlainObject(body)) fail("body must be a JSON object");
  for (const key of Object.keys(body)) {
    if (!KNOWN_FIELDS.has(key)) fail(`unknown field ${JSON.stringify(key.slice(0, ECHOED_KEY_CHARS))}`);
  }
  for (const key of REQUIRED_FIELDS) {
    if (!Object.hasOwn(body, key)) fail(`missing field ${key}`);
  }
  if (body.v !== PING_VERSION) fail(`v must be ${PING_VERSION}`);
  return {
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
  };
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

export function utcDay(date) {
  return date.toISOString().slice(0, 10);
}

export function shiftDay(day, offset) {
  return utcDay(new Date(Date.parse(`${day}T00:00:00Z`) + offset * MS_PER_DAY));
}

export function statsWindow(now) {
  const today = utcDay(now);
  return {
    today,
    recentSince: shiftDay(today, 1 - RECENT_DAYS),
    seriesSince: shiftDay(today, 1 - SERIES_DAYS),
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
    days.push({ day, installs: number(row?.installs), runs: number(row?.runs), applies: number(row?.applies) });
  }
  return days;
}

export function rankFacet(rows, facet) {
  const entries = rows
    .filter((row) => row.facet === facet && row.value !== null && row.value !== undefined)
    .map((row) => [String(row.value), number(row.n)])
    .sort(([a, x], [b, y]) => y - x || (a < b ? -1 : 1))
    .slice(0, MAX_VALUES_PER_FACET);
  // fromEntries defines own properties, so a value such as "__proto__" stays data.
  return Object.fromEntries(entries);
}

export function shapeStats({ generated, window, totals, days, facets }) {
  const stats = {
    generated,
    installs_total: number(totals?.installs_total),
    installs_30d: number(totals?.installs_30d),
    days: fillDays(days, window),
  };
  for (const facet of [...DIMENSIONS, ...COUNTERS]) stats[facet] = rankFacet(facets, facet);
  return stats;
}
