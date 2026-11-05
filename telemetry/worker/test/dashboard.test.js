import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { describe, it } from "node:test";
import { setImmediate } from "node:timers/promises";
import vm from "node:vm";

import { ACTIVATION_BUCKETS, DETAIL_MAPS } from "../src/payload.js";

const SCRIPT = readFileSync(new URL("../../../docs/assets/usage-stats.js", import.meta.url), "utf8");
const PAGES = {
  en: readFileSync(new URL("../../../docs/usage-stats.md", import.meta.url), "utf8"),
  ru: readFileSync(new URL("../../../docs/usage-stats.ru.md", import.meta.url), "utf8"),
};
const EMPTY_CSV = "day,version,downloads,uploaded\n";
const CSV = `${EMPTY_CSV}2026-10-18,0.4.1,1000,2026-10-20
2026-10-19,0.4.1,1010,2026-10-20
2026-10-19,0.4.2,5,2026-10-26
2026-10-20,0.4.1,1020,2026-10-20
2026-10-20,0.4.2,25,2026-10-26
`;

// What the Worker published before plugin 0.4.3: no activity, outcomes or ranges.
const OLD = {
  generated: "2026-11-05T10:00:00.000Z",
  installs_total: 40,
  installs_30d: 12,
  days: [
    { day: "2026-11-03", installs: 9, runs: 20, applies: 1 },
    { day: "2026-11-04", installs: 10, runs: 25, applies: 2 },
    { day: "2026-11-05", installs: 4, runs: 5, applies: 0 },
  ],
  funnel: { active: 12, configured: 8, ran: 6, applied: 2 },
  weeks: [
    { week: "2026-10-26", new: 5, returning: 3 },
    { week: "2026-11-02", new: 2, returning: 6 },
  ],
  retention: [
    { days: 7, installs: 30, kept: 9 },
    { days: 30, installs: 10, kept: 2 },
  ],
  tool_errors: { run_python: { errors: 3, calls: 10 } },
  plugin: { "0.4.2": 8 },
  qgis: { "4.0.1": 12 },
  os: { macos: 7, windows: 5 },
  locale: { en: 9 },
  provider: { remote: 10 },
  dialect: { openai: 12 },
  tools: { list_layers: 40 },
  skills: { inspect: 9 },
  failures: { http_429: 6 },
};

const V3 = {
  ...OLD,
  days: OLD.days.map((day, i) => ({ ...day, sessions: 4 + i, failed: i })),
  activity: { installs: 6, requests: 35, retries: 5, checks: 10, sessions: 10, applies: 4 },
  outcomes: { answered: 40, failed: 6, stopped: 3, limit: 1 },
  modes: { plan: 5, auto: 10 },
  plans: { shown: 8, cancelled: 2, undone: 1, auto: 3 },
  session_requests: { r1: 4, r2: 2, r3_5: 3, r6_10: 1, r11_plus: 0 },
  to_apply: { r1: 2, r2: 1, r3_5: 1, r6_10: 0, r11_plus: 0 },
  steps: { s0: 5, s1: 10, s2_3: 15, s4_7: 12, s8_15: 6, s16_plus: 2 },
  durations: { t0_10: 10, t10_30: 15, t30_60: 12, t60_180: 9, t180_plus: 4 },
  tokens: { k0_5: 5, k5_20: 20, k20_50: 15, k50_200: 8, k200_plus: 2 },
  family: { openai: 6, other_local: 5 },
  families: {
    openai: { installs: 6, runs: 20, failed: 2 },
    other_local: { installs: 5, runs: 30, failed: 4 },
  },
  failure_installs: { http_429: 5 },
  activation: {
    installs: 20,
    configured: { d0: 10, d1: 2, d2_7: 2, d8_plus: 1, never: 5 },
    ran: { d0: 6, d1: 2, d2_7: 2, d8_plus: 1, never: 9 },
    applied: { d0: 1, d1: 1, d2_7: 0, d8_plus: 0, never: 18 },
  },
};

const NEW_CHARTS = [
  "activation",
  "run_kinds",
  "session_requests",
  "to_apply",
  "modes",
  "outcomes",
  "families",
  "steps",
  "durations",
  "tokens",
  "plans",
  "family",
];

