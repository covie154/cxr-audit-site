import { test } from "node:test";
import assert from "node:assert/strict";

class FakeNode {
    constructor(tag, cls) {
        this.tag = tag;
        this.className = cls || "";
        this.childNodes = [];
        this._text = "";
        this.attributes = {};
        this.disposedCount = 0;
        this.nodeObserved = false;
        this.mutationObserved = false;
    }
    get textContent() { return this._text; }
    set textContent(value) { this._text = value === null || value === undefined ? "" : String(value); }
    get children() { return this.childNodes; }
    get firstChild() { return this.childNodes.length ? this.childNodes[0] : null; }
    appendChild(node) { this.childNodes.push(node); return node; }
    removeChild(node) { const at = this.childNodes.indexOf(node); if (at >= 0) { this.childNodes.splice(at, 1); } return node; }
    setAttribute(name, value) { this.attributes[name] = value; }
    getAttribute(name) { return this.attributes[name]; }
    descendants() { const out = [this]; for (const child of this.children) { for (const node of child.descendants()) { out.push(node); } } return out; }
}

const recordedChartOptions = [];
const allCharts = [];

globalThis.document = {
    createElement: (tag) => new FakeNode(tag),
    createTextNode: (text) => { const node = new FakeNode("#text"); node.textContent = text; node.nodeType = 3; return node; },
    documentElement: new FakeNode("html"),
};

function makeChart(box) {
    let disposed = false;
    const chart = {
        box,
        initCount: 0,
        resizeCount: 0,
        setOption(option, config) { recordedChartOptions.push({ option, config }); },
        resize() { chart.resizeCount += 1; },
        dispose() { if (!disposed) { disposed = true; if (box) { box.disposedCount += 1; } } chart.disposeCount = (chart.disposeCount || 0) + 1; },
    };
    chart.initCount += 1;
    allCharts.push(chart);
    return chart;
}

globalThis.window = {
    echarts: { init: (box) => makeChart(box && String(box.className || "").includes("widget-chart") ? box : null) },
};

globalThis.ResizeObserver = class {
    constructor(callback) { this.callback = callback; this.observed = []; }
    observe(node) { this.observed.push(node); if (node) { node.nodeObserved = true; } }
    disconnect() { this.observed = []; }
};

globalThis.MutationObserver = class {
    constructor(callback) { this.callback = callback; this.observed = []; }
    observe(node) { this.observed.push(node); if (node) { node.mutationObserved = true; } }
    disconnect() { this.observed = []; }
};

const { registry } = await import("../../static/report_v2/widgets/registry.mjs");
const { register, get, render, disposeInstance, disposeAll, RendererError } = registry;
const { formatValue, groupColor } = await import("../../static/report_v2/widgets/format.mjs");
const valueRenderer = await import("../../static/report_v2/widgets/value.mjs");
const tableRenderer = await import("../../static/report_v2/widgets/table.mjs");
const lineRenderer = await import("../../static/report_v2/widgets/line.mjs");
const barRenderer = await import("../../static/report_v2/widgets/bar.mjs");

register("value", valueRenderer);
register("table", tableRenderer);
register("line", lineRenderer);
register("bar", barRenderer);

function findByClass(root, cls) { return root.descendants().find((node) => (node.className || "").split(/\s+/).includes(cls)) || null; }
function collectText(node) { let text = node.textContent || ""; for (const child of node.children) { text += " " + collectText(child); } return text; }

function makeContainer(cls) { return new FakeNode("div", cls || "widget-frame"); }

function weeklyBucketPayload(extra) {
    const buckets = [
        { index: 0, size: 7, label: "W1", period_start: "2026-06-01", period_end: "2026-06-07" },
        { index: 1, size: 7, label: "W2", period_start: "2026-06-08", period_end: "2026-06-14" },
        { index: 2, size: 7, label: "W3", period_start: "2026-06-15", period_end: "2026-06-21" },
    ];
    const cells = [];
    for (const group of ["gA", "gB"]) {
        for (let i = 0; i < buckets.length; i += 1) {
            if (i === 1) { continue; }
            cells.push({ group, category: null, bucket_index: i, value: group === "gA" ? 0.8 : 0.6 });
        }
    }
    const payload = { buckets, series: cells, groups: ["gA", "gB"], units: { gA: "rate[0,1]", gB: "rate[0,1]" } };
    return Object.assign(payload, extra || {});
}

function groupedBarPayload() {
    const cells = [];
    for (const group of ["g0", "g1"]) {
        for (let c = 0; c < 3; c += 1) { cells.push({ group, category: "c" + c, bucket_index: null, value: 3 + c }); }
    }
    return { series: cells, groups: ["g0", "g1"], units: { g0: "count", g1: "count" } };
}

