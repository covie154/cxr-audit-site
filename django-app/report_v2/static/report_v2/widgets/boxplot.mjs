/*
 * Box plot widget renderer: one box series (whiskers are the observed extremes within 1.5*IQR, never
 * the fences) plus a scatter outlier series keyed by group index. Optional benchmark markLine attaches
 * to the boxes series only when the candidate unit matches the plot unit. No DOM beyond el/clearContainer.
 */
import { matchUnit, formatValue, groupColor } from "./format.mjs";
import { el, clearContainer, chartLifecycle, buildChart } from "./registry.mjs";

function finiteNumber(value) {
    return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function collectGroups(payload) {
    if (payload && Array.isArray(payload.summaries)) {
        return payload.summaries.map((entry) => ({
            name: entry && entry.name !== null && entry.name !== undefined ? String(entry.name) : "",
            unit: entry ? entry.unit : null,
            summary: (entry && entry.summary) || {},
        }));
    }
    if (payload && payload.summary) {
        return [{ name: String(payload.name || "values"), unit: payload.unit, summary: payload.summary }];
    }
    return [];
}

function isDrawable(summary) {
    const s = summary || {};
    return finiteNumber(s.q1) !== null && finiteNumber(s.median) !== null && finiteNumber(s.q3) !== null
        && finiteNumber(s.lower_whisker) !== null && finiteNumber(s.upper_whisker) !== null;
}

const HEADERS = ["n", "group", "min", "lower whisker", "Q1", "median", "Q3", "upper whisker", "max", "outliers"];

export function render(container, payload, options) {
    clearContainer(container);
    const instance = { type: "boxplot", container, disposed: false, resize() {}, dispose() {} };
    if (payload && payload.error) {
        container.appendChild(el("p", "widget-error", String(payload.error)));
        return instance;
    }
    const opts = options || {};
    const groups = collectGroups(payload).filter((group) => isDrawable(group.summary));
    if (!groups.length) {
        container.appendChild(el("p", "widget-empty", "No matching records in this window."));
        return instance;
    }
    const names = groups.map((group) => group.name);
    const units = (payload && payload.units) || {};
    const plotUnit = groups[0].unit || units.value || null;
    container.className = "widget widget-boxplot widget-chart";
    const box = el("div", "widget-chart-box widget-chart");
    container.appendChild(box);
    const built = buildChart(box, () => instance.disposed);
    instance.chart = built.chart; // exposed for client-side PNG capture (email export)
    const outlierData = [];
    for (let gi = 0; gi < groups.length; gi += 1) {
        const outliers = (groups[gi].summary && groups[gi].summary.outliers) || [];
        if (Array.isArray(outliers)) {
            for (const raw of outliers) {
                const num = finiteNumber(raw);
                if (num !== null) { outlierData.push([num, gi]); }
            }
        }
    }
    const series = [
        {
            name: "boxes",
            type: "boxplot",
            layout: "horizontal",
            itemStyle: { color: groupColor("boxes") },
            data: groups.map((group) => {
                const s = group.summary;
                return [s.lower_whisker, s.q1, s.median, s.q3, s.upper_whisker];
            }),
        },
        {
            name: "outliers",
            type: "scatter",
            symbolSize: 8,
            itemStyle: { color: groupColor("outliers") },
            data: outlierData,
        },
    ];
    const benchmarks = Array.isArray(opts.benchmarks) ? opts.benchmarks : [];
    let warned = false;
    for (const benchmark of benchmarks) {
        const value = benchmark ? finiteNumber(benchmark.value) : null;
        if (value === null) { continue; }
        if (!matchUnit(plotUnit, benchmark.unit)) {
            if (!warned) { warned = true; globalThis.console.warn("widget-boxplot: skipping benchmark with unit " + String(benchmark && benchmark.unit)); }
            continue;
        }
        series[0].markLine = {
            silent: true,
            symbol: "none",
            lineStyle: { type: "dashed", color: "#7a7a7a" },
            label: { formatter: String(benchmark.label === null || benchmark.label === undefined ? "" : benchmark.label) + " " + formatValue(value, plotUnit) },
            data: [{ xAxis: value }],
        };
        break;
    }
    const option = {
        animation: false,
        legend: { type: "scroll", bottom: 0, data: names },
        grid: { top: 20, bottom: 48, left: 16, right: 16, containLabel: true },
        xAxis: { type: "value", scale: true },
        yAxis: { type: "category", data: names, boundaryGap: true },
        series: series,
    };
    if (plotUnit === "seconds") { option.xAxis.axisLabel = { formatter: (v) => formatValue(v, "seconds") }; }
    built.chart.setOption(option, true);
    const table = el("table", "widget-a11y widget-alt-table");
    table.appendChild(el("caption", "widget-caption", "Box plot summaries (whiskers are the most extreme observations within 1.5*IQR of the quartiles)"));
    const head = el("tr", "widget-a11y-head");
    head.appendChild(el("th", "widget-a11y-corner", ""));
    for (const header of HEADERS) { head.appendChild(el("th", "widget-a11y-col", header)); }
    table.appendChild(head);
    for (const group of groups) {
        const s = group.summary;
        const unit = group.unit;
        const outliers = Array.isArray(s.outliers) ? s.outliers.map(finiteNumber).filter((value) => value !== null) : [];
        const outlierText = outliers.length ? outliers.map((value) => formatValue(value, unit)).join(", ") : "none";
        const cells = [
            formatValue(s.n, "count"),
            group.name,
            formatValue(s.min, unit),
            formatValue(s.lower_whisker, unit),
            formatValue(s.q1, unit),
            formatValue(s.median, unit),
            formatValue(s.q3, unit),
            formatValue(s.upper_whisker, unit),
            formatValue(s.max, unit),
            outlierText,
        ];
        const row = el("tr", "widget-a11y-row");
        row.appendChild(el("th", "widget-a11y-rowhead", group.name));
        for (const text of cells) { row.appendChild(el("td", "widget-a11y-cell", text)); }
        table.appendChild(row);
    }
    container.appendChild(table);
    container.setAttribute("role", "img");
    container.setAttribute("aria-label", "Box plot, " + groups.length + " groups, whiskers are observed values within 1.5*IQR fences, outliers plotted");
    return chartLifecycle(instance, built);
}
