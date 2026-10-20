import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { describe, it } from "node:test";

import {
  MAX_MAP_KEYS,
  MAX_VALUES_PER_FACET,
  MIN_INSTALLS,
  PING_COLUMNS,
  PingError,
  SERIES_DAYS,
  SERIES_WEEKS,
  extrasRow,
  fillDays,
  fillWeeks,
  hashInstall,
  pingRow,
  rankFacet,
  rankToolErrors,
  shapeRetention,
  shapeStats,
  statsWindow,
  validatePing,
  weekStart,
} from "../src/payload.js";

const NOW = new Date("2026-10-17T12:00:00Z");
const INSTALL = "3f2b8c1e-9a4d-4e6f-8b2a-1c3d5e7f9a0b";

function ping(overrides = {}) {
  return {
    v: 1,
    install: INSTALL,
    day: "2026-10-17",
    plugin: "0.4.0",
    qgis: "4.2.1",
    os: "macos",
    locale: "en",
    provider: "remote",
    dialect: "openai",
    runs: 3,
    applies: 2,
    failures: { timeout: 1 },
    tools: { run_python: 1, inspect_project: 5 },
    skills: { style: 2 },
    ...overrides,
  };
}

function without(field) {
  const body = ping();
  delete body[field];
  return body;
}

function rejects(body, fragment) {
  assert.throws(
    () => validatePing(body, NOW),
    (error) => error instanceof PingError && error.message.includes(fragment),
    `expected an error mentioning ${JSON.stringify(fragment)}`,
  );
}

