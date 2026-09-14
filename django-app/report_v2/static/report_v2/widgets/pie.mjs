/*
 * Pie / donut widget renderer: mutually exclusive category counts drawn as a share chart, with a
 * full accessible alternative table. Shares the chart lifecycle contract with bar/line; ignores
 * benchmarks entirely (a share chart has no meaningful benchmark line). No DOM beyond el/clearContainer.
 */
import { formatValue, groupColor } from "./format.mjs";
import { el, clearContainer, observeLifecycle, buildChart } from "./registry.mjs";

function finiteNumber(value) {
    return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function collectCategories(payload) {
    if (payload && Array.isArray(payload.categories)) {
        return payload.categories
            .filter((entry) => entry && entry.label !== null && entry.label !== undefined)
            .map((entry) => ({ label: entry.label, count: entry.count }));
    }
    const aggregates = (payload && payload.aggregates) || {};
    const out = [];
    for (const key of Object.keys(aggregates)) {
        const value = aggregates[key];
        if (typeof value === "number" && Number.isFinite(value)) { out.push({ label: key, count: value }); }
    }
    return out;
}

export function render(container, payload, options) {
    clearContainer(container);
    let disposed = false;
    const instance = { type: "pie", container, disposed: false, resize() {}, dispose() {} };
    if (payload && payload.error) {
        container.appendChild(el("p", "widget-error", String(payload.error)));
        return instance;
    }
    const opts = options || {};
    const categories = collectCategories(payload);
    let total = 0;
    for (const entry of categories) {
        const value = finiteNumber(entry.count);
        total += value === null ? 0 : value;
    }
    if (!categories.length || total <= 0) {
        container.appendChild(el("p", "widget-empty", "No matching records in this window."));
        return instance;
    }
    const labels = categories.map((entry) => String(entry.label));
    const radius = opts.donut ? ["45%", "70%"] : "70%";
    container.className = "widget widget-pie widget-chart";
    container.setAttribute("data-donut", opts.donut ? "true" : "false");
    const box = el("div", "widget-chart-box widget-chart");
    container.appendChild(box);
    const built = buildChart(box, () => disposed);
    built.chart.setOption({
        animation: false,
        color: categories.map((entry) => groupColor(String(entry.label))),
        legend: { data: labels },
        series: [{
            type: "pie",
            name: "share",
            radius: radius,
            avoidLabelOverlap: true,
            data: categories.map((entry) => ({ name: String(entry.label), value: finiteNumber(entry.count) })),
            label: { formatter: "{b}: {c} ({d}%)" },
        }],
    }, true);
    const table = el("table", "widget-a11y widget-alt-table");
    table.appendChild(el("caption", "widget-caption", "Category counts and shares"));
    const head = el("tr", "widget-a11y-head");
    head.appendChild(el("th", "widget-a11y-corner", ""));
    head.appendChild(el("th", "widget-a11y-col", "category"));
    head.appendChild(el("th", "widget-a11y-col", "count"));
    head.appendChild(el("th", "widget-a11y-col", "share"));
    table.appendChild(head);
    for (const entry of categories) {
        const value = finiteNumber(entry.count);
        const row = el("tr", "widget-a11y-row");
        row.appendChild(el("td", "widget-a11y-cell", String(entry.label)));
        row.appendChild(el("td", "widget-a11y-cell", value === null ? "—" : String(value)));
        row.appendChild(el("td", "widget-a11y-cell", total > 0 ? formatValue((value === null ? 0 : value) / total, "rate[0,1]") : "unavailable"));
        table.appendChild(row);
    }
    container.appendChild(table);
    container.setAttribute("role", "img");
    container.setAttribute("aria-label", "Pie chart, " + categories.length + " categories: " + labels.join(", "));
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