// Just enough of the DOM for the dashboard to draw into; text() reads what a visitor would see.
class Element {
  constructor(tag) {
    this.tag = tag;
    this.children = [];
    this.dataset = {};
    this.textContent = "";
    this.hidden = false;
    this.clientWidth = 640;
  }
  setAttribute() {}
  appendChild(child) {
    this.children.push(child);
    return child;
  }
  append(...children) {
    this.children.push(...children);
  }
  replaceChildren(...children) {
    this.children = children;
  }
  getContext() {
    return { font: "", measureText: (text) => ({ width: String(text).length * 7 }) };
  }
  createTHead() {
    return this.appendChild(new Element("thead"));
  }
  createTBody() {
    return this.appendChild(new Element("tbody"));
  }
  insertRow() {
    return this.appendChild(new Element("tr"));
  }
  insertCell() {
    return this.appendChild(new Element("td"));
  }
  text() {
    return [this.textContent, ...this.children.map((child) => child.text())].join(" ");
  }
}

function dataset(tag) {
  const values = {};
  for (const [, name, value] of tag.matchAll(/\sdata-([\w-]+)="([^"]*)"/g)) {
    values[name.replace(/-([a-z])/g, (_, letter) => letter.toUpperCase())] = value;
  }
  return values;
}

// The page's own markup, so a chart without its labels fails here and not on the site.
function parsed(markdown) {
  const element = (tag, attributes, text = "") => Object.assign(new Element(tag), { dataset: dataset(attributes), textContent: text });
  return {
    root: element("div", markdown.match(/<div id="usage-stats"[^>]*>/)[0]),
    figures: [...markdown.matchAll(/<figure class="usage-chart"[^>]*>/g)].map(([tag]) => element("figure", tag)),
    cells: [...markdown.matchAll(/(<span[^>]*data-usage-stat[^>]*>)([^<]*)<\/span>/g)].map(([, tag, text]) =>
      element("span", tag, text),
    ),
  };
}

async function rendered(stats, { lang = "en", csv = EMPTY_CSV } = {}) {
  const { root, figures, cells } = parsed(PAGES[lang]);
  root.querySelector = () => new Element("p");
  const document = {
    readyState: "complete",
    documentElement: { lang },
    getElementById: () => root,
    createElement: (tag) => new Element(tag),
    createElementNS: (_, tag) => new Element(tag),
    querySelectorAll: (selector) => (selector.startsWith("figure") ? figures : selector === "[data-usage-stat]" ? cells : []),
  };
  const fetch = async (url) => ({ ok: true, text: async () => (url.endsWith(".csv") ? csv : JSON.stringify(stats)) });
  const warnings = [];
  const console = { warn: (...parts) => warnings.push(parts.join(" ")), error: (...parts) => warnings.push(parts.join(" ")) };
  const context = { document, fetch, window: { addEventListener() {} }, getComputedStyle: () => ({}), console };
  vm.runInNewContext(SCRIPT, { ...context, AbortController, setTimeout, clearTimeout });
  for (let tick = 0; tick < 50 && figures.some((figure) => !figure.children.length); tick += 1) await setImmediate();
  const chart = (kind) => figures.find((figure) => figure.dataset.chart === kind).text();
  const stat = (key, formatted = false) =>
    cells.find((cell) => cell.dataset.usageStat === key && Boolean(cell.dataset.format) === formatted).textContent;
  return { figures, warnings, chart, stat };
}

