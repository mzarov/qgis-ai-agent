import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { DatabaseSync } from "node:sqlite";
import { beforeEach, describe, it } from "node:test";

import { handle } from "../src/index.js";
import { MIN_INSTALLS, hashInstall } from "../src/payload.js";

const SCHEMA = readFileSync(new URL("../schema.sql", import.meta.url), "utf8");
const BASE = "https://ai-agent-usage.example.workers.dev";
const NOW = new Date("2026-10-17T12:00:00Z");
const MINUTE = 60_000;
const INSTALLS = {
  a: "3f2b8c1e-9a4d-4e6f-8b2a-1c3d5e7f9a0b",
  b: "7d1e2f3a-4b5c-4d6e-9f80-a1b2c3d4e5f6",
  c: "0a1b2c3d-4e5f-4a6b-8c7d-9e0f1a2b3c4d",
  d: "c4d5e6f7-0819-4a2b-bc3d-4e5f60718293",
  e: "5e6f7081-92a3-4b4c-8d5e-6f708192a3b4",
};
function crowd(count, from = 0) {
  return Array.from({ length: count }, (_, i) => `00000000-0000-4000-8000-${String(from + i).padStart(12, "0")}`);
}
// The pings table as the first deploy created it, before ping_extras existed.
const FIRST_SCHEMA = `CREATE TABLE pings (
  install_hash TEXT NOT NULL, day TEXT NOT NULL, plugin TEXT NOT NULL, qgis TEXT NOT NULL,
  os TEXT NOT NULL, locale TEXT NOT NULL, provider TEXT NOT NULL, dialect TEXT NOT NULL,
  runs INTEGER NOT NULL, applies INTEGER NOT NULL, tools TEXT NOT NULL DEFAULT '{}',
  skills TEXT NOT NULL DEFAULT '{}', failures TEXT NOT NULL DEFAULT '{}',
  PRIMARY KEY (install_hash, day)
)`;

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

function ping2(install, day, overrides = {}) {
  return ping(install, day, { v: 2, configured: true, ...overrides });
}

