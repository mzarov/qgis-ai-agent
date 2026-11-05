(() => {
  const STATS_URL = "https://ai-agent-usage.mzarov.workers.dev/v1/stats";
  const DOWNLOADS_URL = "https://raw.githubusercontent.com/mzarov/qgis-ai-agent/metrics/downloads.csv";

  const SVG_NS = "http://www.w3.org/2000/svg";
  const FETCH_TIMEOUT_MS = 10000;
  const RECENT_DAYS = 30;
  const SERIES_DAYS = 90;
  const MS_PER_DAY = 86400000;
  const DAY = /^\d{4}-\d{2}-\d{2}$/;
  const FUNNEL_STEPS = ["active", "configured", "ran", "applied"];
  const WEEKLY = ["new", "returning"];
  const DAILY_USE = ["runs", "sessions"];
  // Only plugin 0.4.3 and later report these; the days before their first report are unknown, not zero.
  const LATE_FIELDS = new Set(["sessions"]);
  const RUN_KINDS = ["requests", "retries", "checks"];
  const MODES = ["plan", "auto"];
  const PLAN_STEPS = ["shown", "applied", "cancelled", "undone", "auto"];
  const ACTIVATION_STEPS = ["configured", "ran", "applied"];
  const ACTIVATION_BUCKETS = ["d0", "d1", "d2_7", "d8_plus", "never"];
  const NOT_YET = "never";
  const REQUEST_BUCKETS = ["r1", "r2", "r3_5", "r6_10", "r11_plus"];
  // The keys come in this order and every one is listed; the page names each.
  const BUCKETS = {
    outcomes: ["answered", "failed", "stopped", "limit"],
    session_requests: REQUEST_BUCKETS,
    to_apply: REQUEST_BUCKETS,
    steps: ["s0", "s1", "s2_3", "s4_7", "s8_15", "s16_plus"],
    durations: ["t0_10", "t10_30", "t30_60", "t60_180", "t180_plus"],
    tokens: ["k0_5", "k5_20", "k20_50", "k50_200", "k200_plus"],
  };
  // Service names read the same in every language; the page names the two "other" groups.
  const FAMILY_NAMES = {
    openai: "OpenAI",
    openrouter: "OpenRouter",
    anthropic: "Anthropic",
    gemini: "Gemini",
    deepseek: "DeepSeek",
    mistral: "Mistral",
    groq: "Groq",
    xai: "xAI",
    together: "Together",
    fireworks: "Fireworks",
    moonshot: "Moonshot",
    qwen: "Qwen",
    zhipu: "Zhipu",
    yandex: "Yandex",
    nvidia: "NVIDIA",
    huggingface: "Hugging Face",
    cerebras: "Cerebras",
    perplexity: "Perplexity",
    azure: "Azure",
    ollama: "Ollama",
    lmstudio: "LM Studio",
  };
  const DOWNLOAD_CHARTS = new Set(["downloads"]);
  const TOP_BARS = 15;
  const RESIZE_DELAY_MS = 150;

  const MIN_WIDTH = 160;
  const FALLBACK_WIDTH = 640;
  const SERIES_HEIGHT = 180;
  const SERIES_MARGIN = { top: 12, right: 44, bottom: 24, left: 40 };
  const BAR_THICKNESS = 16;
  const BAR_ROW = 24;
  const BAR_GAP = 2;
  const SEGMENT_GAP = 2;
  const MAX_BAR = 24;
  const CORNER = 4;
  const DOT = 4;
  const LABEL_PAD = 8;
  const MIN_PLOT = 96;
  const BRIEF_WIDTH = 300;
  const TICK_FONT = 12;
  const LABEL_FONT = 13;
  const Y_TICKS = 4;

  const root = document.getElementById("usage-stats");
  if (!root) return;

  const lang = document.documentElement.lang || "en";
  const whole = new Intl.NumberFormat(lang);
  const decimal = new Intl.NumberFormat(lang, { maximumFractionDigits: 1 });
  const compact = new Intl.NumberFormat(lang, { notation: "compact", maximumFractionDigits: 1 });
  const percent = new Intl.NumberFormat(lang, { style: "percent", maximumFractionDigits: 1 });
  const longDay = new Intl.DateTimeFormat(lang, { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
  const monthName = new Intl.DateTimeFormat(lang, { month: "short", timeZone: "UTC" });
  const status = root.querySelector(".usage-stats-status");
  const figures = Array.from(document.querySelectorAll("figure.usage-chart[data-chart]"));
  const measurer = document.createElement("canvas").getContext("2d");
  const state = { stats: null, downloads: null };

  function say(text) {
    if (status) status.textContent = text;
  }

  function number(value) {
    return Number(value) || 0;
  }

  function total(values) {
    return values.reduce((sum, value) => sum + value, 0);
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

  function share(part, of) {
    return percent.format(of > 0 ? part / of : 0);
  }

  function count(value) {
    return whole.format(value);
  }

  function withShare(value, of) {
    return `${count(value)} (${share(value, of)})`;
  }

  function filled(template, values) {
    return values.reduce((text, value, i) => text.replaceAll(`{${i}}`, value), template || "");
  }

  function familyName(key) {
    return FAMILY_NAMES[key] || root.dataset[key] || key;
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

  function boxPath(x, y, width, height) {
    return `M${x},${y}H${x + width}V${y + height}H${x}Z`;
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

  function legend(items) {
    const node = document.createElement("div");
    node.className = "usage-legend";
    for (const { label, tone } of items) {
      const key = document.createElement("span");
      key.className = `usage-key ${tone}`;
      key.textContent = label;
      node.appendChild(key);
    }
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

  function seriesAxes(chart, width, keys, max) {
    const m = SERIES_MARGIN;
    const plotWidth = width - m.left - m.right;
    const plotHeight = SERIES_HEIGHT - m.top - m.bottom;
    const { step, top } = niceScale(max);
    const y = (value) => m.top + plotHeight - (value / top) * plotHeight;
    const band = plotWidth / keys.length;
    for (let tick = 0; tick <= top; tick += step) {
      svg("line", { class: "grid", x1: m.left, x2: m.left + plotWidth, y1: y(tick), y2: y(tick) }, chart);
      const label = svg("text", { class: "axis", x: m.left - 6, y: y(tick), "text-anchor": "end", dy: "0.32em" }, chart);
      label.textContent = compact.format(tick);
    }
    keys.forEach((key, i) => {
      if (i === 0 || key.slice(0, 7) === keys[i - 1].slice(0, 7)) return;
      const label = svg("text", { class: "axis", x: m.left + band * i, y: SERIES_HEIGHT - 6 }, chart);
      label.textContent = monthName.format(new Date(`${key}T00:00:00Z`));
    });
    return { y, band };
  }

  function pointText(series, i) {
    if (series.length === 1) return count(series[0].values[i]);
    const known = series.filter((item) => i >= item.start);
    return known.map((item) => `${item.label} ${count(item.values[i])}`).join(", ");
  }

  function endLabels(chart, x, ends) {
    const placed = ends.map((end) => ({ ...end, at: end.y })).sort((a, b) => a.at - b.at);
    // Close end values would print over each other; push the lower one down.
    placed.forEach((end, i) => {
      if (i > 0) end.at = Math.max(end.at, placed[i - 1].at + LABEL_FONT + 2);
    });
    for (const end of placed) {
      svg("circle", { class: `dot ${end.tone}`, cx: x, cy: end.y, r: DOT }, chart);
      const label = svg("text", { class: "value", x: x + LABEL_PAD, y: end.at, dy: "0.32em" }, chart);
      label.textContent = whole.format(end.value);
    }
  }

  function lineChart(figure, keys, series) {
    const { chart, width } = frame(figure, SERIES_HEIGHT);
    const { y, band } = seriesAxes(chart, width, keys, Math.max(...series.flatMap((item) => item.values)));
    const x = (i) => SERIES_MARGIN.left + band * (i + 0.5);
    for (const item of series) {
      const points = item.values.map((value, i) => `${x(i)},${y(value)}`).slice(item.start).join(" ");
      svg("polyline", { class: `line ${item.tone}`, points }, chart);
    }
    keys.forEach((key, i) => {
      const datum = svg("g", { class: "datum" }, chart);
      svg("line", { class: "rule", x1: x(i), x2: x(i), y1: SERIES_MARGIN.top, y2: y(0) }, datum);
      for (const item of series.filter((known) => i >= known.start)) {
        svg("circle", { class: `dot hover-only ${item.tone}`, cx: x(i), cy: y(item.values[i]), r: DOT }, datum);
      }
      svg("rect", { class: "hit", x: x(i) - band / 2, y: 0, width: band, height: SERIES_HEIGHT }, datum);
      hint(datum, `${dayLabel(key)}: ${pointText(series, i)}`);
    });
    const last = keys.length - 1;
    const ends = series.map((item) => ({ tone: item.tone, value: item.values[last], y: y(item.values[last]) }));
    endLabels(chart, x(last), ends);
    return chart;
  }

  function columnChart(figure, keys, series) {
    const { chart, width } = frame(figure, SERIES_HEIGHT);
    const sums = keys.map((_, i) => total(series.map((item) => item.values[i])));
    const { y, band } = seriesAxes(chart, width, keys, Math.max(...sums));
    const thickness = Math.max(1, Math.min(MAX_BAR, band - Math.min(BAR_GAP, band / 3)));
    keys.forEach((key, i) => {
      const datum = svg("g", { class: "datum" }, chart);
      const left = SERIES_MARGIN.left + band * i + (band - thickness) / 2;
      const stacked = series.filter((item) => item.values[i] > 0);
      let base = 0;
      stacked.forEach((item, j) => {
        // A thin surface gap between stacked segments shows the edge without relying on colour.
        const bottom = y(base) - (j > 0 ? SEGMENT_GAP : 0);
        base += item.values[i];
        const top = y(base);
        if (bottom <= top) return;
        const shape = j === stacked.length - 1 ? columnPath : boxPath;
        svg("path", { class: `mark ${item.tone}`, d: shape(left, top, thickness, bottom - top) }, datum);
      });
      svg("rect", { class: "hit", x: SERIES_MARGIN.left + band * i, y: 0, width: band, height: SERIES_HEIGHT }, datum);
      hint(datum, `${dayLabel(key)}: ${pointText(series, i)}`);
    });
    return chart;
  }

  function barChart(figure, entries, { text = count, brief = null, max, tip } = {}) {
    const { chart, width } = frame(figure, entries.length * BAR_ROW);
    const labelRoom = Math.min(width * 0.4, Math.max(...entries.map(([k]) => textWidth(k, LABEL_FONT))) + LABEL_PAD);
    const room = (label) => width - labelRoom - LABEL_PAD - Math.max(...entries.map(([, v], i) => textWidth(label(v, i), TICK_FONT)));
    // A narrow chart keeps its bars readable; the long figure stays in the tooltip and the table.
    const endText = brief && (width < BRIEF_WIDTH || room(text) < MIN_PLOT) ? brief : text;
    const plotWidth = Math.max(1, room(endText));
    const top = max ?? Math.max(...entries.map(([, v]) => v), 1);
    entries.forEach(([key, value], i) => {
      const datum = svg("g", { class: "datum" }, chart);
      const middle = i * BAR_ROW + BAR_ROW / 2;
      const label = svg("text", { class: "label", x: labelRoom - LABEL_PAD, y: middle, "text-anchor": "end", dy: "0.32em" }, datum);
      label.textContent = fitText(key, LABEL_FONT, labelRoom - LABEL_PAD);
      const length = (value / top) * plotWidth;
      if (value > 0) {
        svg("path", { class: "mark", d: barPath(labelRoom, middle - BAR_THICKNESS / 2, length, BAR_THICKNESS) }, datum);
      }
      const end = svg("text", { class: "value", x: labelRoom + length + 6, y: middle, dy: "0.32em" }, datum);
      end.textContent = endText(value, i);
      svg("rect", { class: "hit", x: 0, y: i * BAR_ROW, width, height: BAR_ROW }, datum);
      hint(datum, tip ? tip(i) : `${key}: ${text(value, i)}`);
    });
    return chart;
  }

  function stackedBars(figure, rows, parts) {
    const { chart, width } = frame(figure, rows.length * BAR_ROW);
    const labelRoom = Math.min(width * 0.4, Math.max(...rows.map((row) => textWidth(row.label, LABEL_FONT))) + LABEL_PAD);
    const plotWidth = Math.max(1, width - labelRoom - LABEL_PAD);
    rows.forEach((row, i) => {
      const middle = i * BAR_ROW + BAR_ROW / 2;
      const label = svg("text", { class: "label", x: labelRoom - LABEL_PAD, y: middle, "text-anchor": "end", dy: "0.32em" }, chart);
      label.textContent = fitText(row.label, LABEL_FONT, labelRoom - LABEL_PAD);
      const sum = total(row.values);
      const shown = row.values.map((value, j) => [value, j]).filter(([value]) => value > 0);
      let x = labelRoom;
      shown.forEach(([value, j], k) => {
        const start = x + (k > 0 ? SEGMENT_GAP : 0);
        x += (value / sum) * plotWidth;
        if (x <= start) return;
        const datum = svg("g", { class: "datum" }, chart);
        const shape = k === shown.length - 1 ? barPath : boxPath;
        svg("path", { class: `mark ${parts[j].tone}`, d: shape(start, middle - BAR_THICKNESS / 2, x - start, BAR_THICKNESS) }, datum);
        hint(datum, `${row.label}, ${parts[j].label}: ${withShare(value, sum)}`);
      });
    });
    return chart;
  }

  function ranked(counts) {
    return Object.entries(counts || {})
      .filter(([, value]) => Number.isFinite(value))
      .sort(([a, x], [b, y]) => y - x || a.localeCompare(b))
      .slice(0, TOP_BARS);
  }

  function complete(stats) {
    // Today is still being counted; drawn, it would read as a sudden drop.
    return stats.days.slice(0, -1);
  }

  function overTime(figure, entries, keyField, fields, form) {
    if (!entries.length) return {};
    const keys = entries.map((entry) => entry[keyField]);
    // Tones follow the field, so a series an older document leaves out does not repaint the rest.
    const series = fields
      .map((field, i) => {
        const values = entries.map((entry) => number(entry[field]));
        const start = LATE_FIELDS.has(field) ? values.findIndex((value) => value > 0) : 0;
        return { label: figure.dataset[field] || figure.dataset.value, tone: `tone-${i + 1}`, values, start };
      })
      .filter((item, i) => i === 0 || (item.start >= 0 && item.values.some((value) => value > 0)));
    const cell = (item, i) => (i >= item.start ? item.values[i] : "—");
    return {
      chart: form(figure, keys, series),
      legend: series.length > 1 ? series : null,
      rows: keys.map((key, i) => [dayLabel(key), ...series.map((item) => cell(item, i))]).reverse(),
      headers: [figure.dataset.key, ...series.map((item) => item.label)],
    };
  }

  function fixedBars(figure, entries, of = 0, max = undefined) {
    if (!entries.some(([, value]) => value > 0)) return {};
    if (!of) return { chart: barChart(figure, entries), rows: entries };
    return {
      chart: barChart(figure, entries, { text: (value) => withShare(value, of), brief: count, max }),
      rows: entries.map(([label, value]) => [label, value, share(value, of)]),
      headers: [figure.dataset.key, figure.dataset.value, figure.dataset.share],
    };
  }

  function labelled(figure, keys, counts) {
    return keys.map((key) => [figure.dataset[key] || key, number(counts?.[key])]);
  }

  function runCount(stats) {
    return total(Object.values(stats.outcomes || {}).map(number));
  }

  function reported(stats) {
    // Only plugin 0.4.3 and later send the detail; before it the activity block counts no installs.
    return number(stats.activity?.installs) > 0;
  }

  function buckets(figure, stats, kind) {
    const entries = labelled(figure, BUCKETS[kind], stats[kind]);
    return fixedBars(figure, entries, total(entries.map(([, value]) => value)));
  }

  function modes(figure, stats) {
    // Plan and Auto are a part of all runs, so their bars are measured against the whole.
    const runs = runCount(stats);
    return fixedBars(figure, labelled(figure, MODES, stats.modes), runs, runs);
  }

  function runKinds(figure, stats) {
    return reported(stats) ? fixedBars(figure, labelled(figure, RUN_KINDS, stats.activity)) : {};
  }

  function plans(figure, stats) {
    if (!reported(stats) || !stats.plans) return {};
    return fixedBars(figure, labelled(figure, PLAN_STEPS, { ...stats.plans, applied: stats.activity.applies }));
  }

  function retention(figure, stats) {
    const periods = (stats.retention || []).filter((period) => number(period.installs) > 0);
    if (!periods.length) return {};
    const counts = periods.map((period) => [number(period.kept), number(period.installs)]);
    const entries = periods.map((period, i) => [figure.dataset[`kept_${period.days}`] || `${period.days}`, counts[i][0] / counts[i][1]]);
    const text = (value, i) => filled(figure.dataset.format, [percent.format(value), ...counts[i].map((n) => whole.format(n))]);
    return {
      chart: barChart(figure, entries, { text, brief: (value) => percent.format(value), max: 1 }),
      rows: entries.map(([label, value], i) => [label, ...counts[i], percent.format(value)]),
      headers: [figure.dataset.key, figure.dataset.kept, figure.dataset.installs, figure.dataset.share],
    };
  }

  function funnel(figure, stats) {
    const counts = stats.funnel || {};
    const active = number(counts.active);
    if (!active) return {};
    const entries = labelled(figure, FUNNEL_STEPS, counts);
    return {
      chart: barChart(figure, entries, { text: (value) => withShare(value, active), brief: count }),
      rows: entries.map(([label, value]) => [label, value, share(value, active)]),
      headers: [figure.dataset.key, figure.dataset.value, figure.dataset.share],
    };
  }

  function activation(figure, stats) {
    const data = stats.activation || {};
    const rows = ACTIVATION_STEPS.map((step) => ({
      label: figure.dataset[step] || step,
      values: ACTIVATION_BUCKETS.map((bucket) => number(data[step]?.[bucket])),
    })).filter((row) => total(row.values) > 0);
    if (!rows.length) return {};
    const parts = ACTIVATION_BUCKETS.map((bucket, i) => ({
      label: figure.dataset[bucket] || bucket,
      tone: bucket === NOT_YET ? "rest" : `step-${i}`,
    }));
    return {
      chart: stackedBars(figure, rows, parts),
      legend: parts,
      rows: rows.map((row) => [row.label, ...row.values.map((value) => withShare(value, total(row.values)))]),
      headers: [figure.dataset.key, ...parts.map((part) => part.label)],
    };
  }

  function failures(figure, stats) {
    const entries = ranked(stats.failures);
    if (!entries.length) return {};
    const installs = stats.failure_installs || {};
    if (!entries.some(([kind]) => Number.isFinite(installs[kind]))) return { chart: barChart(figure, entries), rows: entries };
    const reach = (kind) => number(installs[kind]);
    const tip = (i) => `${entries[i][0]}: ${whole.format(entries[i][1])}; ${figure.dataset.installs}: ${whole.format(reach(entries[i][0]))}`;
    return {
      chart: barChart(figure, entries, { tip }),
      rows: entries.map(([kind, count]) => [kind, count, reach(kind)]),
      headers: [figure.dataset.key, figure.dataset.value, figure.dataset.installs],
    };
  }

  function families(figure, stats) {
    const rows = Object.entries(stats.families || {})
      .map(([family, counts]) => {
        const runs = number(counts?.runs);
        return [familyName(family), number(counts?.installs), runs, Math.min(number(counts?.failed), runs)];
      })
      .filter(([, , runs]) => runs > 0)
      .sort((a, b) => b[2] - a[2] || a[0].localeCompare(b[0]))
      .slice(0, TOP_BARS);
    if (!rows.length) return {};
    const rates = rows.map(([, , runs, failed]) => failed / runs);
    const text = (rate, i) => filled(figure.dataset.format, [percent.format(rate), whole.format(rows[i][3]), whole.format(rows[i][2])]);
    return {
      chart: barChart(figure, rows.map((row, i) => [row[0], rates[i]]), {
        text,
        brief: (rate) => percent.format(rate),
        max: Math.max(...rates) || 1,
      }),
      rows: rows.map((row, i) => [...row, percent.format(rates[i])]),
      headers: [figure.dataset.key, figure.dataset.installs, figure.dataset.runs, figure.dataset.failed, figure.dataset.rate],
    };
  }

  function toolErrors(figure, stats) {
    const tools = Object.entries(stats.tool_errors || {})
      .map(([tool, counts]) => {
        const calls = number(counts?.calls);
        // A tool cannot fail more often than it ran: an older document may say otherwise.
        return [tool, Math.min(number(counts?.errors), calls), calls];
      })
      .filter(([, errors]) => errors > 0)
      .sort(([a, x], [b, y]) => y - x || a.localeCompare(b))
      .slice(0, TOP_BARS);
    if (!tools.length) return {};
    return {
      chart: barChart(figure, tools.map(([tool, errors]) => [tool, errors]), {
        text: (errors, i) => withShare(errors, tools[i][2]),
        brief: count,
      }),
      rows: tools.map(([tool, errors, calls]) => [tool, errors, calls, share(errors, calls)]),
      headers: [figure.dataset.key, figure.dataset.value, figure.dataset.calls, figure.dataset.rate],
    };
  }

  function facet(figure, stats, kind) {
    const rows = ranked(stats[kind]).map(([key, value]) => [kind === "family" ? familyName(key) : key, value]);
    return rows.length ? { chart: barChart(figure, rows), rows } : {};
  }

  function downloadDays(totals) {
    return totals
      .slice(1)
      .map(([day, count], i) => ({ day, downloads: Math.max(0, count - totals[i][1]) }))
      .slice(-SERIES_DAYS);
  }

  const CHARTS = new Map([
    ["installs", (figure, stats) => overTime(figure, complete(stats), "day", ["installs"], lineChart)],
    ["daily_use", (figure, stats) => overTime(figure, complete(stats), "day", DAILY_USE, lineChart)],
    ["weeks", (figure, stats) => overTime(figure, (stats.weeks || []).slice(0, -1), "week", WEEKLY, columnChart)],
    ["downloads", (figure, totals) => overTime(figure, downloadDays(totals), "day", ["downloads"], columnChart)],
    ["retention", retention],
    ["funnel", funnel],
    ["activation", activation],
    ["run_kinds", runKinds],
    ["modes", modes],
    ["plans", plans],
    ["failures", failures],
    ["families", families],
    ["tool_errors", toolErrors],
    ...Object.keys(BUCKETS).map((kind) => [kind, buckets]),
  ]);

  function draw(figure, data) {
    const kind = figure.dataset.chart;
    let drawn = {};
    try {
      drawn = (CHARTS.get(kind) || facet)(figure, data, kind);
    } catch (error) {
      // A chart the document cannot fill must not take the rest of the page with it.
      console.warn(`Usage chart ${kind}:`, error);
    }
    const content = [caption(figure)];
    if (drawn.chart) {
      if (drawn.legend) content.push(legend(drawn.legend));
      content.push(drawn.chart, tableView(figure, drawn.rows, drawn.headers));
    } else {
      const empty = document.createElement("p");
      empty.className = "usage-empty";
      empty.textContent = root.dataset.empty || "";
      content.push(empty);
    }
    figure.replaceChildren(...content);
    figure.hidden = false;
  }

  function sourceOf(figure) {
    return DOWNLOAD_CHARTS.has(figure.dataset.chart) ? "downloads" : "stats";
  }

  function render(source = null) {
    for (const figure of figures) {
      const from = sourceOf(figure);
      if ((source === null || source === from) && state[from]) draw(figure, state[from]);
    }
  }

  function hide(source) {
    for (const figure of figures) if (sourceOf(figure) === source) figure.hidden = true;
  }

  function fillSummary(stats) {
    const recent = stats.days.slice(-RECENT_DAYS);
    const recentSum = (field) => total(recent.map((day) => number(day[field])));
    const values = {
      installs_total: stats.installs_total,
      installs_30d: stats.installs_30d,
      requests_30d: recentSum("runs"),
      applies_30d: recentSum("applies"),
    };
    for (const period of stats.retention || []) {
      const installs = number(period.installs);
      const kept = number(period.kept);
      if (installs > 0) values[`kept_${period.days}`] = [share(kept, installs), whole.format(kept), whole.format(installs)];
    }
    if (reported(stats)) {
      const sessions = number(stats.activity.sessions);
      values.sessions_30d = sessions;
      if (sessions > 0) values.requests_per_session = [decimal.format(number(stats.activity.requests) / sessions)];
    }
    const runs = runCount(stats);
    if (runs > 0) {
      const answered = number(stats.outcomes.answered);
      values.answered = [share(answered, runs), whole.format(answered), whole.format(runs)];
    }
    show(values);
  }

  function show(values) {
    for (const cell of document.querySelectorAll("[data-usage-stat]")) {
      const value = values[cell.dataset.usageStat];
      const parts = Array.isArray(value) ? value : Number.isFinite(value) ? [whole.format(value)] : null;
      if (parts) cell.textContent = cell.dataset.format ? filled(cell.dataset.format, parts) : parts[0];
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
    const [lastDay, count] = totals.at(-1);
    // Snapshots younger than 30 days count from the first one; the label names the day either way.
    const [baseDay, baseCount] = totals.filter(([day]) => day <= shiftDay(lastDay, -RECENT_DAYS)).at(-1) || totals[0];
    return { downloads_total: count, downloads_30d: [whole.format(count - baseCount), dayLabel(baseDay)] };
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
      state.downloads = downloadTotals(await fetched(DOWNLOADS_URL));
    } catch (error) {
      console.warn("Download counts:", error);
      hide("downloads");
      return;
    }
    show(downloadValues(state.downloads));
    render("downloads");
  }

  function redrawOnResize() {
    let drawnWidth = root.clientWidth;
    let pending = 0;
    window.addEventListener("resize", () => {
      clearTimeout(pending);
      pending = setTimeout(() => {
        if (root.clientWidth === drawnWidth) return;
        drawnWidth = root.clientWidth;
        render();
      }, RESIZE_DELAY_MS);
    });
  }

  async function start() {
    say(root.dataset.loading || "");
    redrawOnResize();
    loadDownloads();
    try {
      state.stats = await load();
    } catch (error) {
      console.warn("Usage statistics:", error);
      say(root.dataset.failed || "");
      hide("stats");
      return;
    }
    say("");
    if (status) status.hidden = true;
    fillSummary(state.stats);
    render("stats");
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start);
  } else {
    start();
  }
})();
