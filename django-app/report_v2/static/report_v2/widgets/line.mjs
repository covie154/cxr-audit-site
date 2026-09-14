import { formatValue, groupColor } from "./format.mjs";
import { el, clearContainer, observeLifecycle, buildChart } from "./registry.mjs";

const PREFERRED = ["value", "mean", "median", "sensitivity", "specificity", "positive_predictive_value"];

function isRatio(u) { const s = String(u || ""); return s.includes("rate[0,1]") || s.includes("ratio") || s.includes("probability"); }
function isTime(u) { const s = String(u || ""); return s === "seconds" || s.includes("time") || s.includes("duration"); }
function isCount(u) { const s = String(u || ""); return s === "count" || s.includes("count"); }

function matchUnit(a, b) {
    if (!a || !b) { return false; }
    if (a === b) { return true; }
    if (isRatio(a) && isRatio(b)) { return true; }
    if (isCount(a) && isCount(b)) { return true; }
    if (isTime(a) && isTime(b)) { return true; }
    return false;
}

function bucketSpine(buckets) {
    const list = Array.isArray(buckets) ? buckets.slice() : [];
    list.sort((a, b) => (Number(a && a.index) || 0) - (Number(b && b.index) || 0));
    return list;
}

function seriesFromCells(cells, spine) {
    const groups = [];
    const byGroup = new Map();
    for (const cell of cells) {
        if (!cell || typeof cell !== "object") { continue; }
        const name = String(cell.group);
        if (!byGroup.has(name)) { byGroup.set(name, []); groups.push(name); }
        byGroup.get(name).push(cell);
    }
    const series = [];
    for (const name of groups) {
        const groupCells = byGroup.get(name);
        const data = spine.map((bucket) => {
            const cell = groupCells.find((entry) => Number(entry.bucket_index) === Number(bucket.index));
            return cell ? (cell.value === null || cell.value === undefined ? null : cell.value) : null;
        });
        series.push({ name, data, unit: (groupCells.find((entry) => entry.unit) || {}).unit });
    }
    return series;
}

function scalarFallback(aggregate) {
    if (!aggregate || typeof aggregate !== "object") { return []; }
    const keys = Object.keys(aggregate);
    const chosen = PREFERRED.find((key) => typeof aggregate[key] === "number" && Number.isFinite(aggregate[key]))
        || keys.find((key) => typeof aggregate[key] === "number" && Number.isFinite(aggregate[key]));
    if (!chosen) { return []; }
    return [{ name: chosen, data: [aggregate[chosen]], unit: undefined }];
}

function buildA11y(container, series, labels, spine, units) {
    const table = el("table", "widget-a11y widget-alt-table");
    table.appendChild(el("caption", "widget-caption", series.map((entry) => entry.name).join(", ")));
    const head = el("tr", "widget-a11y-head");
    head.appendChild(el("th", "widget-a11y-corner", ""));
    for (const label of labels) { head.appendChild(el("th", "widget-a11y-col", label)); }
    table.appendChild(head);
    for (let col = 0; col < labels.length; col += 1) {
        const row = el("tr", "widget-a11y-row");
        row.appendChild(el("td", "widget-a11y-rowhead", labels[col]));
        for (const entry of series) {
            const value = entry.data[col];
            row.appendChild(el("td", "widget-a11y-cell", value === null || value === undefined ? "—" : formatValue(value, units[entry.name])));
        }
        table.appendChild(row);
    }
    container.appendChild(table);
}