describe("validatePing", () => {
  it("accepts the contract example and normalizes it", () => {
    const result = validatePing(ping({ install: INSTALL.toUpperCase() }), NOW);
    assert.equal(result.install, INSTALL);
    assert.deepEqual(Object.keys(result.tools), ["inspect_project", "run_python"]);
    assert.equal(result.runs, 3);
    assert.equal("v" in result, false);
  });

  it("lets an install that called nothing omit the counter maps", () => {
    const body = ping();
    delete body.tools;
    delete body.skills;
    delete body.failures;
    const result = validatePing(body, NOW);
    assert.deepEqual([result.tools, result.skills, result.failures], [{}, {}, {}]);
  });

  it("accepts every listed os, provider and dialect", () => {
    for (const os of ["macos", "windows", "linux", "other"]) validatePing(ping({ os }), NOW);
    for (const provider of ["local", "remote"]) validatePing(ping({ provider }), NOW);
    for (const dialect of ["openai", "anthropic"]) validatePing(ping({ dialect }), NOW);
  });

  it("accepts a day up to eight days back and one ahead of the server date", () => {
    for (const day of ["2026-10-09", "2026-10-18"]) validatePing(ping({ day }), NOW);
  });

  it("accepts the week-old day of a client west of UTC", () => {
    // 20:00 on 2026-10-16 at UTC-10: the pending 2026-10-09 is seven days old there.
    validatePing(ping({ day: "2026-10-09" }), new Date("2026-10-17T06:00:00Z"));
  });

  it("accepts the limits themselves", () => {
    validatePing(ping({ plugin: "1".repeat(32), locale: "a".repeat(16), runs: 100000, applies: 0 }), NOW);
    validatePing(ping({ tools: { [`a${"b".repeat(48)}`]: 0 } }), NOW);
    const full = Object.fromEntries(Array.from({ length: MAX_MAP_KEYS }, (_, i) => [`tool_${i}`, 1]));
    validatePing(ping({ tools: full }), NOW);
  });

  it("rejects a body that is not an object", () => {
    for (const body of [null, [], "ping", 1]) rejects(body, "JSON object");
  });

  it("rejects unknown and missing fields", () => {
    rejects(ping({ ip: "1.2.3.4" }), "unknown field");
    for (const field of ["v", "install", "day", "plugin", "qgis", "os", "locale", "provider", "dialect", "runs"]) {
      rejects(without(field), `missing field ${field}`);
    }
    rejects(without("applies"), "missing field applies");
  });

  it("rejects another contract version", () => {
    for (const v of [3, "1", "2", 0, null]) rejects(ping({ v }), "v must be 1 or 2");
  });

  it("accepts a v2 ping and carries its new fields", () => {
    const result = validatePing(ping({ v: 2, configured: true, tool_errors: { run_python: 1 } }), NOW);
    assert.equal(result.version, 2);
    assert.equal(result.configured, true);
    assert.deepEqual(result.tool_errors, { run_python: 1 });
    assert.deepEqual(validatePing(ping({ v: 2, configured: false }), NOW).tool_errors, {});
  });

  it("leaves the v2 fields out of a v1 ping", () => {
    const result = validatePing(ping(), NOW);
    assert.equal(result.version, 1);
    assert.equal(result.configured, null);
    assert.deepEqual(result.tool_errors, {});
    rejects(ping({ configured: true }), "unknown field");
    rejects(ping({ tool_errors: { run_python: 1 } }), "unknown field");
  });

  it("requires a true or false configured in v2 and checks the tool errors map", () => {
    rejects(ping({ v: 2 }), "missing field configured");
    for (const configured of [1, "true", null]) rejects(ping({ v: 2, configured }), "configured must be true or false");
    rejects(ping({ v: 2, configured: true, tool_errors: { "Run Python": 1 } }), "tool_errors has a malformed key");
    rejects(ping({ v: 2, configured: true, tool_errors: { run_python: -1 } }), "tool_errors.run_python");
    rejects(ping({ v: 2, configured: true, url: "http://localhost" }), "unknown field");
  });

  it("rejects more errors for a tool than calls of it", () => {
    const v2 = { v: 2, configured: true, tools: { run_python: 2 } };
    validatePing(ping({ ...v2, tool_errors: { run_python: 2 } }), NOW);
    rejects(ping({ ...v2, tool_errors: { run_python: 3 } }), "tool_errors.run_python is more than its calls");
    rejects(ping({ ...v2, tool_errors: { inspect_project: 1 } }), "tool_errors.inspect_project is more than its calls");
    validatePing(ping({ ...v2, tool_errors: { inspect_project: 0 } }), NOW);
  });

  it("rejects an install that is not a UUID", () => {
    for (const install of ["install-1", INSTALL.replaceAll("-", ""), `${INSTALL}0`, 42]) {
      rejects(ping({ install }), "install");
    }
  });

  it("rejects days that are malformed, unreal or too far away", () => {
    for (const day of ["2026-10-7", "17.10.2026", 20261017]) rejects(ping({ day }), "YYYY-MM-DD");
    for (const day of ["2026-02-30", "2026-13-01", "2026-10-00"]) rejects(ping({ day }), "real date");
    for (const day of ["2026-10-08", "2026-10-19", "2026-10-24", "2025-10-17"]) rejects(ping({ day }), "too far");
  });

  it("rejects malformed version strings and locales", () => {
    for (const plugin of ["", "1".repeat(33), "0.4.0 beta", "0.4/0", 4]) rejects(ping({ plugin }), "plugin");
    for (const qgis of ["", "4.2.1;drop", null]) rejects(ping({ qgis }), "qgis");
    for (const locale of ["", "a".repeat(17), "en1", "ru.RU"]) rejects(ping({ locale }), "locale");
  });

  it("rejects values outside the listed sets", () => {
    rejects(ping({ os: "MacOS" }), "os must be one of");
    rejects(ping({ provider: "cloud" }), "provider must be one of");
    rejects(ping({ dialect: "gemini" }), "dialect must be one of");
  });

  it("rejects counts that are not small non-negative integers", () => {
    for (const runs of [-1, 1.5, 100001, "3", true, null]) rejects(ping({ runs }), "runs must be an integer");
    rejects(ping({ applies: -2 }), "applies must be an integer");
  });

  it("rejects malformed counter maps", () => {
    for (const tools of [[], null, "inspect"]) rejects(ping({ tools }), "tools must be an object");
    for (const key of ["Inspect", "1tool", "_tool", "tool-name", `a${"b".repeat(49)}`, "__proto__"]) {
      rejects(ping({ skills: JSON.parse(`{${JSON.stringify(key)}: 1}`) }), "skills has a malformed key");
    }
    rejects(ping({ failures: { timeout: -1 } }), "failures.timeout must be an integer");
    rejects(ping({ failures: { timeout: 0.5 } }), "failures.timeout must be an integer");
    const crowded = Object.fromEntries(Array.from({ length: MAX_MAP_KEYS + 1 }, (_, i) => [`tool_${i}`, 1]));
    rejects(ping({ tools: crowded }), `more than ${MAX_MAP_KEYS} keys`);
  });
});

