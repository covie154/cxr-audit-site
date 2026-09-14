/*
 * Task 15 node widget suite — exercises the SEVEN boot-registered renderers through the real registry
 * against the canonical synthetic fixtures owned by ./gallery/synthetic_gallery.mjs. The DOM/echarts/
 * observer harness is the same class shape as widgets.test.mjs; boot.mjs performs every registration so
 * this file resolves value/table/line/bar/pie/confusion_matrix/boxplot through registry.get(k).render.
 * Pins the two task-15b amend fixes (boxplot n-as-count cell, pie null-count cell) plus the shared
 * empty/error/dispose contracts. Synthetic data only; no network, no clinical values.
 */
import { test } from 'node:test';
import assert from 'node:assert/strict';

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

import { formatValue, groupColor } from "../../static/report_v2/widgets/format.mjs";
import * as pieRenderer from "../../static/report_v2/widgets/pie.mjs";
import * as confusionRenderer from "../../static/report_v2/widgets/confusion.mjs";
import * as boxplotRenderer from "../../static/report_v2/widgets/boxplot.mjs";

const { registry } = await import("../../static/report_v2/widgets/registry.mjs");
await import("../../static/report_v2/widgets/boot.mjs");
const { SEVEN_FIXTURES } = await import("./gallery/synthetic_gallery.mjs");

function findByClass(root, cls) { return root.descendants().find((node) => (node.className || "").split(/\s+/).includes(cls)) || null; }
function collectText(node) { let text = node.textContent || ""; for (const child of node.children) { text += " " + collectText(child); } return text; }
function makeContainer(cls) { return new FakeNode("div", cls || "widget-frame"); }
function lastRecord() { return recordedChartOptions[recordedChartOptions.length - 1].option; }
function byKind(kind) { return SEVEN_FIXTURES.find((fixture) => fixture.kind === kind); }
function confusionFixtures() { return SEVEN_FIXTURES.filter((fixture) => fixture.kind === "confusion_matrix"); }
function boxFixture() { return byKind("boxplot"); }
function tableHead(table) { return findByClass(table, "widget-a11y-head"); }
function tableBodyRows(table) { return table.children.filter((node) => (node.className || "").split(/\s+/).includes("widget-a11y-row")); }
function rowCells(row) { return row.children.filter((node) => (node.className || "").split(/\s+/).includes("widget-a11y-cell")); }
function collectKeys(node, out) {
    if (node && typeof node === "object") {
        for (const key of Object.keys(node)) { out.push(key); collectKeys(node[key], out); }
    }
    return out;
}

const SEVEN_KINDS = ["value", "table", "line", "bar", "pie", "confusion_matrix", "boxplot"];

test("t1 boot resolves all seven kinds and flags bootReady", () => {
    for (const kind of SEVEN_KINDS) {
        assert.equal(typeof registry.get(kind).render, "function", kind + " must resolve to a renderer");
    }
    assert.equal(globalThis.window.__rv2widgets.bootReady, true);
});

test("t2 registry renders the donut pie through a single pie series", () => {
    const fixture = byKind("pie");
    const container = makeContainer();
    const instance = registry.render("pie", container, fixture.payload, fixture.options);
    assert.equal(instance.type, "pie");
    const option = lastRecord();
    assert.equal(option.series.length, 1);
    assert.equal(option.series[0].type, "pie");
    assert.deepEqual(option.series[0].data.map((d) => d.name), ["Normal", "Finding", "Other"]);
    assert.deepEqual(option.series[0].data.map((d) => d.value), [6, 3, 1]);
    assert.deepEqual(option.series[0].radius, ["45%", "70%"]);
    assert.equal(option.color[0], groupColor("Normal"));
});

test("t3 direct pie render without donut collapses radius to a single string", () => {
    const fixture = byKind("pie");
    const container = makeContainer();
    pieRenderer.render(container, fixture.payload, {});
    assert.equal(lastRecord().series[0].radius, "70%");
});

test("t4 pie alt table exposes category/count/share and the caption", () => {
    const fixture = byKind("pie");
    const container = makeContainer();
    registry.render("pie", container, fixture.payload, fixture.options);
    const text = collectText(container);
    for (const token of ["category", "count", "share", "6", "60.0%", "30.0%", "10.0%"]) {
        assert.ok(text.includes(token), "expected " + token + " in the alt table");
    }
    assert.ok(text.includes("Category counts and shares"));
});

