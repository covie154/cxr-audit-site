import { formatValue, formatDateText } from "./format.mjs";
import { el, clearContainer, observeLifecycle } from "./registry.mjs";

function cellText(value, unit) {
    if (value === null || value === undefined) { return "—"; }
    if (typeof value === "number") { return formatValue(value, unit); }
    return formatDateText(value);
}

export function render(container, payload, options) {
    clearContainer(container);
    let disposed = false;
    const instance = { type: "table", container, disposed: false, resize() {}, dispose() {} };
    if (payload && payload.error) {
        container.appendChild(el("p", "widget-error", String(payload.error)));
        return instance;
    }
    const rows = payload && Array.isArray(payload.rows) ? payload.rows : [];
    if ((payload && payload.empty === true) || rows.length === 0) {
        container.appendChild(el("p", "widget-empty", "No matching records in this window."));
        return instance;
    }
    const units = (payload && payload.units) || {};
    const columns = [];
    for (const row of rows) {
        if (!row || typeof row !== "object") { continue; }
        for (const key of Object.keys(row)) { if (!columns.includes(key)) { columns.push(key); } }
    }
    const captionText = (payload && (payload.caption || payload.title)) || columns.join(", ");
    const table = el("table", "widget-table widget-alt-table");
    const caption = el("caption", "widget-caption", captionText);
    if (options && options.hideCaption) { caption.className += " widget-a11y"; }
    table.appendChild(caption);
    const head = el("thead", "widget-thead");
    const headRow = el("tr", "widget-head-row");
    for (const key of columns) { headRow.appendChild(el("th", "widget-th", key.replaceAll("_", " "))); }
    head.appendChild(headRow);
    table.appendChild(head);
    const body = el("tbody", "widget-tbody");
    for (const [index, row] of rows.entries()) {
        const tr = el("tr", payload.overall_row && index === rows.length - 1 ? "widget-tr overall-row" : "widget-tr");
        for (const key of columns) {
            const value = row && typeof row === "object" ? row[key] : null;
            tr.appendChild(el("td", "widget-td", cellText(value, units[key])));
        }
        body.appendChild(tr);
    }
    table.appendChild(body);
    container.appendChild(table);
    container.setAttribute("role", "region");
    container.setAttribute("aria-label", captionText);
    const disconnect = observeLifecycle(instance, container, () => { if (!disposed) { instance.resize(); } });
    instance.dispose = () => {
        if (disposed) { return; }
        disposed = true;
        instance.disposed = true;
        disconnect();
        clearContainer(container);
    };
    return instance;
}