function lastRecord() { return recordedChartOptions[recordedChartOptions.length - 1].option; }

test("format: unit rules and deterministic group color", () => {
    assert.equal(formatValue(0.873, "rate[0,1]"), "87.3%");
    assert.equal(formatValue(0.8, "ratio"), "80.0%");
    assert.equal(formatValue(0.8, "probability[0,1]"), "80.0%");
    assert.equal(formatValue(300, "seconds"), "5 minutes");
    assert.equal(formatValue(90, "seconds"), "1 min 30 s");
    assert.equal(formatValue(45, "seconds"), "45 s");
    assert.equal(formatValue(3660, "seconds"), "1 h 1 min");
    assert.equal(formatValue(0, "seconds"), "0 seconds");
    assert.equal(formatValue(360, "seconds"), "6 minutes");
    assert.equal(formatValue(0.5, "index[-1,1]"), "0.500");
    assert.equal(formatValue(1234, "count"), "1,234");
    assert.equal(formatValue(null, "count"), "—");
    assert.equal(formatValue(Number.NaN, "count"), "—");
    assert.equal(formatValue(4, "frobnicate"), "4");
    assert.equal(groupColor("alpha"), groupColor("alpha"));
    assert.equal(groupColor("alpha"), "#8E6BAF");
});

test("value: percent + supported CI + null", () => {
    const container = makeContainer();
    const instance = render("value", container, {
        aggregates: { sensitivity: 0.873, n: 1234, note: null },
        units: { sensitivity: "rate[0,1]", n: "count", note: "count" },
        ci: { sensitivity: { available: true, lower: 0.8, upper: 0.93, k: 8, n: 10, method: "wilson", confidence_level: 0.95 }, note: { available: false, reason: "too few" } },
    });
    assert.equal(instance.type, "value");
    assert.ok(collectText(container).includes("87.3%"));
    assert.ok(findByClass(container, "widget-ci"));
    assert.ok(collectText(findByClass(container, "widget-ci")).includes("95% CI"));
    assert.ok(collectText(container).includes("1,234"));
    assert.ok(collectText(container).includes("—"));
    assert.ok(findByClass(container, "widget-a11y"));
    assert.ok(collectText(findByClass(container, "widget-a11y")).includes("sensitivity 87.3%"));
    container.children.length = 0;
    render("value", container, { aggregates: { sens: 0.8 }, units: { sens: "rate[0,1]" }, ci: { sens: { available: false, reason: "low n" } } });
    assert.equal(findByClass(container, "widget-ci"), null);
});

test("value: error and empty states", () => {
    const errContainer = makeContainer();
    render("value", errContainer, { error: "boom" });
    assert.equal(collectText(findByClass(errContainer, "widget-error")), "boom");
    const emptyContainer = makeContainer();
    render("value", emptyContainer, { empty: true });
    assert.equal(collectText(findByClass(emptyContainer, "widget-empty")), "No matching records in this window.");
});

test("table: union columns, formatted numeric, null cell, pageinfo", () => {
    const container = makeContainer();
    const rows = [
        { accession: "A1", sensitivity: 0.873 },
        { accession: "A2", record_count: 7 },
        { accession: "A3", sensitivity: null, latency: 300 },
    ];
    render("table", container, { rows, units: { sensitivity: "rate[0,1]", latency: "seconds", record_count: "count" }, pagination: { page: 2, page_size: 50, returned: 3, truncated: true } });
    const table = findByClass(container, "widget-table");
    assert.ok(table);
    assert.equal(table.className.split(/\s+/).includes("widget-alt-table"), true);
    const headers = findByClass(table, "widget-thead").children[0].children.map((node) => node.textContent);
    assert.deepEqual(headers, ["accession", "sensitivity", "record_count", "latency"]);
    const bodyRows = findByClass(table, "widget-tbody").children;
    assert.equal(collectText(bodyRows[0].children[1]), "87.3%");
    assert.equal(collectText(bodyRows[1].children[1]), "—");
    assert.equal(collectText(bodyRows[1].children[2]), "7");
    assert.equal(collectText(bodyRows[2].children[1]), "—");
    assert.equal(collectText(bodyRows[2].children[3]), "5 minutes");
    assert.equal(collectText(findByClass(container, "widget-pageinfo")), "page 2 (3 shown)");
    assert.equal(container.getAttribute("role"), "region");
    assert.ok(container.getAttribute("aria-label"));
});

