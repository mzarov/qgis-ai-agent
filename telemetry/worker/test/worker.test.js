import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { DatabaseSync } from "node:sqlite";
import { beforeEach, describe, it } from "node:test";

import { handle } from "../src/index.js";
import { hashInstall } from "../src/payload.js";

const SCHEMA = readFileSync(new URL("../schema.sql", import.meta.url), "utf8");
const BASE = "https://ai-agent-usage.example.workers.dev";
const NOW = new Date("2026-10-17T12:00:00Z");
const MINUTE = 60_000;
const INSTALLS = {
  a: "3f2b8c1e-9a4d-4e6f-8b2a-1c3d5e7f9a0b",
  b: "7d1e2f3a-4b5c-4d6e-9f80-a1b2c3d4e5f6",
  c: "0a1b2c3d-4e5f-4a6b-8c7d-9e0f1a2b3c4d",
  d: "c4d5e6f7-0819-4a2b-bc3d-4e5f60718293",
};

function d1(database) {
  class Statement {
    constructor(sql, params = []) {
      this.sql = sql;
      this.params = params;
    }
    bind(...params) {
      return new Statement(this.sql, params);
    }
    async run() {
      database.prepare(this.sql).run(...this.params);
      return { success: true };
    }
    async all() {
      return { success: true, results: database.prepare(this.sql).all(...this.params) };
    }
    async first() {
      return database.prepare(this.sql).get(...this.params) ?? null;
    }
  }
  return {
    prepare: (sql) => new Statement(sql),
    batch: (statements) => Promise.all(statements.map((statement) => statement.all())),
  };
}

function ping(install, day, overrides = {}) {
  return {
    v: 1,
    install,
    day,
    plugin: "0.4.0",
    qgis: "4.2.1",
    os: "macos",
    locale: "en",
    provider: "remote",
    dialect: "openai",
    runs: 1,
    applies: 0,
    ...overrides,
  };
}

function post(body, headers = { "content-type": "application/json" }) {
  const text = typeof body === "string" ? body : JSON.stringify(body);
  return new Request(`${BASE}/v1/ping`, { method: "POST", headers, body: text });
}

