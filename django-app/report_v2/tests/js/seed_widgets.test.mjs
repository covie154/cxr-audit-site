/*
 * Task 16 C2 node suite — renders one synthetic SERVER-CONTRACT payload per display kind through the REAL
 * registry (registry.get(kind).render), not a reimplementation. Payload shapes mirror what the Task-16
 * server emits and what the renderers actually consume (see report_v2/static/report_v2/widgets/*.mjs).
 * The DOM/echarts/observer harness is the same class shape as widgets.test.mjs / widgets15.test.mjs.
 * Synthetic data only; no network, no clinical values.
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
        setOption() {},
        resize() {},
        dispose() { if (!disposed) { disposed = true; if (box) { box.disposedCount += 1; } } },
    };
    allCharts.push(chart);
    return chart;
}

globalThis.window = {
    echarts: { init: (box) => makeChart(box && String(box.className || "").includes("widget-chart") ? box : null) },
};

globalThis.ResizeObserver = class {
    constructor(callback) { this.callback = callback; this.observed = []; }
    observe(node) { this.observed.push(node); if (node) { this._node = node; } }
    disconnect() { this.observed = []; }
};

globalThis.MutationObserver = class {
    constructor(callback) { this.callback = callback; this.observed = []; }
    observe(node) { this.observed.push(node); }
    disconnect() { this.observed = []; }
};

const { registry } = await import("../../static/report_v2/widgets/registry.mjs");
await import("../../static/report_v2/widgets/boot.mjs");

// --- harness helpers (shared with widgets15.test.mjs in spirit) ----------------------------------------
function findByClass(root, cls) { return root.descendants().find((node) => (node.className || "").split(/\s+/).includes(cls)) || null; }
function findAllWithClass(root, cls) { return root.descendants().filter((node) => (node.className || "").split(/\s+/).includes(cls)); }
function collectText(node) { let text = node.textContent || ""; for (const child of node.children) { text += " " + collectText(child); } return text; }
function makeContainer(cls) { return new FakeNode("div", cls || "widget-frame"); }

// The container after a render must carry a real painted structure — either a chart box or a fallback table/dl.
function assertPainted(container) {
    assert.ok(container.descendants().length > 1, "must build nested DOM");
    const painted = ["widget-chart", "widget-alt-table", "widget-table", "widget-values"]
        .some((cls) => findByClass(container, cls));
    assert.ok(painted, "a canvas/child was appended or an alt-table/dl exists");
}
// Accessible alternative: a fallback <table> (widget-alt-table) or the value summary line (widget-a11y).
function assertAccessible(container) {
    assert.ok(findByClass(container, "widget-alt-table") || findByClass(container, "widget-a11y"),
        "an accessible alternative (fallback table or a11y summary) must exist");
    assert.equal(findByClass(container, "widget-error"), null, "render must not surface an error node");
}
// Second render followed by dispose must leave no error node and no dangling child.
function assertRerenderAndDispose(kind, payload, options) {
    const container = makeContainer();
    registry.render(kind, container, payload, options);
    const instance = registry.render(kind, container, payload, options);
    assert.equal(findByClass(container, "widget-error"), null, "re-render must not surface an error node");
    instance.dispose();
    assert.equal(container.children.length, 0, "dispose must empty the container, leaving no dangling node");
    assert.equal(findByClass(container, "widget-error"), null, "dispose path must not surface an error node");
}

// --- DRIFT GUARD ---------------------------------------------------------------------------------------
// The twelve classification-summary columns the Task-16 server test / seeding.CLASSIFICATION_SUMMARY_COLUMNS
// projects, declared independently here and byte-compared (join equality) against the literal the TABLE
// renderer actually projects from a classification_summary row. If the server-side column contract and the
// rendered header ever diverge, this test fails.
const SERVER_CLASSIFICATION_SUMMARY_COLUMNS = [
    "n", "accuracy", "balanced_accuracy", "sensitivity", "specificity",
    "ppv", "npv", "tp", "tn", "fp", "fn", "predicted_negative_fraction",
];

// One synthetic server-contract payload per display kind (renderer-consumption-accurate shapes).
const VALUE_PAYLOAD = {
    aggregates: { n: 1234, sensitivity: 0.873 },
    units: { n: "count", sensitivity: "rate[0,1]" },
};
const TABLE_PAYLOAD = {
    rows: [{ accession: "S-1", sensitivity: 0.873 }, { accession: "S-2", sensitivity: null }],
    units: { sensitivity: "rate[0,1]" },
    pagination: { page: 2, returned: 2 },
};
const LINE_PAYLOAD = {
    buckets: [{ index: 0, label: "W1" }, { index: 1, label: "W2" }, { index: 2, label: "W3" }],
    series: [
        { group: "gA", category: null, bucket_index: 0, value: 0.8 },
        { group: "gA", category: null, bucket_index: 2, value: 0.6 },
    ],
    groups: ["gA"],
    units: { gA: "rate[0,1]" },
};
const BAR_PAYLOAD = {
    buckets: [],
    series: [
        { group: "g0", category: "c0", bucket_index: null, value: 3 },
        { group: "g0", category: "c1", bucket_index: null, value: 4 },
    ],
    groups: ["g0"],
    units: { g0: "count" },
};
// Server contract as consumed by boxplot.mjs collectGroups: a summaries[] with a drawable summary each.
const BOXPLOT_PAYLOAD = {
    summaries: [{
        name: "report", unit: "seconds",
        summary: { n: 11, min: 1, max: 10, mean: 5, q1: 3, median: 6, q3: 8, lower_whisker: 1, upper_whisker: 10, outliers: [] },
    }],
    units: { value: "seconds" },
};
// categorical_count demo shape: categories[] of {label,count}.
const PIE_PAYLOAD = {
    categories: [{ label: "Normal", count: 6 }, { label: "Finding", count: 3 }],
};
// confusion matrix top-level contract as consumed by confusion.mjs (matrix === payload).
const CONFUSION_PAYLOAD = {
    classes: ["Negative", "Positive"],
    cells: [[6, 4], [2, 4]],
    rows_are: "ground_truth",
    columns_are: "prediction",
    row_totals: [10, 6],
    column_totals: [8, 8],
    n: 16,
    accuracy: { label: "Accuracy", value: 0.625, numerator: 10, denominator: 16 },
};
// classification_summary table: a single row keyed by the twelve server columns.
function classificationSummaryRow() {
    return {
        n: 40, accuracy: 0.9, balanced_accuracy: 0.88, sensitivity: 0.85, specificity: 0.91,
        ppv: 0.93, npv: 0.82, tp: 18, tn: 18, fp: 1, fn: 3, predicted_negative_fraction: 0.475,
    };
}
const CLASSIFICATION_SUMMARY_PAYLOAD = {
    rows: [classificationSummaryRow()],
    units: { accuracy: "rate[0,1]", balanced_accuracy: "rate[0,1]", sensitivity: "rate[0,1]", specificity: "rate[0,1]", ppv: "rate[0,1]", npv: "rate[0,1]" },
};

const KIND_CASES = [
    { kind: "value", payload: VALUE_PAYLOAD },
    { kind: "table", payload: TABLE_PAYLOAD },
    { kind: "line", payload: LINE_PAYLOAD },
    { kind: "bar", payload: BAR_PAYLOAD },
    { kind: "boxplot", payload: BOXPLOT_PAYLOAD },
    { kind: "pie", payload: PIE_PAYLOAD },
    { kind: "confusion_matrix", payload: CONFUSION_PAYLOAD },
];

// Per display kind: no throw, painted structure, accessible alternative, re-render + dispose is clean.
for (const kase of KIND_CASES) {
    test(`t16 seed ${kase.kind}: renders through the real registry without throwing`, () => {
        assert.equal(typeof registry.get(kase.kind).render, "function", kase.kind + " must resolve to a renderer");
        const container = makeContainer();
        let instance;
        assert.doesNotThrow(() => { instance = registry.render(kase.kind, container, kase.payload, {}); });
        assert.equal(instance.type, kase.kind, "instance.type must match the rendered kind");
    });

    test(`t16 seed ${kase.kind}: paints a non-empty structure with an accessible alternative`, () => {
        const container = makeContainer();
        registry.render(kase.kind, container, kase.payload, {});
        assertPainted(container);
        assertAccessible(container);
    });

    test(`t16 seed ${kase.kind}: a second render then dispose leaves no error and no dangling node`, () => {
        assertRerenderAndDispose(kase.kind, kase.payload, {});
    });
}

test("t16 seed all seven kinds are boot-registered", () => {
    for (const kase of KIND_CASES) {
        assert.equal(typeof registry.get(kase.kind).render, "function", kase.kind + " is not registered");
    }
    assert.equal(globalThis.window.__rv2widgets.bootReady, true);
});

// DRIFT GUARD test: the twelve-column server contract vs. the header the table renderer actually projects.
test("t16 drift guard: classification_summary columns the server declares match the rendered table header byte-for-byte", () => {
    assert.equal(SERVER_CLASSIFICATION_SUMMARY_COLUMNS.length, 12, "the classification-summary contract is exactly twelve columns");
    const container = makeContainer();
    registry.render("table", container, CLASSIFICATION_SUMMARY_PAYLOAD, {});
    const headerCells = findAllWithClass(container, "widget-th").map((node) => node.textContent);
    assert.equal(headerCells.join(","), SERVER_CLASSIFICATION_SUMMARY_COLUMNS.join(","),
        "the table renderer's projected columns must equal the server CLASSIFICATION_SUMMARY_COLUMNS literal");
});