describe("hashInstall", () => {
  it("is the lower-case hex SHA-256 of the install id", async () => {
    const hash = await hashInstall(INSTALL);
    assert.equal(hash, createHash("sha256").update(INSTALL).digest("hex"));
    assert.match(hash, /^[0-9a-f]{64}$/);
  });

  it("hashes an upper-case resend to the same row key", async () => {
    const upper = validatePing(ping({ install: INSTALL.toUpperCase() }), NOW);
    assert.equal(await hashInstall(upper.install), await hashInstall(INSTALL));
  });
});

describe("pingRow", () => {
  it("lines values up with the columns and never carries the raw id", async () => {
    const hash = await hashInstall(INSTALL);
    const row = pingRow(validatePing(ping(), NOW), hash);
    assert.equal(row.length, PING_COLUMNS.length);
    const byColumn = Object.fromEntries(PING_COLUMNS.map((column, i) => [column, row[i]]));
    assert.equal(byColumn.install_hash, hash);
    assert.equal(byColumn.day, "2026-10-17");
    assert.equal(byColumn.tools, '{"inspect_project":5,"run_python":1}');
    assert.equal(byColumn.failures, '{"timeout":1}');
    assert.equal(row.includes(INSTALL), false);
  });
});

describe("extrasRow", () => {
  it("stores the v2 flag as a number and the errors as JSON", async () => {
    const hash = await hashInstall(INSTALL);
    const body = ping({ v: 2, configured: true, tools: { a_tool: 2, b_tool: 1 }, tool_errors: { b_tool: 1, a_tool: 2 } });
    assert.deepEqual(extrasRow(validatePing(body, NOW), hash), [hash, "2026-10-17", 1, '{"a_tool":2,"b_tool":1}']);
  });
});

describe("statsWindow", () => {
  it("ends today and spans thirty and ninety inclusive days and thirteen weeks", () => {
    assert.deepEqual(statsWindow(NOW), {
      today: "2026-10-17",
      recentSince: "2026-09-18",
      seriesSince: "2026-07-20",
      thisWeek: "2026-10-12",
      weeksSince: "2026-07-20",
    });
  });

  it("crosses a year boundary", () => {
    assert.deepEqual(statsWindow(new Date("2027-01-05T00:00:00Z")), {
      today: "2027-01-05",
      recentSince: "2026-12-07",
      seriesSince: "2026-10-08",
      thisWeek: "2027-01-04",
      weeksSince: "2026-10-12",
    });
  });
});

describe("weekStart", () => {
  it("is the Monday of the ISO week", () => {
    assert.equal(weekStart("2026-10-12"), "2026-10-12");
    assert.equal(weekStart("2026-10-18"), "2026-10-12");
    assert.equal(weekStart("2027-01-01"), "2026-12-28");
  });
});

describe("fillWeeks", () => {
  it("returns every week of the window, zero where nobody was active", () => {
    const weeks = fillWeeks([{ week: "2026-10-05", new_installs: 2, returning_installs: 3 }], statsWindow(NOW));
    assert.equal(weeks.length, SERIES_WEEKS);
    assert.deepEqual(weeks[0], { week: "2026-07-20", new: 0, returning: 0 });
    assert.deepEqual(weeks.at(-2), { week: "2026-10-05", new: 2, returning: 3 });
    assert.deepEqual(weeks.at(-1), { week: "2026-10-12", new: 0, returning: 0 });
  });
});

describe("shapeRetention", () => {
  it("lists each period with its installs and the ones kept", () => {
    assert.deepEqual(shapeRetention({ installs_7: 4, kept_7: 1, installs_30: 2, kept_30: null }), [
      { days: 7, installs: 4, kept: 1 },
      { days: 30, installs: 2, kept: 0 },
    ]);
  });
});

describe("rankToolErrors", () => {
  it("orders tools by errors, keeps their calls and drops the ones without errors", () => {
    const ranked = rankToolErrors([
      { tool: "inspect_project", calls: 50, errors: 0, installs: 0 },
      { tool: "run_python", calls: 10, errors: 2, installs: MIN_INSTALLS },
      { tool: "download_osm", calls: 4, errors: 3, installs: MIN_INSTALLS },
      { tool: "add_layer", calls: 9, errors: 2, installs: MIN_INSTALLS },
    ]);
    assert.deepEqual(Object.entries(ranked), [
      ["download_osm", { errors: 3, calls: 4 }],
      ["add_layer", { errors: 2, calls: 9 }],
      ["run_python", { errors: 2, calls: 10 }],
    ]);
  });

  it("caps the number of tools", () => {
    const rows = Array.from({ length: MAX_VALUES_PER_FACET + 5 }, (_, i) => ({
      tool: `t${i}`,
      calls: 99,
      errors: i + 1,
      installs: MIN_INSTALLS,
    }));
    assert.equal(Object.keys(rankToolErrors(rows)).length, MAX_VALUES_PER_FACET);
  });

  it("drops a tool whose errors fewer than five installs reported", () => {
    const rows = [
      { tool: "run_python", calls: 10, errors: 2, installs: MIN_INSTALLS - 1 },
      { tool: "add_layer", calls: 9, errors: 2 },
    ];
    assert.deepEqual(rankToolErrors(rows), {});
  });
});