function noon(day) {
  return new Date(`${day}T12:00:00Z`);
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

  it("adds the v2 table to the first database without touching its rows", async () => {
    sqlite = new DatabaseSync(":memory:");
    sqlite.exec(FIRST_SCHEMA);
    sqlite
      .prepare("INSERT INTO pings VALUES (?, ?, '0.4.0', '4.2.1', 'macos', 'en', 'remote', 'openai', 2, 1, ?, '{}', '{}')")
      .run(await hashInstall(INSTALLS.a), "2026-10-16", '{"run_python":3}');
    const before = sqlite.prepare("SELECT * FROM pings").all();
    sqlite.exec(SCHEMA);
    sqlite.exec(SCHEMA);
    env = { DB: d1(sqlite) };
    assert.deepEqual(sqlite.prepare("SELECT * FROM pings").all(), before);
    assert.equal((await send(ping2(INSTALLS.b, "2026-10-17"))).status, 204);
    const body = JSON.parse((await stats()).text);
    assert.deepEqual(body.funnel, { active: 2, configured: 2, ran: 2, applied: 1 });
    assert.equal(body.installs_total, 2);
  });

  it("stores the v2 fields beside the ping and none for a v1 ping", async () => {
    await send(ping2(INSTALLS.a, "2026-10-17", { configured: false, tool_errors: { run_python: 2 } }));
    await send(ping(INSTALLS.b, "2026-10-17"));
    const extras = sqlite.prepare("SELECT * FROM ping_extras").all();
    assert.deepEqual(
      extras.map((row) => ({ ...row })),
      [{ install_hash: await hashInstall(INSTALLS.a), day: "2026-10-17", configured: 0, tool_errors: '{"run_python":2}' }],
    );
    assert.equal(sqlite.prepare("SELECT COUNT(*) AS n FROM pings").get().n, 2);
  });

  it("drops the v2 fields when a v1 ping replaces the day", async () => {
    await send(ping2(INSTALLS.a, "2026-10-17", { tool_errors: { run_python: 1 } }));
    await send(ping(INSTALLS.a, "2026-10-17"));
    assert.equal(sqlite.prepare("SELECT COUNT(*) AS n FROM ping_extras").get().n, 0);
  });

  it("counts the funnel, the weeks, retention and tool errors from the stored days", async () => {
    // a: first seen in August, back in October with a configured model, a run and an apply.
    await send(ping2(INSTALLS.a, "2026-08-01"), noon("2026-08-01"));
    await send(
      ping2(INSTALLS.a, "2026-10-16", {
        runs: 2,
        applies: 1,
        tools: { run_python: 4, inspect_project: 2 },
        tool_errors: { run_python: 1 },
      }),
    );
    // b: configured, never ran. c: loaded the plugin without a model.
    await send(ping2(INSTALLS.b, "2026-10-16", { runs: 0 }));
    await send(ping2(INSTALLS.c, "2026-10-15", { runs: 0, configured: false }));
    // d: a 0.4.0 client that ran; its calls have no error counts.
    await send(ping(INSTALLS.d, "2026-10-10", { runs: 3, tools: { run_python: 10 } }), noon("2026-10-10"));
    // e: one day in September, outside the 30 days.
    await send(ping(INSTALLS.e, "2026-09-01", { runs: 0 }), noon("2026-09-01"));

    const body = JSON.parse((await stats()).text);
    assert.deepEqual(body.funnel, { active: 4, configured: 3, ran: 2, applied: 1 });
    assert.deepEqual(
      body.weeks.filter((week) => week.new || week.returning),
      [
        { week: "2026-07-27", new: 1, returning: 0 },
        { week: "2026-08-31", new: 1, returning: 0 },
        { week: "2026-10-05", new: 1, returning: 0 },
        { week: "2026-10-12", new: 2, returning: 1 },
      ],
    );
    assert.deepEqual(body.retention, [
      { days: 7, installs: 3, kept: 1 },
      { days: 30, installs: 2, kept: 1 },
    ]);
    assert.deepEqual(body.tool_errors, {});
    assert.deepEqual(body.tools, {});
  });

  it("counts tool errors against the calls of v2 pings", async () => {
    for (const install of crowd(MIN_INSTALLS)) {
      await send(ping2(install, "2026-10-16", { tools: { run_python: 4, inspect_project: 2 }, tool_errors: { run_python: 1 } }));
    }
    await send(ping(INSTALLS.d, "2026-10-16", { tools: { run_python: 10 } }));
    const body = JSON.parse((await stats()).text);
    assert.deepEqual(body.tool_errors, { run_python: { errors: 5, calls: 20 } });
    assert.deepEqual(body.tools, { run_python: 30, inspect_project: 10 });
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
    const many = crowd(MIN_INSTALLS);
    await send(ping(INSTALLS.d, "2026-01-10"), new Date("2026-01-10T12:00:00Z"));
    await send(ping(INSTALLS.c, "2026-08-01"), new Date("2026-08-01T12:00:00Z"));
    for (const install of many) {
      await send(
        ping(install, "2026-10-16", {
          plugin: "0.3.0",
          runs: 4,
          applies: 1,
          tools: { inspect_project: 2, run_python: 1 },
          skills: { style: 1 },
        }),
      );
      await send(
        ping(install, "2026-10-17", {
          runs: 3,
          applies: 2,
          tools: { inspect_project: 5 },
          skills: { style: 2 },
          failures: { timeout: 1 },
        }),
      );
    }
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
    assert.equal(body.installs_total, 8);
    assert.equal(body.installs_30d, 6);
    assert.equal(body.days.length, 90);
    assert.deepEqual(body.days.at(-1), { day: "2026-10-17", installs: 5, runs: 15, applies: 10 });
    assert.deepEqual(body.days.at(-2), { day: "2026-10-16", installs: 6, runs: 21, applies: 5 });
    assert.deepEqual(
      body.days.find((day) => day.day === "2026-08-01"),
      { day: "2026-08-01", installs: 1, runs: 1, applies: 0 },
    );
    assert.deepEqual(body.plugin, { "0.4.0": 6, "0.3.0": 5 });
    assert.deepEqual(body.qgis, { "4.2.1": 5 });
    assert.deepEqual(body.os, { macos: 5 });
    assert.deepEqual(body.locale, { en: 5 });
    assert.deepEqual(body.provider, { remote: 5 });
    assert.deepEqual(body.dialect, { openai: 5 });
    assert.deepEqual(body.tools, { inspect_project: 36, run_python: 5 });
    assert.deepEqual(body.skills, { style: 15 });
    assert.deepEqual(body.failures, { timeout: 5 });

    for (const install of [...Object.values(INSTALLS), ...many]) {
      assert.equal(text.includes(install), false);
      assert.equal(text.includes(await hashInstall(install)), false);
    }
    assert.doesNotMatch(text, /[0-9a-f]{32}/);
  });

  it("publishes a value only once five installs reported it", async () => {
    const rare = {
      qgis: "4.1.0",
      locale: "eu",
      skills: { acme_parcels: 1 },
      tools: { acme_tool: 3, run_python: 2 },
      tool_errors: { run_python: 1 },
    };
    for (const install of crowd(MIN_INSTALLS - 1)) await send(ping2(install, "2026-10-17", rare));
    await send(ping2(INSTALLS.a, "2026-10-17", { tools: { acme_tool: 0 }, skills: { acme_parcels: 0 } }));
    let body = JSON.parse((await stats()).text);
    for (const facet of ["qgis", "locale", "skills", "tools", "tool_errors"]) assert.deepEqual(body[facet], {}, facet);

    await send(ping2(INSTALLS.b, "2026-10-17", rare));
    body = JSON.parse((await stats(new Date(NOW.getTime() + 61 * MINUTE))).text);
    assert.equal(body.qgis["4.1.0"], 5);
    assert.equal(body.locale.eu, 5);
    assert.equal(body.skills.acme_parcels, 5);
    assert.equal(body.tools.acme_tool, 15);
    assert.deepEqual(body.tool_errors, { run_python: { errors: 5, calls: 10 } });
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