export function render(container, payload, options) {
    clearContainer(container);
    let disposed = false;
    const instance = { type: "line", container, disposed: false, resize() {}, dispose() {} };
    if (payload && payload.error) {
        container.appendChild(el("p", "widget-error", String(payload.error)));
        return instance;
    }
    const opts = options || {};
    const aggregates = (payload && payload.aggregates) || {};
    const units = (payload && payload.units) || {};
    const rawSeries = payload && Array.isArray(payload.series) ? payload.series : null;
    let spine = bucketSpine(payload && payload.buckets);
    let labels = spine.map((bucket) => String(bucket.label));
    let series = [];
    if (rawSeries) {
        if (!spine.length) {
            const maxIndex = rawSeries.reduce((max, cell) => Math.max(max, Number(cell && cell.bucket_index)), -1);
            if (maxIndex >= 0) { spine = Array.from({ length: maxIndex + 1 }, (_, i) => ({ index: i, label: "b" + i })); }
        }
        labels = spine.map((bucket) => String(bucket.label));
        series = seriesFromCells(rawSeries, spine);
    }
    let preferredKey = null;
    if (!series.length) {
        const keys = Object.keys(aggregates);
        preferredKey = PREFERRED.find((key) => typeof aggregates[key] === "number" && Number.isFinite(aggregates[key]))
            || keys.find((key) => typeof aggregates[key] === "number" && Number.isFinite(aggregates[key]));
        series = scalarFallback(aggregates);
        const note = payload && payload.dates && payload.dates.coverage_note;
        if (!spine.length) { spine = [{ index: 0, label: note || "current" }]; labels = [String(spine[0].label)]; }
    }
    if (series.length === 0 || (payload && payload.empty === true)) {
        container.appendChild(el("p", "widget-empty", "No matching records in this window."));
        return instance;
    }
    let chartUnit = null;
    for (const entry of series) {
        const candidate = units[entry.name] || entry.unit;
        if (candidate) { chartUnit = candidate; break; }
    }
    const benchmarks = Array.isArray(opts.benchmarks) ? opts.benchmarks : [];
    let warned = false;
    for (const benchmark of benchmarks) {
        if (!benchmark || typeof benchmark.value !== "number" || !Number.isFinite(benchmark.value)) { continue; }
        if (!chartUnit || !matchUnit(chartUnit, benchmark.unit)) {
            if (!warned) { warned = true; globalThis.console.warn("widget-line: skipping benchmark with unit " + String(benchmark && benchmark.unit)); }
            continue;
        }
        const first = series[0];
        first.markLine = {
            silent: true, symbol: "none",
            lineStyle: { type: "dashed", color: "#7a7a7a" },
            label: { formatter: benchmark.label === undefined || benchmark.label === null ? "" : String(benchmark.label) },
            data: [{ yAxis: benchmark.value }],
        };
        break;
    }
    container.className = "widget widget-line widget-chart";
    const box = el("div", "widget-chart-box widget-chart");
    container.appendChild(box);
    const built = buildChart(box, () => disposed);
    const chart = built.chart;
    chart.setOption({
        animation: false,
        color: series.map((entry) => groupColor(entry.name)),
        legend: { data: series.map((entry) => entry.name) },
        xAxis: { type: "category", data: labels, boundaryGap: false },
        yAxis: { type: "value", scale: true },
        series: series.map((entry) => {
            const config = { name: entry.name, type: "line", data: entry.data, color: groupColor(entry.name), connectNulls: false, symbol: "circle", showSymbol: true };
            if (entry.markLine) { config.markLine = entry.markLine; }
            return config;
        }),
    }, true);
    const unitsUsed = {};
    for (const entry of series) { unitsUsed[entry.name] = units[entry.name] || entry.unit; }
    buildA11y(container, series, labels, spine, unitsUsed);
    container.setAttribute("role", "img");
    container.setAttribute("aria-label", "Line chart, " + series.length + " series: " + series.map((entry) => entry.name).join(", ") + ". " + (chartUnit || ""));
    instance.resize = () => { if (!disposed) { built.resize(); } };
    const disconnect = observeLifecycle(instance, container, () => { if (!disposed) { instance.resize(); } });
    instance.dispose = () => {
        if (disposed) { return; }
        disposed = true;
        instance.disposed = true;
        disconnect();
        built.dispose();
        clearContainer(container);
    };
    return instance;
}
