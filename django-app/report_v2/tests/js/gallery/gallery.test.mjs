/*
 * Task 15 gallery contract suite — validates the synthetic_gallery builder's pure-string output and
 * re-renders every shared fixture through the real registry. The DOM/echarts/observer harness matches
 * widgets.test.mjs (same class shapes) so registry renderers run headlessly. Synthetic data only; the
 * builder source scan proves it stays network-free / inner-HTML-free. Run: node --test on this file.
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

globalThis.document = {
    createElement: (tag) => new FakeNode(tag),
    createTextNode: (text) => { const node = new FakeNode("#text"); node.textContent = text; node.nodeType = 3; return node; },
    documentElement: new FakeNode("html"),
};

function makeChart(box) {
    let disposed = false;
    const chart = {
        box,
        setOption(option, config) { recordedChartOptions.push({ option, config }); },
        resize() {},
        dispose() { if (!disposed) { disposed = true; if (box) { box.disposedCount += 1; } } },
    };
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

const { SEVEN_FIXTURES, buildGalleryHtml } = await import("./synthetic_gallery.mjs");
const { registry } = await import("../../../static/report_v2/widgets/registry.mjs");
await import("../../../static/report_v2/widgets/boot.mjs");

function makeContainer(cls) { return new FakeNode("div", cls || "widget-frame"); }

const SEVEN_KINDS = ["value", "table", "line", "bar", "pie", "confusion_matrix", "boxplot"];
const SCRIPT_CLOSE = "</scr" + "ipt>";
const SENTINEL = "/*ECHARTS-SRC-SENTINEL*/";

test("g1 SEVEN_FIXTURES covers the seven kinds across eight sections", () => {
    assert.ok(SEVEN_FIXTURES.length >= 8);
    for (const kind of SEVEN_KINDS) {
        assert.ok(SEVEN_FIXTURES.some((fixture) => fixture.kind === kind), kind + " must be present");
    }
    assert.equal(SEVEN_FIXTURES.filter((fixture) => fixture.kind === "confusion_matrix").length, 2);
});

test("g2 buildGalleryHtml embeds echarts, the module imports, and every data-kind", () => {
    const html = buildGalleryHtml({ baseUrl: "http://rv2gallery.test", echartsSource: SENTINEL });
    assert.ok(html.includes(SENTINEL), "echarts source sentinel must be embedded");
    assert.ok(html.includes("/widgets/registry.mjs"), "module must import the registry");
    assert.ok(html.includes("/widgets/boot.mjs"), "module must import boot");
    for (const kind of SEVEN_KINDS) {
        assert.ok(html.includes('data-kind="' + kind + '"'), kind + " needs a data-kind frame");
    }
    assert.ok(
        html.includes(".widget-chart,.widget-chart-box{width:100%;min-height:240px}"),
        "inline chart-box sizing rule must ship in the gallery <style>",
    );
});

test("g3 the document declares exactly eight widget-frame elements", () => {
    const html = buildGalleryHtml({ baseUrl: "http://rv2gallery.test", echartsSource: SENTINEL });
    const count = html.split('class="widget-frame"').length - 1;
    assert.equal(count, 8);
});

test("g4 the embedded fixtures JSON round-trips to SEVEN_FIXTURES", () => {
    const html = buildGalleryHtml({ baseUrl: "http://rv2gallery.test", echartsSource: SENTINEL });
    const markerStart = html.indexOf('id="rv2-fixtures"');
    assert.ok(markerStart >= 0, "fixtures script element must exist");
    const region = html.slice(markerStart);
    const body = region.slice(0, region.indexOf(SCRIPT_CLOSE));
    const json = body.slice(body.indexOf("["), body.lastIndexOf("]") + 1);
    assert.deepEqual(JSON.parse(json), SEVEN_FIXTURES);
});

test("g5 the builder source carries no network or inner-HTML tokens", async () => {
    const readfile = await import("node:fs/promises");
    const pathe = await import("node:path");
    const { fileURLToPath } = await import("node:url");
    const here = pathe.dirname(fileURLToPath(import.meta.url));
    const text = await readfile.readFile(pathe.join(here, "synthetic_gallery.mjs"), "utf-8");
    for (const token of ["fetch" + "(", "XMLHttp" + "Request", "http://cdn", "inner" + "HTML"]) {
        assert.equal(text.toLowerCase().includes(token.toLowerCase()), false, "builder must not contain " + token);
    }
});

test("g6 every shared fixture renders through the registry into nested DOM", () => {
    for (const fixture of SEVEN_FIXTURES) {
        const container = makeContainer();
        const instance = registry.render(fixture.kind, container, fixture.payload, fixture.options);
        assert.equal(instance.type, fixture.kind);
        assert.ok(container.descendants().length > 1, fixture.kind + " must build nested DOM");
    }
});
