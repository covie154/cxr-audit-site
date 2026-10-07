import { formatValue } from "./format.mjs";
import { el, clearContainer, observeLifecycle } from "./registry.mjs";

function entries(aggregate) {
    if (!aggregate || typeof aggregate !== "object") { return []; }
    return Object.entries(aggregate);
}

function ciSpan(ciEntry, name, units) {
    if (!ciEntry || ciEntry.available !== true) { return null; }
    if (typeof ciEntry.lower !== "number" || typeof ciEntry.upper !== "number") { return null; }
    if (!Number.isFinite(ciEntry.lower) || !Number.isFinite(ciEntry.upper)) { return null; }
    const confidence = typeof ciEntry.confidence_level === "number" ? Math.round(ciEntry.confidence_level * 100) : 95;
    const unit = units && units[name];
    return el("span", "widget-ci", "(" + confidence + "% CI " + formatValue(ciEntry.lower, unit) + " to " + formatValue(ciEntry.upper, unit) + ")");
}

export function render(container, payload, options) {
    clearContainer(container);
    let disposed = false;
    const instance = { type: "value", container, disposed: false, resize() {}, dispose() {} };
    if (payload && payload.error) {
        container.appendChild(el("p", "widget-error", String(payload.error)));
        return instance;
    }
    if (payload && payload.empty === true) {
        container.appendChild(el("p", "widget-empty", "No matching records in this window."));
        return instance;
    }
    if (options && options.primaryOnly) {
        const key = options.measurement === "record_count" ? "n" : options.measurement;
        if (payload && Array.isArray(payload.grouped_values)) {
            const units = payload.units || {};
            for (const group of payload.grouped_values) {
                const row = el("div", "widget-group-value");
                row.appendChild(el("span", "widget-value-name", group.name));
                row.appendChild(el("p", "widget-primary-value", formatValue((group.aggregates || {})[key], units[key])));
                const span = ciSpan((group.ci || {})[key], key, units);
                if (span) { row.appendChild(span); }
                container.appendChild(row);
            }
            return instance;
        }
        const value = ((payload && payload.aggregates) || {})[key];
        const number = el("p", "widget-primary-value widget-single-value", formatValue(value, ((payload && payload.units) || {})[key]));
        container.appendChild(number);
        instance.resize = () => {
            if (disposed || !container.clientWidth || !container.clientHeight) { return; }
            let low = 0;
            let high = container.clientHeight;
            // Measure the actual text so long counts and durations also fit.
            while (high - low > 0.5) {
                const size = (low + high) / 2;
                number.style.fontSize = size + "px";
                if (number.scrollWidth <= container.clientWidth * 0.9 && number.getBoundingClientRect().height <= container.clientHeight * 0.8) {
                    low = size;
                } else {
                    high = size;
                }
            }
            number.style.fontSize = low + "px";
        };
        const disconnect = observeLifecycle(instance, container, instance.resize);
        instance.dispose = () => {
            if (disposed) { return; }
            disposed = true;
            instance.disposed = true;
            disconnect();
            clearContainer(container);
        };
        instance.resize();
        return instance;
    }
    const list = entries(payload && payload.aggregates);
    if ((payload && payload.empty === true) || list.length === 0) {
        container.appendChild(el("p", "widget-empty", "No matching records in this window."));
        return instance;
    }
    const units = (payload && payload.units) || {};
    const ci = (payload && payload.ci) || {};
    const dl = el("dl", "widget-values");
    const summary = [];
    for (const [name, value] of list) {
        const formatted = typeof value === "number" ? formatValue(value, units[name])
            : (typeof value === "string" ? value : "—");
        const row = el("div", "widget-value");
        row.appendChild(el("dt", "widget-value-name", name));
        const dd = el("dd", "widget-value-num", formatted);
        const span = ciSpan(ci[name], name, units);
        if (span) { dd.appendChild(span); }
        row.appendChild(dd);
        dl.appendChild(row);
        summary.push(name + " " + formatted);
    }
    dl.setAttribute("role", "group");
    dl.setAttribute("aria-label", (options && options.label) || (list.map((pair) => pair[0]).join(", ")) + " measures");
    container.appendChild(dl);
    container.appendChild(el("p", "widget-a11y", summary.join("; ")));
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