test("t5 pie ignores benchmarks entirely (no markLine at any depth)", () => {
    const fixture = byKind("pie");
    const container = makeContainer();
    registry.render("pie", container, fixture.payload, { benchmarks: [{ label: "x", value: 9, unit: "count" }] });
    const keys = collectKeys(lastRecord(), []);
    assert.equal(keys.includes("markLine"), false, "a share chart must never attach a benchmark line");
});

test("t6 pie empty and error paths", () => {
    const emptyA = makeContainer();
    registry.render("pie", emptyA, { categories: [] }, {});
    assert.equal(collectText(findByClass(emptyA, "widget-empty")), "No matching records in this window.");
    const emptyB = makeContainer();
    registry.render("pie", emptyB, { categories: [{ label: "a", count: 0 }] }, {});
    assert.equal(collectText(findByClass(emptyB, "widget-empty")), "No matching records in this window.");
    const errored = makeContainer();
    registry.render("pie", errored, { error: "boom" }, {});
    assert.equal(collectText(findByClass(errored, "widget-error")), "boom");
});

test("t7 pie falls back to aggregates when no categories are present", () => {
    const container = makeContainer();
    registry.render("pie", container, { aggregates: { a: 2, b: 4 } }, {});
    assert.deepEqual(lastRecord().series[0].data, [{ name: "a", value: 2 }, { name: "b", value: 4 }]);
});

test("t7b (amend FIX 2) pie renders a null count as an em dash and keeps the share", () => {
    const container = makeContainer();
    registry.render("pie", container, { categories: [{ label: "a", count: 5 }, { label: "b", count: null }] }, {});
    const table = findByClass(container, "widget-alt-table");
    assert.ok(table, "alt table must exist");
    const rows = tableBodyRows(table);
    const aCells = rowCells(rows[0]).map((cell) => collectText(cell));
    const bCells = rowCells(rows[1]).map((cell) => collectText(cell));
    assert.equal(bCells[1], "—");
    assert.equal(aCells[1], "5");
    assert.equal(aCells[2], "100.0%");
    assert.equal(bCells[2], "0.0%");
});

test("t8 confusion binary percent cells, attributes, and summary line", () => {
    const fixture = confusionFixtures()[0];
    const container = makeContainer();
    registry.render("confusion_matrix", container, fixture.payload, fixture.options);
    const table = findByClass(container, "widget-confusion");
    assert.ok(table, "confusion table must carry widget-confusion");
    const head = tableHead(table);
    assert.deepEqual(head.children.map((node) => collectText(node)), ["GT \\ Pred", "Negative", "Positive"]);
    const rows = tableBodyRows(table);
    assert.equal(collectText(rows[0].children[0]), "Negative");
    assert.deepEqual(rowCells(rows[0]).map((cell) => collectText(cell)), ["60.0%", "40.0%"]);
    assert.deepEqual(rowCells(rows[1]).map((cell) => collectText(cell)), ["33.3%", "66.7%"]);
    for (const cell of rowCells(rows[0])) {
        assert.equal(cell.getAttribute("data-normalised"), "value");
        assert.ok(cell.getAttribute("data-row-class"));
        assert.ok(cell.getAttribute("data-col-class"));
    }
    assert.equal(collectText(findByClass(container, "widget-summary-line")), "Accuracy: 62.5%");
    const offenders = container.descendants().filter((node) => {
        const cn = (node.className || "").toLowerCase();
        return cn.includes("benchmark") || cn.includes("mark");
    });
    assert.deepEqual(offenders.map((node) => node.className), []);
});

