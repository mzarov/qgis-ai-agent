(() => {
  const STATS_URL = "https://ai-agent-usage.mzarov.workers.dev/v1/stats";
  const DOWNLOADS_URL = "https://raw.githubusercontent.com/mzarov/qgis-ai-agent/metrics/downloads.csv";

  const SVG_NS = "http://www.w3.org/2000/svg";
  const FETCH_TIMEOUT_MS = 10000;
  const RECENT_DAYS = 30;
  const MS_PER_DAY = 86400000;
  const DAY = /^\d{4}-\d{2}-\d{2}$/;
  const FUNNEL_STEPS = ["active", "configured", "ran", "applied"];
  const WEEKLY = ["new", "returning"];
  const TOP_BARS = 15;
  const RESIZE_DELAY_MS = 150;

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
  const percent = new Intl.NumberFormat(lang, { style: "percent", maximumFractionDigits: 1 });
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

  function shiftDay(day, offset) {
    return new Date(Date.parse(`${day}T00:00:00Z`) + offset * MS_PER_DAY).toISOString().slice(0, 10);
  }

  function share(part, total) {
    return percent.format(total > 0 ? part / total : 0);
  }

  function filled(template, values) {
    return values.reduce((text, value, i) => text.replaceAll(`{${i}}`, value), template || "");
  }

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

  function tableView(figure, rows, headers = [figure.dataset.key, figure.dataset.value]) {
    const details = document.createElement("details");
    const summary = document.createElement("summary");
    summary.textContent = root.dataset.table || "Table";
    const table = document.createElement("table");
    const head = table.createTHead().insertRow();
    for (const label of headers) {
      const cell = document.createElement("th");
      cell.textContent = label || "";
      head.appendChild(cell);
    }
    const body = table.createTBody();
    for (const cells of rows) {
      const row = body.insertRow();
      for (const cell of cells) row.insertCell().textContent = typeof cell === "number" ? whole.format(cell) : cell;
    }
    details.append(summary, table);
    return details;
  }

  function seriesAxes(chart, width, days, values, max = Math.max(...values)) {
    const m = SERIES_MARGIN;
    const plotWidth = width - m.left - m.right;
    const plotHeight = SERIES_HEIGHT - m.top - m.bottom;
    const { step, top } = niceScale(max);
    const y = (value) => m.top + plotHeight - (value / top) * plotHeight;
    const band = plotWidth / days.length;
    for (let tick = 0; tick <= top; tick += step) {
      svg("line", { class: "grid", x1: m.left, x2: m.left + plotWidth, y1: y(tick), y2: y(tick) }, chart);
      const label = svg("text", { class: "axis", x: m.left - 6, y: y(tick), "text-anchor": "end", dy: "0.32em" }, chart);
      label.textContent = compact.format(tick);
    }
    days.forEach((day, i) => {
      if (i === 0 || day.slice(0, 7) === days[i - 1].slice(0, 7)) return;
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

  function columnChart(figure, days, values, max) {
    const { chart, width } = frame(figure, SERIES_HEIGHT);
    const { y, band } = seriesAxes(chart, width, days, values, max);
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

  function barChart(figure, entries, text = (value) => whole.format(value)) {
    const height = entries.length * BAR_ROW;
    const { chart, width } = frame(figure, height);
    const labelRoom = Math.min(width * 0.4, Math.max(...entries.map(([k]) => textWidth(k, LABEL_FONT))) + LABEL_PAD);
    const valueRoom = Math.max(...entries.map(([, v], i) => textWidth(text(v, i), TICK_FONT))) + LABEL_PAD;
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
      tip.textContent = text(value, i);
      svg("rect", { class: "hit", x: 0, y: i * BAR_ROW, width, height: BAR_ROW }, datum);
      hint(datum, `${key}: ${text(value, i)}`);
    });
    return chart;
  }

  function ranked(counts) {
    return Object.entries(counts || {})
      .filter(([, value]) => Number.isFinite(value))
      .sort(([a, x], [b, y]) => y - x || a.localeCompare(b))
      .slice(0, TOP_BARS);
  }

  function daily(figure, stats, kind) {
    // Today is still being counted; drawn, it would read as a sudden drop.
    const complete = stats.days.slice(0, -1);
    const days = complete.map((entry) => entry.day);
    const values = complete.map((entry) => Number(entry[kind]) || 0);
    const chart = kind === "installs" ? lineChart(figure, days, values) : columnChart(figure, days, values);
    return { chart, rows: days.map((day, i) => [dayLabel(day), values[i]]).reverse() };
  }

  function weekly(figure, stats, kind) {
    // The current week is still being counted, like today.
    const complete = (stats.weeks || []).slice(0, -1);
    if (!complete.length) return { chart: null };
    const weeks = complete.map((entry) => entry.week);
    const values = complete.map((entry) => Number(entry[kind]) || 0);
    const max = Math.max(...complete.flatMap((entry) => WEEKLY.map((key) => Number(entry[key]) || 0)));
    return {
      chart: columnChart(figure, weeks, values, max),
      rows: weeks.map((week, i) => [dayLabel(week), values[i]]).reverse(),
    };
  }

  function funnel(figure, stats) {
    const counts = stats.funnel || {};
    const active = Number(counts.active) || 0;
    if (!active) return { chart: null };
    const entries = FUNNEL_STEPS.map((step) => [figure.dataset[step] || step, Number(counts[step]) || 0]);
    return {
      chart: barChart(figure, entries, (value) => `${whole.format(value)} (${share(value, active)})`),
      rows: entries.map(([label, value]) => [label, value, share(value, active)]),
      headers: [figure.dataset.key, figure.dataset.value, figure.dataset.share],
    };
  }

  function toolErrors(figure, stats) {
    const tools = Object.entries(stats.tool_errors || {})
      .map(([tool, counts]) => {
        const calls = Number(counts?.calls) || 0;
        // A tool cannot fail more often than it ran: an older document may say otherwise.
        return [tool, Math.min(Number(counts?.errors) || 0, calls), calls];
      })
      .filter(([, errors]) => errors > 0)
      .sort(([a, x], [b, y]) => y - x || a.localeCompare(b))
      .slice(0, TOP_BARS);
    if (!tools.length) return { chart: null };
    const text = (errors, i) => `${whole.format(errors)} (${share(errors, tools[i][2])})`;
    return {
      chart: barChart(figure, tools.map(([tool, errors]) => [tool, errors]), text),
      rows: tools.map(([tool, errors, calls]) => [tool, errors, calls, share(errors, calls)]),
      headers: [figure.dataset.key, figure.dataset.value, figure.dataset.calls, figure.dataset.rate],
    };
  }

  function facet(figure, stats, kind) {
    const rows = ranked(stats[kind]);
    return { chart: rows.length ? barChart(figure, rows) : null, rows };
  }

  const CHARTS = new Map([
    ["installs", daily],
    ["runs", daily],
    ["new", weekly],
    ["returning", weekly],
    ["funnel", funnel],
    ["tool_errors", toolErrors],
  ]);

  function draw(figure, stats) {
    const kind = figure.dataset.chart;
    const { chart, rows, headers } = (CHARTS.get(kind) || facet)(figure, stats, kind);
    const content = [caption(figure)];
    if (chart) {
      content.push(chart, tableView(figure, rows, headers));
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
    for (const period of stats.retention || []) {
      const installs = Number(period.installs) || 0;
      const kept = Number(period.kept) || 0;
      if (installs > 0) values[`kept_${period.days}`] = [share(kept, installs), whole.format(kept), whole.format(installs)];
    }
    show(values);
  }

  function show(values) {
    for (const cell of document.querySelectorAll("[data-usage-stat]")) {
      const value = values[cell.dataset.usageStat];
      if (Array.isArray(value)) cell.textContent = filled(cell.dataset.format, value);
      else if (Number.isFinite(value)) cell.textContent = whole.format(value);
    }
  }

  function downloadTotals(text) {
    const [header = "", ...lines] = text.trim().split(/\r?\n/);
    const columns = header.split(",");
    const dayAt = columns.indexOf("day");
    const countAt = columns.indexOf("downloads");
    const totals = new Map();
    for (const line of lines) {
      const cells = line.split(",");
      const day = cells[dayAt] || "";
      const count = Number(cells[countAt]);
      if (DAY.test(day) && Number.isFinite(count)) totals.set(day, (totals.get(day) || 0) + count);
    }
    return Array.from(totals).sort(([a], [b]) => (a < b ? -1 : 1));
  }

  function downloadValues(totals) {
    if (!totals.length) return {};
    const [lastDay, total] = totals.at(-1);
    const base = totals.filter(([day]) => day <= shiftDay(lastDay, -RECENT_DAYS)).at(-1);
    if (base) return { downloads_total: total, downloads_30d: total - base[1] };
    // The daily snapshots are younger than 30 days: count from the first one and say so.
    const [firstDay, firstTotal] = totals[0];
    return { downloads_total: total, downloads_30d: [whole.format(total - firstTotal), dayLabel(firstDay)] };
  }

  function render(stats) {
    for (const figure of figures) draw(figure, stats);
  }

  function unavailable(text) {
    say(text);
    for (const figure of figures) figure.hidden = true;
  }

  async function fetched(url) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), FETCH_TIMEOUT_MS);
    try {
      const response = await fetch(url, { signal: controller.signal });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      return await response.text();
    } finally {
      clearTimeout(timer);
    }
  }

  async function load() {
    const stats = JSON.parse(await fetched(STATS_URL));
    if (!Array.isArray(stats.days) || stats.days.length < 2) throw new Error("malformed statistics");
    return stats;
  }

  async function loadDownloads() {
    try {
      show(downloadValues(downloadTotals(await fetched(DOWNLOADS_URL))));
    } catch (error) {
      console.warn("Download counts:", error);
    }
  }

  async function start() {
    say(root.dataset.loading || "");
    loadDownloads();
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