describe("fillDays", () => {
  it("returns every day of the window, zero where nobody pinged", () => {
    const days = fillDays([{ day: "2026-10-16", installs: 2, runs: 5, applies: 1 }], statsWindow(NOW));
    assert.equal(days.length, SERIES_DAYS);
    assert.deepEqual(days[0], { day: "2026-07-20", installs: 0, runs: 0, applies: 0 });
    assert.deepEqual(days.at(-2), { day: "2026-10-16", installs: 2, runs: 5, applies: 1 });
    assert.deepEqual(days.at(-1), { day: "2026-10-17", installs: 0, runs: 0, applies: 0 });
  });
});

describe("rankFacet", () => {
  it("orders values by count, then by name, within one facet", () => {
    const rows = [
      { facet: "os", value: "linux", n: 2, installs: MIN_INSTALLS },
      { facet: "os", value: "macos", n: 5, installs: MIN_INSTALLS },
      { facet: "os", value: "windows", n: 2, installs: MIN_INSTALLS },
      { facet: "qgis", value: "4.2.1", n: 9, installs: MIN_INSTALLS },
    ];
    assert.deepEqual(Object.entries(rankFacet(rows, "os")), [
      ["macos", 5],
      ["linux", 2],
      ["windows", 2],
    ]);
  });

  it("caps the number of values", () => {
    const rows = Array.from({ length: MAX_VALUES_PER_FACET + 20 }, (_, i) => ({
      facet: "tools",
      value: `t${i}`,
      n: i,
      installs: MIN_INSTALLS,
    }));
    const ranked = rankFacet(rows, "tools");
    assert.equal(Object.keys(ranked).length, MAX_VALUES_PER_FACET);
    assert.equal(Object.values(ranked)[0], MAX_VALUES_PER_FACET + 19);
  });

  it("keeps a value named like a prototype key as data", () => {
    const ranked = rankFacet([{ facet: "locale", value: "__proto__", n: 1, installs: MIN_INSTALLS }], "locale");
    assert.equal(Object.hasOwn(ranked, "__proto__"), true);
    assert.equal(JSON.stringify(ranked), '{"__proto__":1}');
  });

  it("drops a value fewer than five installs reported, however large its count", () => {
    const rows = [
      { facet: "skills", value: "style", n: 6, installs: MIN_INSTALLS },
      { facet: "skills", value: "acme_parcels", n: 100000, installs: MIN_INSTALLS - 1 },
      { facet: "skills", value: "unknown_installs", n: 7 },
    ];
    assert.equal(MIN_INSTALLS, 5);
    assert.deepEqual(rankFacet(rows, "skills"), { style: 6 });
  });
});

describe("shapeStats", () => {
  it("produces exactly the public keys", () => {
    const stats = shapeStats({
      generated: NOW.toISOString(),
      window: statsWindow(NOW),
      totals: { installs_total: 4, installs_30d: 2 },
      days: [],
      facets: [{ facet: "tools", value: "inspect_project", n: 7, installs: MIN_INSTALLS }],
    });
    assert.deepEqual(Object.keys(stats), [
      "generated",
      "installs_total",
      "installs_30d",
      "days",
      "funnel",
      "weeks",
      "retention",
      "tool_errors",
      "plugin",
      "qgis",
      "os",
      "locale",
      "provider",
      "dialect",
      "tools",
      "skills",
      "failures",
    ]);
    assert.deepEqual(stats.tools, { inspect_project: 7 });
    assert.deepEqual(stats.os, {});
    assert.deepEqual(stats.funnel, { active: 0, configured: 0, ran: 0, applied: 0 });
    assert.equal(stats.weeks.length, SERIES_WEEKS);
    assert.deepEqual(stats.tool_errors, {});
  });
});
