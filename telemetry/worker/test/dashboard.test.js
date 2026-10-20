import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { describe, it } from "node:test";
import { setImmediate } from "node:timers/promises";
import vm from "node:vm";

const SCRIPT = readFileSync(new URL("../../../docs/assets/usage-stats.js", import.meta.url), "utf8");
const DAYS = [
  { day: "2026-10-16", installs: 1, runs: 1, applies: 0 },
  { day: "2026-10-17", installs: 1, runs: 1, applies: 0 },
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

async function drawn(stats, chart) {
  const figure = Object.assign(new Element("figure"), { dataset: { chart, title: chart } });
  const root = Object.assign(new Element("div"), {
    querySelector: () => new Element("p"),
    querySelectorAll: () => [figure],
  });
  const document = {
    readyState: "complete",
    documentElement: { lang: "en" },
    getElementById: () => root,
    createElement: (tag) => new Element(tag),
    createElementNS: (_, tag) => new Element(tag),
    querySelectorAll: () => [],
  };
  const fetch = async (url) => ({
    ok: true,
    text: async () => (url.endsWith(".csv") ? "day,version,downloads,uploaded\n" : JSON.stringify(stats)),
  });
  const context = { document, fetch, window: { addEventListener() {} }, getComputedStyle: () => ({}) };
  vm.runInNewContext(SCRIPT, { ...context, console, AbortController, setTimeout, clearTimeout });
  for (let tick = 0; tick < 50 && !figure.children.length; tick += 1) await setImmediate();
  return figure.text();
}

describe("usage dashboard", () => {
  it("never shows more errors than calls for a tool", async () => {
    const text = await drawn({ days: DAYS, tool_errors: { run_python: { errors: 7, calls: 4 } } }, "tool_errors");
    assert.match(text, /run_python: 4 \(100%\)/);
    assert.doesNotMatch(text, /175%|\b7\b/);
  });
});
