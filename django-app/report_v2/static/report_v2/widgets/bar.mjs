import { formatValue, groupColor } from "./format.mjs";
import { el, clearContainer, observeLifecycle, buildChart } from "./registry.mjs";

const PREFERRED = ["value", "mean", "median", "n", "count"];

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

function groupCells(cells) {
    const groups = [];
    const byGroup = new Map();
    for (const cell of cells) {
        if (!cell || typeof cell !== "object") { continue; }
        const name = String(cell.group);
        if (!byGroup.has(name)) {
            byGroup.set(name, { cats: new Map(), buckets: new Map(), unit: undefined });
            groups.push(name);
        }
        const store = byGroup.get(name);
        if (cell.category !== null && cell.category !== undefined) { store.cats.set(cell.category, cell.value); }
        else if (cell.bucket_index !== null && cell.bucket_index !== undefined) { store.buckets.set(Number(cell.bucket_index), cell.value); }
        if (cell.unit && store.unit === undefined) { store.unit = cell.unit; }
    }
    return { groups, byGroup };
}

function spineFor(cells, buckets) {
    const categories = [];
    let sawBucket = false;
    for (const cell of cells) {
        if (!cell || typeof cell !== "object") { continue; }
        if (cell.category !== null && cell.category !== undefined) { if (!categories.includes(cell.category)) { categories.push(cell.category); } }
        else if (cell.bucket_index !== null && cell.bucket_index !== undefined) { sawBucket = true; }
    }
    if (categories.length) { return { mode: "category", labels: categories.map(String), keys: categories }; }
    if (sawBucket) {
        const list = (Array.isArray(buckets) ? buckets.slice() : []).sort((a, b) => (Number(a && a.index) || 0) - (Number(b && b.index) || 0));
        return { mode: "bucket", labels: list.map((bucket) => String(bucket.label)), keys: list.map((bucket) => Number(bucket.index)) };
    }
    return { mode: "category", labels: [], keys: [] };
}

function scalarFallback(aggregate) {
    if (!aggregate || typeof aggregate !== "object") { return null; }
    const keys = Object.keys(aggregate);
    const chosen = PREFERRED.find((key) => typeof aggregate[key] === "number" && Number.isFinite(aggregate[key]))
        || keys.find((key) => typeof aggregate[key] === "number" && Number.isFinite(aggregate[key]));
    if (!chosen) { return null; }
    return { label: chosen, value: aggregate[chosen] };
}

function buildA11y(container, groupNames, labels, series, units) {
    const table = el("table", "widget-a11y widget-alt-table");
    table.appendChild(el("caption", "widget-caption", groupNames.join(", ")));
    const head = el("tr", "widget-a11y-head");
    head.appendChild(el("th", "widget-a11y-corner", ""));
    for (const label of labels) { head.appendChild(el("th", "widget-a11y-col", label)); }
    table.appendChild(head);
    for (let gi = 0; gi < groupNames.length; gi += 1) {
        const row = el("tr", "widget-a11y-row");
        row.appendChild(el("td", "widget-a11y-rowhead", groupNames[gi]));
        for (const label of labels) {
            const value = series[gi].data[labels.indexOf(label)];
            row.appendChild(el("td", "widget-a11y-cell", value === null || value === undefined ? "—" : formatValue(value, units[groupNames[gi]])));
        }
        table.appendChild(row);
    }
    container.appendChild(table);
}

export function render(container, payload, options) {
    clearContainer(container);
    let disposed = false;
    const instance = { type: "bar", container, disposed: false, resize() {}, dispose() {} };
    if (payload && payload.error) {
        container.appendChild(el("p", "widget-error", String(payload.error)));
        return instance;
    }
    const opts = options || {};
    const aggregates = (payload && payload.aggregates) || {};
    const units = (payload && payload.units) || {};
    const rawSeries = payload && Array.isArray(payload.series) ? payload.series : null;
    let groupNames = [];
    let labels = [];
    let series = [];
    if (rawSeries) {
        const { groups, byGroup } = groupCells(rawSeries);
        const spine = spineFor(rawSeries, payload && payload.buckets);
        groupNames = groups;
        labels = spine.labels;
        series = groups.map((name) => {
            const store = byGroup.get(name);
            const data = spine.keys.map((key) => {
                const value = spine.mode === "category" ? store.cats.get(key) : store.buckets.get(key);
                return value === null || value === undefined ? null : value;
            });
            return { name, data, unit: store.unit };
        });
    }
    let chartUnit = null;
    if (!series.length) {
        const scalar = scalarFallback(aggregates);
        if (scalar) {
            groupNames = [scalar.label];
            labels = [scalar.label];
            series = [{ name: scalar.label, data: [scalar.value], unit: units[scalar.label] }];
            chartUnit = units[scalar.label] || null;
        }
    }
    if (!series.length || (payload && payload.empty === true) || labels.length === 0) {
        container.appendChild(el("p", "widget-empty", "No matching records in this window."));
        return instance;
    }
    if (!chartUnit) {
        for (const entry of series) { const candidate = units[entry.name] || entry.unit; if (candidate) { chartUnit = candidate; break; } }
    }
    const benchmarks = Array.isArray(opts.benchmarks) ? opts.benchmarks : [];
    let warned = false;
    for (const benchmark of benchmarks) {
        if (!benchmark || typeof benchmark.value !== "number" || !Number.isFinite(benchmark.value)) { continue; }
        if (!chartUnit || !matchUnit(chartUnit, benchmark.unit)) {
            if (!warned) { warned = true; globalThis.console.warn("widget-bar: skipping benchmark with unit " + String(benchmark && benchmark.unit)); }
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
    container.className = "widget widget-bar widget-chart";
    const box = el("div", "widget-chart-box widget-chart");
    container.appendChild(box);
    const built = buildChart(box, () => disposed);
    const chart = built.chart;
    chart.setOption({
        animation: false,
        color: groupNames.map((name) => groupColor(name)),
        legend: { data: groupNames },
        xAxis: { type: "category", data: labels, boundaryGap: true },
        yAxis: { type: "value", scale: true },
        series: series.map((entry) => {
            const config = { name: entry.name, type: "bar", data: entry.data, barMaxWidth: 48, itemStyle: { color: groupColor(entry.name) } };
            if (entry.markLine) { config.markLine = entry.markLine; }
            return config;
        }),
    }, true);
    const unitsUsed = {};
    for (const entry of series) { unitsUsed[entry.name] = units[entry.name] || entry.unit; }
    buildA11y(container, groupNames, labels, series, unitsUsed);
    container.setAttribute("role", "img");
    container.setAttribute("aria-label", "Bar chart, " + groupNames.length + " groups: " + groupNames.join(", ") + ". " + (chartUnit || ""));
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