test("t9 confusion multiclass count cells and the a11y label", () => {
    const fixture = confusionFixtures()[1];
    const container = makeContainer();
    registry.render("confusion_matrix", container, fixture.payload, fixture.options);
    const table = findByClass(container, "widget-confusion");
    assert.ok((table.className || "").split(/\s+/).includes("widget-confusion"));
    assert.deepEqual(tableHead(table).children.map((node) => collectText(node)), ["GT \\ Pred", "A", "B", "C"]);
    assert.deepEqual(tableBodyRows(table).map((row) => rowCells(row).map((cell) => collectText(cell))), [["8", "1", "0"], ["1", "6", "2"], ["0", "2", "7"]]);
    const aria = container.getAttribute("aria-label");
    assert.ok(aria.includes("3 by 3"));
    assert.ok(aria.includes("rows ground truth, columns prediction"));
});

test("t10 confusion zero-denominator row degrades to unavailable", () => {
    const container = makeContainer();
    registry.render("confusion_matrix", container, { classes: ["A", "B"], cells: [[0, 0], [3, 1]], row_totals: [0, 4], column_totals: [3, 1], n: 4, accuracy: { value: null } }, { display: "percent" });
    const rows = tableBodyRows(findByClass(container, "widget-confusion"));
    const zeroCells = rowCells(rows[0]);
    assert.deepEqual(zeroCells.map((cell) => collectText(cell)), ["unavailable", "unavailable"]);
    for (const cell of zeroCells) { assert.equal(cell.getAttribute("data-normalised"), "unavailable"); }
    assert.deepEqual(rowCells(rows[1]).map((cell) => collectText(cell)), ["75.0%", "25.0%"]);
    assert.equal(collectText(findByClass(container, "widget-summary-line")), "Accuracy: unavailable");
});

test("t11 confusion empty, error, and idempotent dispose", () => {
    const emptyC = makeContainer();
    registry.render("confusion_matrix", emptyC, { classes: [] }, {});
    assert.equal(collectText(findByClass(emptyC, "widget-empty")), "No matching records in this window.");
    const errored = makeContainer();
    registry.render("confusion_matrix", errored, { error: "boom" }, {});
    assert.equal(collectText(findByClass(errored, "widget-error")), "boom");
    const live = makeContainer();
    const instance = registry.render("confusion_matrix", live, confusionFixtures()[0].payload, confusionFixtures()[0].options);
    assert.ok(findByClass(live, "widget-confusion"));
    instance.dispose();
    instance.dispose();
    assert.equal(live.children.length, 0, "dispose must empty the container and stay idempotent");
});

test("t12 box builds a boxplot series plus a scatter outlier series from observed values", () => {
    const fixture = boxFixture();
    const container = makeContainer();
    registry.render("boxplot", container, fixture.payload, {});
    const option = lastRecord();
    assert.deepEqual(option.series.map((entry) => entry.type), ["boxplot", "scatter"]);
    assert.deepEqual(option.series[0].data, [[1, 3, 6, 8, 10]]);
    const flat = JSON.stringify(option.series[0].data);
    assert.equal(flat.includes("-4.5"), false);
    assert.equal(flat.includes("15.5"), false);
    assert.deepEqual(option.series[1].data, [[0, 100]]);
    assert.deepEqual(option.xAxis.data, ["report"]);
});

test("t13 box benchmark markLine formats the duration label", () => {
    const fixture = boxFixture();
    const container = makeContainer();
    registry.render("boxplot", container, fixture.payload, { benchmarks: [{ label: "target", value: 300, unit: "seconds" }] });
    const markLine = lastRecord().series[0].markLine;
    assert.equal(markLine.data[0].yAxis, 300);
    assert.equal(markLine.lineStyle.type, "dashed");
    assert.equal(typeof markLine.label.formatter, "string");
    assert.ok(markLine.label.formatter.includes("5 minutes"));
    assert.equal(markLine.label.formatter.includes("300 s"), false);
    assert.equal(lastRecord().yAxis.axisLabel.formatter(300), "5 minutes");
});

test("t14 box drops a benchmark whose unit cannot match the plot unit", () => {
    const fixture = boxFixture();
    const container = makeContainer();
    registry.render("boxplot", container, fixture.payload, { benchmarks: [{ label: "bad", value: 0.9, unit: "rate[0,1]" }] });
    assert.equal(lastRecord().series[0].markLine, undefined);
});

