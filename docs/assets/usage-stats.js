// Charts for the usage statistics page (docs/usage-stats.md and its Russian
// twin). MkDocs loads this file on every page through extra_javascript; it
// does nothing unless the page has an element with the id "usage-stats".
// Page text, chart titles and table headings come from data attributes, so
// both languages share this script.

(() => {
  // The deployed Worker (telemetry/worker); the usage-stats workflow prints its
  // URL into the job summary.
  const STATS_URL = "https://ai-agent-usage.mzarov.workers.dev/v1/stats";

  const SVG_NS = "http://www.w3.org/2000/svg";
  const FETCH_TIMEOUT_MS = 10000;
  const RECENT_DAYS = 30;
  const TOP_BARS = 15;
  const RESIZE_DELAY_MS = 150;

  // Geometry in CSS pixels; the SVG is drawn at the figure's width.
  const MIN_WIDTH = 160;
  const FALLBACK_WIDTH = 640;
  const SERIES_HEIGHT = 180;
  const SERIES_MARGIN = { top: 12, right: 44, bottom: 24, left: 40 };
  const BAR_THICKNESS = 16;
  const BAR_ROW = 24;
  const BAR_GAP = 2;
  const MAX_BAR = 24;
  const CORNER = 4;
  const LABEL_PAD = 8;
  const TICK_FONT = 12;
  const LABEL_FONT = 13;
  const Y_TICKS = 4;

  const root = document.getElementById("usage-stats");
  if (!root) return;

  const lang = document.documentElement.lang || "en";
  const whole = new Intl.NumberFormat(lang);
  const compact = new Intl.NumberFormat(lang, { notation: "compact", maximumFractionDigits: 1 });
  const longDay = new Intl.DateTimeFormat(lang, { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
  const monthName = new Intl.DateTimeFormat(lang, { month: "short", timeZone: "UTC" });
  const status = root.querySelector(".usage-stats-status");
  const figures = Array.from(root.querySelectorAll("figure[data-chart]"));
  const measurer = document.createElement("canvas").getContext("2d");

  function say(text) {
    if (status) status.textContent = text;
  }

  function svg(tag, attributes = {}, parent = null) {
    const node = document.createElementNS(SVG_NS, tag);
    for (const [name, value] of Object.entries(attributes)) node.setAttribute(name, String(value));
    if (parent) parent.appendChild(node);
    return node;
  }

  function hint(parent, text) {
    svg("title", {}, parent).textContent = text;
  }

  function textWidth(text, size) {
    measurer.font = `${size}px ${getComputedStyle(root).fontFamily}`;
    return measurer.measureText(text).width;
  }

  function fitText(text, size, room) {
    if (textWidth(text, size) <= room) return text;
    let cut = text;
    while (cut.length > 1 && textWidth(`${cut}…`, size) > room) cut = cut.slice(0, -1);
    return `${cut}…`;
  }

  function dayLabel(day) {
    return longDay.format(new Date(`${day}T00:00:00Z`));
  }

  // A rectangle with rounded corners on the data end only, square at the baseline.
  function columnPath(x, y, width, height) {
    const r = Math.min(CORNER, width / 2, height);
    const base = y + height;
    return `M${x},${base}V${y + r}Q${x},${y} ${x + r},${y}H${x + width - r}Q${x + width},${y} ${x + width},${y + r}V${base}Z`;
  }

  function barPath(x, y, width, height) {
    const r = Math.min(CORNER, height / 2, width);
    const end = x + width;
    return `M${x},${y}H${end - r}Q${end},${y} ${end},${y + r}V${y + height - r}Q${end},${y + height} ${end - r},${y + height}H${x}Z`;
  }

  // The smallest round step (1, 2 or 5 times a power of ten) giving at most Y_TICKS steps.
  function niceScale(max) {
    if (max <= 0) return { step: 1, top: 1 };
    const rough = max / Y_TICKS;
    const power = 10 ** Math.floor(Math.log10(rough));
    const step = [1, 2, 5, 10].map((m) => m * power).find((s) => s >= rough);
    const wholeStep = Math.max(1, step);
    return { step: wholeStep, top: Math.ceil(max / wholeStep) * wholeStep };
  }

  function frame(figure, height) {
    const width = Math.max(MIN_WIDTH, Math.floor(figure.clientWidth || FALLBACK_WIDTH));
    const chart = svg("svg", {
      width,
      height,
      viewBox: `0 0 ${width} ${height}`,
      role: "img",
      "aria-label": figure.dataset.title || "",
    });
    return { chart, width };
  }

  function caption(figure) {
    const node = document.createElement("figcaption");
    node.textContent = figure.dataset.title || "";
    return node;
  }

  function tableView(figure, rows) {
    const details = document.createElement("details");
    const summary = document.createElement("summary");
    summary.textContent = root.dataset.table || "Table";
    const table = document.createElement("table");
    const head = table.createTHead().insertRow();
    for (const label of [figure.dataset.key || "", figure.dataset.value || ""]) {
      const cell = document.createElement("th");
      cell.textContent = label;
      head.appendChild(cell);
    }
    const body = table.createTBody();
    for (const [label, value] of rows) {
      const row = body.insertRow();
      row.insertCell().textContent = label;
      row.insertCell().textContent = whole.format(value);
    }
    details.append(summary, table);
    return details;
  }

  // Shared frame of the two 90-day charts: gridlines, y ticks and month labels.
  function seriesAxes(chart, width, days, values) {
    const m = SERIES_MARGIN;
    const plotWidth = width - m.left - m.right;
    const plotHeight = SERIES_HEIGHT - m.top - m.bottom;
    const { step, top } = niceScale(Math.max(...values));
    const y = (value) => m.top + plotHeight - (value / top) * plotHeight;
    const band = plotWidth / days.length;
    for (let tick = 0; tick <= top; tick += step) {
      svg("line", { class: "grid", x1: m.left, x2: m.left + plotWidth, y1: y(tick), y2: y(tick) }, chart);
      const label = svg("text", { class: "axis", x: m.left - 6, y: y(tick), "text-anchor": "end", dy: "0.32em" }, chart);
      label.textContent = compact.format(tick);
    }
    days.forEach((day, i) => {
      if (!day.endsWith("-01")) return;
      const label = svg("text", { class: "axis", x: m.left + band * i, y: SERIES_HEIGHT - 6 }, chart);
      label.textContent = monthName.format(new Date(`${day}T00:00:00Z`));
    });
    return { y, band, plotHeight };
  }

  function lineChart(figure, days, values) {
    const { chart, width } = frame(figure, SERIES_HEIGHT);
    const { y, band } = seriesAxes(chart, width, days, values);
    const x = (i) => SERIES_MARGIN.left + band * (i + 0.5);
    const points = values.map((value, i) => `${x(i)},${y(value)}`).join(" ");
    svg("polyline", { class: "line", points }, chart);
    days.forEach((day, i) => {
      const datum = svg("g", { class: "datum" }, chart);
      svg("line", { class: "rule", x1: x(i), x2: x(i), y1: SERIES_MARGIN.top, y2: y(0) }, datum);
      svg("circle", { class: "dot hover-only", cx: x(i), cy: y(values[i]), r: 4 }, datum);
      svg("rect", { class: "hit", x: x(i) - band / 2, y: 0, width: band, height: SERIES_HEIGHT }, datum);
      hint(datum, `${dayLabel(day)}: ${whole.format(values[i])}`);
    });
    const last = values.length - 1;
    svg("circle", { class: "dot", cx: x(last), cy: y(values[last]), r: 4 }, chart);
    const end = svg("text", { class: "value", x: x(last) + 8, y: y(values[last]), dy: "0.32em" }, chart);
    end.textContent = whole.format(values[last]);
    return chart;
  }

  function columnChart(figure, days, values) {
    const { chart, width } = frame(figure, SERIES_HEIGHT);
    const { y, band } = seriesAxes(chart, width, days, values);
    // On a phone a day is under 3px wide: shrink the gap before the bar.
    const thickness = Math.max(1, Math.min(MAX_BAR, band - Math.min(BAR_GAP, band / 3)));
    days.forEach((day, i) => {
      const datum = svg("g", { class: "datum" }, chart);
      const left = SERIES_MARGIN.left + band * i;
      const top = y(values[i]);
      if (values[i] > 0) {
        svg("path", { class: "mark", d: columnPath(left + (band - thickness) / 2, top, thickness, y(0) - top) }, datum);
      }
      svg("rect", { class: "hit", x: left, y: 0, width: band, height: SERIES_HEIGHT }, datum);
      hint(datum, `${dayLabel(day)}: ${whole.format(values[i])}`);
    });
    return chart;
  }

  function barChart(figure, entries) {
    const height = entries.length * BAR_ROW;
    const { chart, width } = frame(figure, height);
    const labelRoom = Math.min(width * 0.4, Math.max(...entries.map(([k]) => textWidth(k, LABEL_FONT))) + LABEL_PAD);
    const valueRoom = Math.max(...entries.map(([, v]) => textWidth(whole.format(v), TICK_FONT))) + LABEL_PAD;
    const plotWidth = Math.max(1, width - labelRoom - valueRoom);
    const max = Math.max(...entries.map(([, v]) => v), 1);
    entries.forEach(([key, value], i) => {
      const datum = svg("g", { class: "datum" }, chart);
      const middle = i * BAR_ROW + BAR_ROW / 2;
      const label = svg("text", { class: "label", x: labelRoom - LABEL_PAD, y: middle, "text-anchor": "end", dy: "0.32em" }, datum);
      label.textContent = fitText(key, LABEL_FONT, labelRoom - LABEL_PAD);
      const length = (value / max) * plotWidth;
      if (value > 0) {
        svg("path", { class: "mark", d: barPath(labelRoom, middle - BAR_THICKNESS / 2, length, BAR_THICKNESS) }, datum);
      }
      const tip = svg("text", { class: "value", x: labelRoom + length + 6, y: middle, dy: "0.32em" }, datum);
      tip.textContent = whole.format(value);
      svg("rect", { class: "hit", x: 0, y: i * BAR_ROW, width, height: BAR_ROW }, datum);
      hint(datum, `${key}: ${whole.format(value)}`);
    });
    return chart;
  }

  function ranked(counts) {
    return Object.entries(counts || {})
      .filter(([, value]) => Number.isFinite(value))
      .sort(([a, x], [b, y]) => y - x || a.localeCompare(b))
      .slice(0, TOP_BARS);
  }

  function draw(figure, stats) {
    const kind = figure.dataset.chart;
    let chart;
    let rows;
    if (kind === "installs" || kind === "runs") {
      // Today is still being counted; drawn, it would read as a sudden drop.
      const complete = stats.days.slice(0, -1);
      const days = complete.map((entry) => entry.day);
      const values = complete.map((entry) => Number(entry[kind]) || 0);
      chart = kind === "installs" ? lineChart(figure, days, values) : columnChart(figure, days, values);
      rows = days.map((day, i) => [dayLabel(day), values[i]]).reverse();
    } else {
      rows = ranked(stats[kind]);
      chart = rows.length ? barChart(figure, rows) : null;
    }
    const content = [caption(figure)];
    if (chart) {
      content.push(chart, tableView(figure, rows));
    } else {
      const empty = document.createElement("p");
      empty.textContent = root.dataset.empty || "";
      content.push(empty);
    }
    figure.replaceChildren(...content);
    figure.hidden = false;
  }

  function fillSummary(stats) {
    const recent = stats.days.slice(-RECENT_DAYS);
    const values = {
      installs_total: stats.installs_total,
      installs_30d: stats.installs_30d,
      runs_30d: recent.reduce((sum, day) => sum + (Number(day.runs) || 0), 0),
      applies_30d: recent.reduce((sum, day) => sum + (Number(day.applies) || 0), 0),
    };
    for (const cell of document.querySelectorAll("[data-usage-stat]")) {
      const value = values[cell.dataset.usageStat];
      if (Number.isFinite(value)) cell.textContent = whole.format(value);
    }
  }

  function render(stats) {
    for (const figure of figures) draw(figure, stats);
  }

  // The plain summary table above the charts stays as the fallback.
  function unavailable(text) {
    say(text);
    for (const figure of figures) figure.hidden = true;
  }

  async function load() {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), FETCH_TIMEOUT_MS);
    try {
      const response = await fetch(STATS_URL, { signal: controller.signal, headers: { accept: "application/json" } });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const stats = await response.json();
      if (!Array.isArray(stats.days) || stats.days.length < 2) throw new Error("malformed statistics");
      return stats;
    } finally {
      clearTimeout(timer);
    }
  }

  async function start() {
    say(root.dataset.loading || "");
    let stats;
    try {
      stats = await load();
    } catch (error) {
      console.warn("Usage statistics:", error);
      unavailable(root.dataset.failed || "");
      return;
    }
    say("");
    if (status) status.hidden = true;
    fillSummary(stats);
    render(stats);
    let drawnWidth = root.clientWidth;
    let pending = 0;
    window.addEventListener("resize", () => {
      clearTimeout(pending);
      pending = setTimeout(() => {
        if (root.clientWidth === drawnWidth) return;
        drawnWidth = root.clientWidth;
        render(stats);
      }, RESIZE_DELAY_MS);
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start);
  } else {
    start();
  }
})();
