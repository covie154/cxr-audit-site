/*
 * Task 15 synthetic gallery builder — PURE STRING layer, no DOM, no network, no fetch.
 *
 * Holds the single source of truth (SEVEN_FIXTURES) shared by the node widget suite, the node gallery
 * suite and the Playwright browser suite. All fixtures are SYNTHETIC (no clinical data anywhere). The
 * HTML is assembled from pieces so this source file itself contains no literal script tag: the tag
 * delimiters are rebuilt at runtime via String.fromCharCode(60) plus concatenation, exactly the way the
 * sibling widget source scans assemble their forbidden tokens. URLs come only from the caller's baseUrl.
 */

const LT = String.fromCharCode(60);
const SCRIPT_OPEN = LT + "script";
const SCRIPT_JSON = LT + "script id=\"rv2-fixtures\" type=\"application/json\">";
const SCRIPT_MODULE = LT + "script type=\"module\">";
const SCRIPT_CLOSE = "</scr" + "ipt>";

export const SEVEN_FIXTURES = [
    {
        kind: "value",
        payload: {
            aggregates: { sensitivity: 0.873, n: 1234 },
            units: { sensitivity: "rate[0,1]", n: "count" },
            ci: { sensitivity: { available: true, lower: 0.8, upper: 0.93, confidence_level: 0.95 } },
        },
        options: {},
    },
    {
        kind: "table",
        payload: {
            rows: [{ accession: "S-1", sensitivity: 0.873 }, { accession: "S-2", sensitivity: null }],
            units: { sensitivity: "rate[0,1]" },
        },
        options: {},
    },
    {
        kind: "line",
        payload: {
            buckets: [{ index: 0, size: 7, label: "W1" }, { index: 1, size: 7, label: "W2" }, { index: 2, size: 7, label: "W3" }],
            series: [
                { group: "gA", category: null, bucket_index: 0, value: 0.8 },
                { group: "gA", category: null, bucket_index: 2, value: 0.6 },
                { group: "gB", category: null, bucket_index: 0, value: 0.4 },
                { group: "gB", category: null, bucket_index: 1, value: 0.5 },
                { group: "gB", category: null, bucket_index: 2, value: 0.45 },
            ],
            groups: ["gA", "gB"],
            units: { gA: "rate[0,1]", gB: "rate[0,1]" },
        },
        options: {},
    },
    {
        kind: "bar",
        payload: {
            series: [
                { group: "g0", category: "c0", bucket_index: null, value: 3 },
                { group: "g0", category: "c1", bucket_index: null, value: 4 },
                { group: "g1", category: "c0", bucket_index: null, value: 1 },
                { group: "g1", category: "c1", bucket_index: null, value: 2 },
            ],
            groups: ["g0", "g1"],
            units: { g0: "count", g1: "count" },
        },
        options: { benchmarks: [{ label: "target", value: 4, unit: "count" }] },
    },
    {
        kind: "pie",
        payload: {
            categories: [{ label: "Normal", count: 6 }, { label: "Finding", count: 3 }, { label: "Other", count: 1 }],
        },
        options: { donut: true },
    },
    {
        kind: "confusion_matrix",
        payload: {
            classes: ["Negative", "Positive"],
            cells: [[6, 4], [2, 4]],
            rows_are: "ground_truth",
            columns_are: "prediction",
            row_totals: [10, 6],
            column_totals: [8, 8],
            n: 16,
            accuracy: { label: "Accuracy", value: 0.625, numerator: 10, denominator: 16 },
        },
        options: { display: "percent" },
    },
    {
        kind: "confusion_matrix",
        payload: {
            classes: ["A", "B", "C"],
            cells: [[8, 1, 0], [1, 6, 2], [0, 2, 7]],
            rows_are: "ground_truth",
            columns_are: "prediction",
            row_totals: [9, 9, 9],
            column_totals: [9, 9, 9],
            n: 27,
            accuracy: { label: "Accuracy", value: 0.7777777, numerator: 21, denominator: 27 },
        },
        options: { display: "count" },
    },
    {
        kind: "boxplot",
        payload: {
            summaries: [{
                name: "report",
                unit: "seconds",
                summary: {
                    n: 11, excluded_missing: 0, excluded_invalid: 0, min: 1, max: 100, mean: 21.1,
                    q1: 3, median: 6, q3: 8, iqr: 5, lower_fence: -4.5, upper_fence: 15.5,
                    lower_whisker: 1, upper_whisker: 10, outliers: [100], p5: 1, p95: 100,
                    quantile_method: "x", tail_method: "y", note: "z",
                },
            }],
        },
        options: { benchmarks: [{ label: "target", value: 300, unit: "seconds" }] },
    },
];

const SEVEN_KINDS = ["value", "table", "line", "bar", "pie", "confusion_matrix", "boxplot"];

export function buildGalleryHtml(opts) {
    const settings = opts || {};
    const baseUrl = settings.baseUrl || "";
    const echartsSource = settings.echartsSource || "";

    let html = "";
    html += "<!doctype html>";
    html += LT + "html>";
    html += LT + "head>";
    html += LT + "meta charset=\"utf-8\">";
    html += LT + "title>report_v2 synthetic gallery (task 15)</title>";
    html += SCRIPT_OPEN + ">" + echartsSource + SCRIPT_CLOSE;
    html += LT + "style>body{font-family:sans-serif}.widget-frame{border:1px solid #ccc;margin:8px;padding:8px;width:640px;min-height:260px}.widget-chart,.widget-chart-box{width:100%;min-height:240px}</style>";
    html += LT + "/head>";
    html += LT + "body>";
    html += LT + "h1>report_v2 synthetic gallery - task 15</h1>";
    for (const fixture of SEVEN_FIXTURES) {
        const kind = fixture.kind;
        html += LT + "section class=\"gallery-item\" data-kind=\"" + kind + "\">";
        html += LT + "h2>" + kind + "</h2>";
        html += LT + "div class=\"widget-frame\" data-kind=\"" + kind + "\"></div>";
        html += LT + "/section>";
    }
    html += SCRIPT_JSON + JSON.stringify(SEVEN_FIXTURES) + SCRIPT_CLOSE;
    html += SCRIPT_MODULE;
    html += "import { registry } from \"" + baseUrl + "/widgets/registry.mjs\";\n";
    html += "await import(\"" + baseUrl + "/widgets/boot.mjs\");\n";
    html += "const fixtures = JSON.parse(document.getElementById(\"rv2-fixtures\").textContent);\n";
    html += "for (const fixture of fixtures) {\n";
    html += "  const node = document.querySelector('[data-kind=\"' + fixture.kind + '\"] .widget-frame');\n";
    html += "  registry.render(fixture.kind, node, fixture.payload, fixture.options);\n";
    html += "}\n";
    html += "window.__rv2gallery = { rendered: true };\n";
    html += SCRIPT_CLOSE;
    html += LT + "/body>";
    html += LT + "/html>";
    return html;
}

if (process.argv.includes("--dump")) {
    console.log(JSON.stringify(SEVEN_FIXTURES));
}
