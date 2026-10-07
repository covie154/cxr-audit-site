/*
 * Confusion matrix widget renderer: a shaded square DOM table is the display (export/PDF safe).
 * Consumes the server matrix dict verbatim: declared-order classes on both axes, ground-truth rows,
 * prediction columns. Count or percent mode is driven purely by options.display. Idempotent dispose
 * (clearContainer only) since there is no chart handle or observers to tear down.
 */
import { formatValue } from "./format.mjs";
import { el, clearContainer } from "./registry.mjs";

function finiteNumber(value) {
    return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function cellAt(cells, i, j) {
    const row = cells ? cells[i] : null;
    if (!Array.isArray(row)) { return 0; }
    const value = row[j];
    return typeof value === "number" && Number.isFinite(value) ? value : 0;
}

export function render(container, payload, options) {
    clearContainer(container);
    let disposed = false;
    const instance = { type: "confusion_matrix", container, disposed: false, resize() {}, dispose() {} };
    if (payload && payload.error) {
        container.appendChild(el("p", "widget-error", String(payload.error)));
        return instance;
    }
    const opts = options || {};
    const matrix = payload || {};
    const classes = Array.isArray(matrix.classes) ? matrix.classes : null;
    if (!classes || !classes.length) {
        container.appendChild(el("p", "widget-empty", "No matching records in this window."));
        return instance;
    }
    const percent = opts.display === "percent";
    const cells = matrix.cells || [];
    const maximum = Math.max(0, ...classes.flatMap((_, i) => classes.map((_, j) => cellAt(cells, i, j))));
    const classLabel = (value) => classes.length === 2 && classes.map(String).join(",") === "0,1" ? (String(value) === "0" ? "Negative" : "Positive") : String(value);
    const rowTotals = Array.isArray(matrix.row_totals) ? matrix.row_totals : [];
    container.className = "widget widget-confusion_matrix widget-table";
    const table = el("table", "widget-confusion widget-a11y widget-alt-table");
    table.setAttribute("style", "--matrix-classes: " + classes.length);
    table.appendChild(el("caption", "widget-caption", "Ground truth rows, prediction columns"));
    const head = el("tr", "widget-a11y-head");
    head.appendChild(el("th", "widget-a11y-corner", ""));
    for (let j = 0; j < classes.length; j += 1) {
        head.appendChild(el("th", "widget-a11y-col", classLabel(classes[j])));
    }
    table.appendChild(head);
    for (let i = 0; i < classes.length; i += 1) {
        const row = el("tr", "widget-a11y-row");
        row.appendChild(el("th", "widget-a11y-rowhead", classLabel(classes[i])));
        const rowTotal = finiteNumber(rowTotals[i]);
        for (let j = 0; j < classes.length; j += 1) {
            const cell = cellAt(cells, i, j);
            let text = String(cell);
            const td = el("td", "widget-a11y-cell", text);
            const intensity = maximum > 0 ? Math.max(0, cell / maximum) : 0;
            const rgb = [231, 245, 236].map((start, index) => Math.round(start + ([0, 100, 65][index] - start) * intensity));
            td.setAttribute("style", "background-color: rgb(" + rgb.join(",") + "); color: " + (intensity > 0.55 ? "#fff" : "#123c2d"));
            td.setAttribute("data-row-class", String(classes[i]));
            td.setAttribute("data-col-class", String(classes[j]));
            if (percent) {
                if (rowTotal !== null && rowTotal > 0) {
                    td.textContent = formatValue(cell / rowTotal, "rate[0,1]");
                    td.setAttribute("data-normalised", "value");
                } else {
                    td.textContent = "unavailable";
                    td.setAttribute("data-normalised", "unavailable");
                }
            }
            row.appendChild(td);
        }
        table.appendChild(row);
    }
    const plot = el("div", "widget-confusion-plot");
    plot.appendChild(el("span", "widget-confusion-axis", "Ground truth"));
    plot.appendChild(el("div", "widget-confusion-prediction", "Prediction"));
    plot.appendChild(table);
    container.appendChild(plot);
    const accuracy = matrix.accuracy;
    const value = accuracy ? finiteNumber(accuracy.value) : null;
    container.appendChild(el("p", "widget-summary-line", value === null ? "Accuracy: unavailable" : "Accuracy: " + formatValue(value, "rate[0,1]")));
    container.setAttribute("role", "img");
    container.setAttribute("aria-label", classes.length + " by " + classes.length + " classes, rows ground truth, columns prediction");
    instance.dispose = () => {
        if (disposed) { return; }
        disposed = true;
        instance.disposed = true;
        clearContainer(container);
    };
    return instance;
}