test("t15 box alt table mirrors formatValue and treats n as a plain count", () => {
    const fixture = boxFixture();
    const container = makeContainer();
    registry.render("boxplot", container, fixture.payload, {});
    const table = findByClass(container, "widget-alt-table");
    assert.ok(table, "alt table must exist");
    const headers = tableHead(table).children.map((node) => collectText(node));
    for (const h of ["n", "group", "min", "lower whisker", "Q1", "median", "Q3", "upper whisker", "max", "outliers"]) {
        assert.ok(headers.includes(h), "header " + h + " missing");
    }
    assert.ok(collectText(findByClass(table, "widget-caption")).includes("1.5*IQR"));
    const row = tableBodyRows(table)[0];
    const cells = rowCells(row).map((cell) => collectText(cell));
    // layout: [n, group, min, lower whisker, Q1, median, Q3, upper whisker, max, outliers]
    assert.equal(cells[0], formatValue(11, "count"));
    assert.equal(cells[1], "report");
    assert.equal(cells[2], formatValue(1, "seconds"));
    assert.equal(cells[3], formatValue(1, "seconds"));
    assert.equal(cells[4], formatValue(3, "seconds"));
    assert.equal(cells[5], formatValue(6, "seconds"));
    assert.equal(cells[6], formatValue(8, "seconds"));
    assert.equal(cells[7], formatValue(10, "seconds"));
    assert.equal(cells[8], formatValue(100, "seconds"));
    assert.equal(cells[9], formatValue(100, "seconds"));
});

test("t15b (amend FIX 1) box n cell is a bare count, not a duration", () => {
    const fixture = boxFixture();
    const container = makeContainer();
    registry.render("boxplot", container, fixture.payload, {});
    const cells = rowCells(tableBodyRows(findByClass(container, "widget-alt-table"))[0]).map((cell) => collectText(cell));
    assert.equal(cells[0], "11");
    assert.equal(cells[0].includes(" s"), false);
    assert.equal(cells[5], "6 s");
});

test("t16 box empty and error paths", () => {
    const partial = makeContainer();
    registry.render("boxplot", partial, { summaries: [{ name: "g", unit: "seconds", summary: { n: 3, min: 1, max: 9, mean: 5, q1: null, median: 5, q3: 8, lower_whisker: 1, upper_whisker: 9 } }] }, {});
    assert.equal(collectText(findByClass(partial, "widget-empty")), "No matching records in this window.");
    const emptyC = makeContainer();
    registry.render("boxplot", emptyC, { summaries: [] }, {});
    assert.equal(collectText(findByClass(emptyC, "widget-empty")), "No matching records in this window.");
    const errored = makeContainer();
    registry.render("boxplot", errored, { error: "boom" }, {});
    assert.equal(collectText(findByClass(errored, "widget-error")), "boom");
});

test("t17 the seven fixtures render through the registry and build nested DOM", () => {
    assert.deepEqual(SEVEN_FIXTURES.map((fixture) => fixture.kind), ["value", "table", "line", "bar", "pie", "confusion_matrix", "confusion_matrix", "boxplot"]);
    for (const fixture of SEVEN_FIXTURES) {
        assert.equal(typeof registry.get(fixture.kind).render, "function", fixture.kind + " must resolve");
        const container = makeContainer();
        const instance = registry.render(fixture.kind, container, fixture.payload, fixture.options);
        assert.equal(instance.type, fixture.kind);
        assert.ok(container.descendants().length > 1, fixture.kind + " must build nested DOM");
    }
});

test("t18 source scan: the three chart widgets carry no forbidden host tokens", async () => {
    const readfile = await import("node:fs/promises");
    const pathe = await import("node:path");
    const { fileURLToPath } = await import("node:url");
    const here = pathe.dirname(fileURLToPath(import.meta.url));
    const widgetDir = pathe.join(here, "..", "..", "static", "report_v2", "widgets");
    const forbidden = ["inner" + "HTML", "local" + "Storage", "session" + "Storage", "indexed" + "DB", "http://cdn", "fetch" + "("];
    for (const name of ["pie.mjs", "confusion.mjs", "boxplot.mjs"]) {
        const text = await readfile.readFile(pathe.join(widgetDir, name), "utf-8");
        for (const token of forbidden) {
            assert.equal(text.toLowerCase().includes(token.toLowerCase()), false, name + " must not contain " + token);
        }
    }
});