describe("usage worker", () => {
  let sqlite;
  let env;

  beforeEach(() => {
    sqlite = new DatabaseSync(":memory:");
    sqlite.exec(SCHEMA);
    env = { DB: d1(sqlite) };
  });

  async function send(body, now = NOW) {
    return handle(post(body), env, now);
  }

  async function stats(now = NOW) {
    const response = await handle(new Request(`${BASE}/v1/stats`), env, now);
    assert.equal(response.status, 200);
    return { response, text: await response.text() };
  }

  it("applies the schema idempotently", () => {
    sqlite.exec(SCHEMA);
  });

  it("stores a ping under the hash of the install id", async () => {
    const response = await send(ping(INSTALLS.a, "2026-10-17", { tools: { inspect_project: 5 } }));
    assert.equal(response.status, 204);
    const rows = sqlite.prepare("SELECT * FROM pings").all();
    assert.equal(rows.length, 1);
    assert.equal(rows[0].install_hash, await hashInstall(INSTALLS.a));
    assert.equal(rows[0].tools, '{"inspect_project":5}');
    assert.equal(rows[0].skills, "{}");
    assert.equal(JSON.stringify(rows).includes(INSTALLS.a), false);
  });

  it("replaces the row when a client resends the same day", async () => {
    await send(ping(INSTALLS.a, "2026-10-17", { runs: 2 }));
    assert.equal((await send(ping(INSTALLS.a.toUpperCase(), "2026-10-17", { runs: 5 }))).status, 204);
    await send(ping(INSTALLS.a, "2026-10-16", { runs: 1 }));
    const rows = sqlite.prepare("SELECT day, runs FROM pings ORDER BY day").all();
    assert.deepEqual(
      rows.map((row) => [row.day, row.runs]),
      [
        ["2026-10-16", 1],
        ["2026-10-17", 5],
      ],
    );
  });

  it("accepts a charset on the JSON content type", async () => {
    const response = await handle(
      post(ping(INSTALLS.a, "2026-10-17"), { "content-type": "Application/JSON; charset=utf-8" }),
      env,
      NOW,
    );
    assert.equal(response.status, 204);
  });

  it("refuses other content types", async () => {
    for (const headers of [{ "content-type": "text/plain" }, {}]) {
      const response = await handle(post(ping(INSTALLS.a, "2026-10-17"), headers), env, NOW);
      assert.equal(response.status, 415);
      assert.match((await response.json()).error, /application\/json/);
    }
  });

  it("refuses a body over 4096 bytes, declared or streamed", async () => {
    const big = JSON.stringify({ ...ping(INSTALLS.a, "2026-10-17"), padding: "x".repeat(5000) });
    const declared = post(big, { "content-type": "application/json", "content-length": String(big.length) });
    assert.equal((await handle(declared, env, NOW)).status, 413);
    assert.equal((await send(big)).status, 413);
    assert.equal(sqlite.prepare("SELECT COUNT(*) AS n FROM pings").get().n, 0);
  });

  it("answers 400 with a short JSON error for a broken or invalid ping", async () => {
    for (const body of ["{", "", "[1]", JSON.stringify(ping(INSTALLS.a, "2026-10-17", { os: "beos" }))]) {
      const response = await send(body);
      assert.equal(response.status, 400, body);
      assert.match(response.headers.get("content-type"), /^application\/json/);
      const { error } = await response.json();
      assert.equal(typeof error, "string");
      assert.ok(error.length < 120, error);
    }
    assert.equal(sqlite.prepare("SELECT COUNT(*) AS n FROM pings").get().n, 0);
  });

  it("checks the day against the server date", async () => {
    assert.equal((await send(ping(INSTALLS.a, "2026-10-09"))).status, 400);
    assert.equal((await send(ping(INSTALLS.a, "2026-10-09"), new Date("2026-10-11T00:00:00Z"))).status, 204);
  });

  it("routes only the documented methods and paths", async () => {
    const getPing = await handle(new Request(`${BASE}/v1/ping`), env, NOW);
    assert.equal(getPing.status, 405);
    assert.equal(getPing.headers.get("allow"), "POST");
    const postStats = await handle(new Request(`${BASE}/v1/stats`, { method: "POST" }), env, NOW);
    assert.equal(postStats.status, 405);
    const oddMethod = await handle(new Request(`${BASE}/v1/ping`, { method: "constructor" }), env, NOW);
    assert.equal(oddMethod.status, 405);
    assert.equal((await handle(new Request(`${BASE}/v1/pings`), env, NOW)).status, 404);
  });

  it("points the root at the dashboard in one line of plain text", async () => {
    const response = await handle(new Request(`${BASE}/`), env, NOW);
    assert.equal(response.status, 200);
    assert.match(response.headers.get("content-type"), /^text\/plain/);
    const text = await response.text();
    assert.match(text, /^[^\n]*https:\/\/mzarov\.github\.io\/qgis-ai-agent\/usage-stats\/\n$/);
  });

  it("answers a CORS preflight for the stats", async () => {
    const response = await handle(new Request(`${BASE}/v1/stats`, { method: "OPTIONS" }), env, NOW);
    assert.equal(response.status, 204);
    assert.equal(response.headers.get("access-control-allow-origin"), "*");
  });

  it("publishes aggregates and nothing per install", async () => {
    await send(ping(INSTALLS.d, "2026-01-10"), new Date("2026-01-10T12:00:00Z"));
    await send(ping(INSTALLS.c, "2026-08-01"), new Date("2026-08-01T12:00:00Z"));
    await send(
      ping(INSTALLS.a, "2026-10-16", {
        plugin: "0.3.0",
        runs: 4,
        applies: 1,
        tools: { inspect_project: 2, run_python: 1 },
        skills: { style: 1 },
      }),
    );
    await send(
      ping(INSTALLS.a, "2026-10-17", {
        runs: 3,
        applies: 2,
        tools: { inspect_project: 5 },
        skills: { style: 2 },
        failures: { timeout: 1 },
      }),
    );
    await send(
      ping(INSTALLS.b, "2026-10-16", {
        qgis: "4.0.0",
        os: "windows",
        locale: "ru",
        provider: "local",
        dialect: "anthropic",
        tools: { inspect_project: 1 },
      }),
    );

    const { response, text } = await stats();
    assert.equal(response.headers.get("access-control-allow-origin"), "*");
    assert.equal(response.headers.get("cache-control"), "public, max-age=3600");
    const body = JSON.parse(text);
    assert.equal(body.generated, NOW.toISOString());
    assert.equal(body.installs_total, 4);
    assert.equal(body.installs_30d, 2);
    assert.equal(body.days.length, 90);
    assert.deepEqual(body.days.at(-1), { day: "2026-10-17", installs: 1, runs: 3, applies: 2 });
    assert.deepEqual(body.days.at(-2), { day: "2026-10-16", installs: 2, runs: 5, applies: 1 });
    assert.deepEqual(
      body.days.find((day) => day.day === "2026-08-01"),
      { day: "2026-08-01", installs: 1, runs: 1, applies: 0 },
    );
    assert.deepEqual(body.plugin, { "0.4.0": 2, "0.3.0": 1 });
    assert.deepEqual(body.qgis, { "4.0.0": 1, "4.2.1": 1 });
    assert.deepEqual(body.os, { macos: 1, windows: 1 });
    assert.deepEqual(body.locale, { en: 1, ru: 1 });
    assert.deepEqual(body.provider, { local: 1, remote: 1 });
    assert.deepEqual(body.dialect, { anthropic: 1, openai: 1 });
    assert.deepEqual(body.tools, { inspect_project: 8, run_python: 1 });
    assert.deepEqual(body.skills, { style: 3 });
    assert.deepEqual(body.failures, { timeout: 1 });

    for (const install of Object.values(INSTALLS)) {
      assert.equal(text.includes(install), false);
      assert.equal(text.includes(await hashInstall(install)), false);
    }
    assert.doesNotMatch(text, /[0-9a-f]{32}/);
  });

  it("serves the hourly snapshot until it expires", async () => {
    await send(ping(INSTALLS.a, "2026-10-17"));
    const first = await stats();
    await send(ping(INSTALLS.b, "2026-10-17"));

    const cached = await stats(new Date(NOW.getTime() + 10 * MINUTE));
    assert.equal(cached.text, first.text);
    assert.equal(cached.response.headers.get("cache-control"), "public, max-age=3000");

    const fresh = await stats(new Date(NOW.getTime() + 61 * MINUTE));
    assert.equal(JSON.parse(fresh.text).installs_30d, 2);
    assert.equal(fresh.response.headers.get("cache-control"), "public, max-age=3600");
  });
});
