export class RendererError extends Error {
    constructor(message) {
        super(message);
        this.name = "RendererError";
    }
}

const renderers = new Map();
const liveByContainer = new Map();

export function register(type, rendererModule) {
    renderers.set(String(type), rendererModule);
}

export function get(type) {
    const mod = renderers.get(String(type));
    if (!mod) { throw new RendererError("Unknown widget type: " + String(type)); }
    return mod;
}

export function el(tag, cls, text) {
    const node = globalThis.document.createElement(tag);
    node.className = cls || "";
    if (text !== null && text !== undefined) { node.textContent = String(text); }
    return node;
}

export function clearContainer(container) {
    while (container.firstChild) { container.removeChild(container.firstChild); }
}

export function observeLifecycle(instance, container, onResize) {
    const handles = [];
    if (typeof globalThis.ResizeObserver !== "undefined") {
        const resizeObserver = new globalThis.ResizeObserver(onResize);
        resizeObserver.observe(container);
        handles.push(resizeObserver);
    }
    if (typeof globalThis.MutationObserver !== "undefined" && globalThis.document && globalThis.document.documentElement) {
        const mutationObserver = new globalThis.MutationObserver(onResize);
        mutationObserver.observe(globalThis.document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
        handles.push(mutationObserver);
    }
    return function disconnectObservers() {
        while (handles.length) { const handle = handles.pop(); if (handle) { handle.disconnect(); } }
    };
}

export function buildChart(container, getDisposed) {
    if (typeof globalThis.window === "undefined" || !globalThis.window.echarts) {
        throw new RendererError("echarts is not available on the page host");
    }
    const chart = globalThis.window.echarts.init(container);
    let chartDisposed = false;
    return {
        chart,
        resize() { if (!getDisposed()) { chart.resize(); } },
        dispose() { if (!chartDisposed) { chartDisposed = true; chart.dispose(); } },
    };
}

function findLive(container) {
    for (const [node, entry] of liveByContainer) {
        if (node === container) { return entry; }
    }
    return null;
}

function disposeEntry(entry) {
    if (entry.instance && typeof entry.instance.dispose === "function" && !entry.instance.disposed) {
        entry.instance.dispose();
    }
}

export function disposeInstance(instance) {
    if (!instance) { return; }
    const entry = instance.container ? findLive(instance.container) : null;
    if (entry) { liveByContainer.delete(entry.node); }
    disposeEntry({ instance, node: instance.container });
}

export function disposeAll() {
    for (const [, entry] of liveByContainer) { disposeEntry(entry); }
    liveByContainer.clear();
}

export function render(type, container, payload, options) {
    const mod = get(type);
    const previous = findLive(container);
    if (previous) {
        liveByContainer.delete(previous.node);
        disposeEntry(previous);
    }
    const instance = mod.render(container, payload, options || {});
    if (instance && container) { liveByContainer.set(container, { instance, node: container }); }
    return instance;
}

const api = { register, get, render, disposeInstance, disposeAll, RendererError };

if (typeof globalThis.window !== "undefined") {
    globalThis.window.__rv2widgets = globalThis.window.__rv2widgets || {};
    globalThis.window.__rv2widgets.registry = api;
}

export { api as registry };