test("line: weekly buckets with a mid-window gap stay null and connectNulls false", () => {
    const container = makeContainer();
    const instance = render("line", container, weeklyBucketPayload());
    assert.equal(instance.type, "line");
    const option = lastRecord();
    assert.equal(option.series.length, 2);
    assert.deepEqual(option.xAxis.data, ["W1", "W2", "W3"]);
    assert.equal(option.xAxis.type, "category");
    assert.equal(option.series[0].connectNulls, false);
    assert.deepEqual(option.series[0].data, [0.8, null, 0.8]);
    assert.equal(option.series[1].data[1], null);
    assert.ok(findByClass(container, "widget-alt-table"));
    assert.equal(container.getAttribute("role"), "img");
    assert.ok(typeof container.getAttribute("aria-label") === "string");
});

test("bar: grouped bars, deterministic colors, unit-filtered benchmarks", () => {
    const container = makeContainer();
    render("bar", container, groupedBarPayload(), { benchmarks: [{ label: "target", value: 4, unit: "count" }, { label: "bad", value: 0.5, unit: "rate[0,1]" }] });
    const option = lastRecord();
    assert.equal(option.series.length, 2);
    assert.deepEqual(option.xAxis.data, ["c0", "c1", "c2"]);
    assert.equal(option.xAxis.boundaryGap, true);
    assert.deepEqual(option.series[0].data, [3, 4, 5]);
    assert.equal(option.series[0].itemStyle.color, groupColor("g0"));
    assert.equal(option.series[1].itemStyle.color, groupColor("g1"));
    assert.notEqual(option.series[0].itemStyle.color, option.series[1].itemStyle.color);
    const markLine = option.series[0].markLine;
    assert.ok(markLine, "matched benchmark should attach a markLine");
    assert.equal(markLine.data.length, 1);
    assert.ok("yAxis" in markLine.data[0], "markLine data entry must use yAxis");
    assert.equal("xAxis" in markLine.data[0], false, "markLine data entry must not use xAxis");
    assert.equal(markLine.lineStyle.type, "dashed");
    assert.equal(option.series[1].markLine, undefined, "only the first series carries the benchmark");
});

test("registry: replacement disposes once, unknown throws, disposeAll stops charts", () => {
    const firstContainer = makeContainer();
    render("value", firstContainer, { aggregates: { a: 1 }, units: { a: "count" } });
    render("value", firstContainer, { aggregates: { b: 2 }, units: { b: "count" } });
    assert.ok(findByClass(firstContainer, "widget-a11y"));
    assert.equal(collectText(firstContainer).includes("b 2"), true);
    assert.throws(() => get("nope"), RendererError);
    assert.throws(() => render("nope", makeContainer(), {}), (error) => error.name === "RendererError");
    const chartContainer = makeContainer("widget-frame widget-chart");
    const chartInstance = render("line", chartContainer, weeklyBucketPayload());
    const chartBox = chartContainer.children[0];
    assert.equal(chartBox.disposedCount, 0);
    disposeAll();
    assert.equal(chartBox.disposedCount, 1);
    chartInstance.resize();
    chartInstance.dispose();
    assert.equal(chartBox.disposedCount, 1);
});

test("registry: mirrors the api onto the host global", () => {
    assert.equal(globalThis.window.__rv2widgets.registry, registry);
});

test("one comparison dimension: line emits exactly one category axis and one series per group", () => {
    const before = recordedChartOptions.length;
    render("line", makeContainer(), weeklyBucketPayload({ groups: ["gA", "gB"] }));
    const option = lastRecord();
    assert.equal(recordedChartOptions.length, before + 1);
    assert.equal(Array.isArray(option.xAxis), false, "xAxis must be a single object, not an array");
    assert.equal(option.xAxis.type, "category");
    assert.equal(option.series.length, 2);
    assert.equal(option.series.every((entry) => entry.type === "line"), true);
});

test("source scan: no forbidden tokens in the six module files", async () => {
    const readfile = await import("node:fs/promises");
    const pathe = await import("node:path");
    const { fileURLToPath } = await import("node:url");
    const here = pathe.dirname(fileURLToPath(import.meta.url));
    const widgetDir = pathe.join(here, "..", "..", "static", "report_v2", "widgets");
    const names = ["format.mjs", "registry.mjs", "value.mjs", "table.mjs", "line.mjs", "bar.mjs"];
    const forbidden = ["inner" + "HTML", "local" + "Storage", "session" + "Storage", "indexed" + "DB", "http://cdn", "fetch" + "("];
    for (const name of names) {
        const text = await readfile.readFile(pathe.join(widgetDir, name), "utf-8");
        for (const token of forbidden) {
            assert.equal(text.toLowerCase().includes(token.toLowerCase()), false, name + " must not contain " + token);
        }
    }
});