describe("usage dashboard", () => {
  it("draws every chart from a document older than 0.4.3", async () => {
    const page = await rendered(OLD);
    assert.deepEqual(page.warnings, []);
    for (const figure of page.figures) assert.ok(figure.children.length, figure.dataset.chart);
    for (const kind of NEW_CHARTS) assert.match(page.chart(kind), /No data yet\./, kind);
    for (const kind of ["installs", "weeks", "retention", "funnel", "daily_use", "tool_errors", "plugin"]) {
      assert.doesNotMatch(page.chart(kind), /No data yet\./, kind);
    }
    assert.doesNotMatch(page.chart("daily_use"), /Conversations/);
    assert.equal(page.stat("installs_30d"), "12");
    assert.equal(page.stat("installs_total", true), "last 30 days, 40 all time");
    assert.equal(page.stat("requests_30d"), "50");
    assert.equal(page.stat("applies_30d"), "3");
    assert.equal(page.stat("kept_7"), "30%");
    assert.equal(page.stat("kept_7", true), "9 of 30 installs");
    assert.equal(page.stat("sessions_30d"), "—");
    assert.equal(page.stat("requests_per_session"), "—");
    assert.equal(page.stat("answered"), "—");
  });

  it("fills the tiles and the new charts from a 0.4.3 document", async () => {
    const page = await rendered(V3, { csv: CSV });
    assert.deepEqual(page.warnings, []);
    assert.equal(page.stat("sessions_30d"), "10");
    assert.equal(page.stat("requests_per_session"), "3.5");
    assert.equal(page.stat("answered"), "80%");
    assert.equal(page.stat("answered", true), "40 of 50 runs, plugin 0.4.3+");
    assert.equal(page.stat("downloads_total"), "1,045");
    assert.equal(page.stat("downloads_30d", true), "45 since Oct 18, 2026");
    assert.match(page.chart("daily_use"), /Requests 25, Conversations 5/);
    assert.match(page.chart("weeks"), /New 5, Returning 3/);
    assert.match(page.chart("downloads"), /Oct 20, 2026: 30/);
    assert.match(page.chart("activation"), /Set up a model, Same day: 10 \(50%\)/);
    assert.match(page.chart("session_requests"), /3–5: 3 \(30%\)/);
    assert.match(page.chart("durations"), /1–3 min: 9 \(18%\)/);
    assert.match(page.chart("tokens"), /50k–200k: 8 \(16%\)/);
    assert.match(page.chart("steps"), /None: 5 \(10%\)/);
    assert.match(page.chart("modes"), /Auto: 10 \(20%\)/);
    assert.match(page.chart("outcomes"), /Hit a step or token limit: 1 \(2%\)/);
    assert.match(page.chart("run_kinds"), /Checks after Apply: 10/);
    assert.match(page.chart("plans"), /Applied: 4/);
    assert.match(page.chart("families"), /OpenAI: 10% \(2 of 20\)/);
    assert.match(page.chart("families"), /Other local server: 13\.3% \(4 of 30\)/);
    assert.match(page.chart("failures"), /http_429: 6; Installs: 5/);
    assert.match(page.chart("family"), /Other local server: 5/);
  });

  it("starts the conversations line at its first report", async () => {
    const days = V3.days.map((day, i) => (i === 0 ? { ...day, sessions: 0 } : day));
    const page = await rendered({ ...V3, days });
    assert.match(page.chart("daily_use"), /Nov 3, 2026: Requests 20 /);
    assert.match(page.chart("daily_use"), /Nov 4, 2026: Requests 25, Conversations 5/);
    assert.match(page.chart("daily_use"), /Nov 3, 2026 20 —/);
  });

  it("draws the Russian page from the same documents", async () => {
    for (const stats of [OLD, V3]) {
      const page = await rendered(stats, { lang: "ru", csv: CSV });
      assert.deepEqual(page.warnings, []);
      for (const figure of page.figures) assert.ok(figure.children.length, figure.dataset.chart);
    }
    const page = await rendered(V3, { lang: "ru" });
    assert.match(page.chart("tokens"), /50–200 тыс\.: 8/);
    assert.equal(page.stat("answered", true), "прогоны: 40 из 50, плагин 0.4.3+");
  });

  it("mirrors the English page's charts and labels in Russian", () => {
    const shape = (markdown) => {
      const { figures, cells } = parsed(markdown);
      return {
        figures: figures.map((figure) => [figure.dataset.chart, Object.keys(figure.dataset).sort()]),
        cells: cells.map((cell) => [cell.dataset.usageStat, Boolean(cell.dataset.format)]),
      };
    };
    assert.deepEqual(shape(PAGES.ru), shape(PAGES.en));
  });

  it("names every range the Worker publishes", () => {
    const { figures } = parsed(PAGES.en);
    for (const [map, keys] of Object.entries(DETAIL_MAPS)) {
      const figure = figures.find((candidate) => candidate.dataset.chart === map);
      if (!figure) continue;
      for (const key of keys) assert.ok(figure.dataset[key], `${map}.${key}`);
    }
    const activation = figures.find((figure) => figure.dataset.chart === "activation");
    for (const bucket of ACTIVATION_BUCKETS) assert.ok(activation.dataset[bucket], bucket);
  });

  it("never shows more errors than calls for a tool", async () => {
    const page = await rendered({ ...OLD, tool_errors: { run_python: { errors: 7, calls: 4 } } });
    assert.match(page.chart("tool_errors"), /run_python: 4 \(100%\)/);
    assert.doesNotMatch(page.chart("tool_errors"), /175%|\b7\b/);
  });
});
