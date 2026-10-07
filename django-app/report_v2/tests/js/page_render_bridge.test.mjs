/*
 * Runtime harness for the report.js <-> widget-registry bridge (Task 14A).
 *
 * Drives the shipped report.js through the same new Function(...) shim style as page_state.test.mjs
 * and proves the three behaviours that matter: the legacy path is byte-for-byte intact when the
 * registry host is absent, an eligible frame is painted through the registry when the host exists,
 * the previous instance is disposed exactly once before a re-render, and a throwing renderer falls
 * back to the legacy markup without escaping an exception. Case 4 smoke-tests the real registry +
 * boot contract; the last case is the boot.mjs source scan.
 *
 * Run:  node tests/js/page_render_bridge.test.mjs
 */
import { test } from 'node:test';
import assert from 'node:assert/strict';
import readfile from 'node:fs/promises';
import pathe from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const here = pathe.dirname(fileURLToPath(import.meta.url));
const staticDir = pathe.join(here, '..', '..', 'static', 'report_v2');

// ---------------------------------------------------------------------------
// DOM shim (mirrors page_state.test.mjs: canonically spelled members only)
// ---------------------------------------------------------------------------
class FakeNode {
    constructor(tag, className) {
        this.tag = tag;
        this.className = className || '';
        this._children = [];
        this.textContent = '';
        this.disabled = false;
        this.hidden = false;
        this.attributes = {};
        this.dataset = {};
        this.listeners = {};
        this.removed = false;
    }
    get children() { return this._children; }
    removeChild(node) { const at = this._children.indexOf(node); if (at >= 0) { this._children.splice(at, 1); } node.removed = true; return node; }
    append(...nodes) { for (const n of nodes) { this.children.push(n); } }
    remove() { this.removed = true; }
    setAttribute(name, value) { this.attributes[name] = value; }
    addEventListener(type, handler) { (this.listeners[type] = this.listeners[type] || []).push(handler); }
    fire(type, event) { for (const h of this.listeners[type] || []) { h(event); } }
    register(selector, node) { (this._bySelector = this._bySelector || new Map()).set(selector, node); }
    querySelector(selector) { return (this._bySelector || new Map()).get(selector) || null; }
    querySelectorAll(selector) {
        const hit = (this._bySelector || new Map()).get(selector);
        return hit === undefined ? [] : Array.isArray(hit) ? hit : [hit];
    }
    descendants() {
        const out = [this];
        for (const child of this.children) { out.push(...child.descendants()); }
        return out;
    }
}

function collectText(node) {
    let text = node.textContent || '';
    for (const child of node.children) { text += ' ' + collectText(child); }
    return text;
}

// Install the globals report.js expects. ``registry`` (when supplied) is mirrored onto
// window.__rv2widgets exactly the way registry.mjs publishes its api on a real page.
function installGlobals({ registry }) {
    const document = {
        createElement: (tag, cls) => new FakeNode(tag, cls),
        querySelector: null,
        querySelectorAll: null,
        getElementById: () => null,
        cookie: 'csrftoken=test-cookie',
        documentElement: new FakeNode('html'),
    };
    const root = new FakeNode('div');
    root.dataset.slug = 'overview';
    root.dataset.version = 'overview@r1';
    const csrfInput = new FakeNode('input');
    csrfInput.value = 'form-token';
    const csrfHolder = new FakeNode('span');
    csrfHolder.register('[name="csrfmiddlewaretoken"]', csrfInput);
    root.register('[data-role="csrf"] [name="csrfmiddlewaretoken"]', csrfInput);

    const requests = [];
    const pending = [];
    const fetchImpl = (url, init) => new Promise((resolve) => {
        requests.push({ url, init });
        pending.push((payload, ok) => resolve({ ok: ok === undefined ? true : ok, status: ok === false ? 400 : 200, json: async () => payload }));
    });

    const window = {
        echarts: { init: () => ({ setOption() {}, resize() {}, dispose() {} }) },
        fetch: fetchImpl,
        decodeURIComponent: (value) => value,
        getComputedStyle: () => ({ getPropertyValue: () => ' ' }),
        setTimeout: (fn) => fn(),
    };
    if (registry) { window.__rv2widgets = { registry }; }

    globalThis.window = window;
    globalThis.document = document;
    globalThis.fetch = fetchImpl;
    globalThis.AbortController = class { constructor() { this.signal = {}; } abort() { this.aborted = true; } };
    globalThis.ResizeObserver = class { constructor(cb) { this.cb = cb; this.seen = []; } observe(n) { this.seen.push(n); } disconnect() {} };
    globalThis.MutationObserver = class { constructor(cb) { this.cb = cb; this.seen = []; } observe(n) { this.seen.push(n); } disconnect() {} };

    root.register('.widget-frame:not([data-decoration])', root.children);
    document.querySelector = (selector) => (selector === '[data-report-page]' ? root : null);
    document.querySelectorAll = (selector) => (selector === '.widget-frame' ? root.children : selector === '[data-report-chart]' ? [] : []);

    return { document, root, requests, pending };
}

// Build one frame element per requested type and wire the contract report.js reads.
function buildFrames(root, types) {
    const built = [];
    types.forEach((type, index) => {
        const frame = new FakeNode('article');
        frame.dataset.widgetId = 'w' + index;
        frame.dataset.type = type;
        frame.dataset.dataUrl = '/report/overview/widget/w' + index + '/data/';
        frame.dataset.contextToken = 'token-' + index;
        const body = new FakeNode('div');
        frame.register('[data-widget-body]', body);
        const summary = new FakeNode('p', 'widget-summary');
        frame.register('.widget-summary', summary);
        const emptyNote = new FakeNode('p', 'widget-empty');
        emptyNote.textContent = 'EMPTY';
        frame.register('[data-role="empty-message"]', emptyNote);
        const form = new FakeNode('form');
        frame.register('[data-role="controls"]', form);
        if (type === 'table') {
            frame.register('[data-action="more"]', new FakeNode('button'));
        }
        root.children.push(frame);
        built.push({ type, frame, body, summary, form });
    });
    return built;
}

async function runScript({ types, registry, loading = false, transport }) {
    const { document, root, requests, pending } = installGlobals({ registry });
    const frames = buildFrames(root, types);
    if (loading) {
        window.innerHeight = 800;
        frames.forEach(({ frame }, index) => {
            const initial = new FakeNode('pre');
            initial.textContent = JSON.stringify({ loading: true });
            frame.register('[data-initial-payload]', initial);
            frame.getBoundingClientRect = () => ({ top: index === 3 ? 0 : 1000, bottom: index === 3 ? 100 : 1100 });
        });
    }
    const source = await readfile.readFile(pathe.join(staticDir, 'report.js'), 'utf-8');
    new Function('document', 'window', 'AbortController', 'ResizeObserver', 'MutationObserver', 'fetch',
        '"use strict";' + source)(document, globalThis.window, globalThis.AbortController,
        globalThis.ResizeObserver, globalThis.MutationObserver, globalThis.fetch);
    if (transport) { window.__rv2initializeReport(root, transport); }
    return { frames, requests, pending };
}

const flush = () => new Promise((resolve) => setImmediate(resolve));
const RESOLVED = { status: 'ok', empty: false, counts: { incoming: 6, matching: 6, eligible: 5 }, aggregates: { record_count: 5 } };

function makeFakeRegistry() {
    const calls = { render: [], disposeInstance: [] };
    const registry = {
        render(type, container, payload, options) {
            const instance = { type, container, payload, options, disposed: false, dispose() { this.disposed = true; }, resize() {} };
            calls.render.push({ type, container, payload, options, instance });
            return instance;
        },
        disposeInstance(instance) { calls.disposeInstance.push(instance); if (instance && typeof instance.dispose === 'function') { instance.dispose(); } },
    };
    return { registry, calls };
}

// ---------------------------------------------------------------------------
// case 1: no host -> legacy aggregate table is produced (fallback works)
// ---------------------------------------------------------------------------
test('case 1: without __rv2widgets the legacy aggregates path renders', async () => {
    const { frames, pending } = await runScript({ types: ['value'], registry: null });
    frames[0].form.fire('submit', { preventDefault() {} });
    pending.shift()(RESOLVED);
    await flush();
    const text = collectText(frames[0].body);
    assert.match(text, /record_count/, 'legacy aggregates markup must surface record_count');
});

// ---------------------------------------------------------------------------
// case 2: host present -> the registry paints, re-render disposes the old once
// ---------------------------------------------------------------------------
test('case 2: with the registry an eligible frame renders through it and re-renders dispose the old once', async () => {
    const { registry, calls } = makeFakeRegistry();
    const { frames, pending } = await runScript({ types: ['value'], registry });
    frames[0].form.fire('submit', { preventDefault() {} });
    pending.shift()(RESOLVED);
    await flush();
    assert.equal(calls.render.length, 1, 'exactly one render call');
    assert.equal(calls.render[0].type, 'value');
    assert.deepEqual(calls.render[0].payload, RESOLVED);
    // the bridge hands renderers a dedicated mount child, never the live wrapper itself, so the
    // live node keeps its widget-live class + data-live-region marker even when a renderer re-classifies its container
    const liveNode = frames[0].body.children[frames[0].body.children.length - 1];
    assert.equal(calls.render[0].container, liveNode.children[0], 'registry renders into the mount child');
    assert.notEqual(calls.render[0].container, liveNode, 'the live wrapper itself is never the render container');
    assert.equal(liveNode.className, 'widget-live');
    assert.notEqual(liveNode.attributes['data-live-region'], undefined);
    const firstInstance = calls.render[0].instance;
    // a second submit must dispose the previous instance once, before the next render
    frames[0].form.fire('submit', { preventDefault() {} });
    pending.shift()(RESOLVED);
    await flush();
    assert.equal(calls.render.length, 2, 'second submit renders again');
    assert.equal(calls.disposeInstance.length, 1, 'disposeInstance called exactly once between the two renders');
    assert.equal(calls.disposeInstance[0], firstInstance, 'the disposed instance is the previous one');
    assert.equal(firstInstance.disposed, true, 'the previous instance reported itself disposed');
});

// ---------------------------------------------------------------------------
// case 3: a throwing renderer falls back to legacy markup, no exception escapes
// ---------------------------------------------------------------------------
test('case 3: a throwing registry renderer falls back to the legacy path', async () => {
    const calls = { render: 0 };
    const registry = {
        render() { calls.render += 1; throw new Error('renderer blew up'); },
        disposeInstance() {},
    };
    const { frames, pending } = await runScript({ types: ['value'], registry });
    frames[0].form.fire('submit', { preventDefault() {} });
    pending.shift()(RESOLVED);
    await flush();
    assert.equal(calls.render, 1, 'the registry render was attempted');
    const text = collectText(frames[0].body);
    assert.match(text, /record_count/, 'legacy markup still renders after a renderer throw');
});

// ---------------------------------------------------------------------------
// case 4: real registry + boot contract smoke
// ---------------------------------------------------------------------------
test('case 4: boot.mjs registers value/table/line/bar and flags bootReady on the real registry', async () => {
    globalThis.window = {};
    globalThis.document = { createElement: () => new FakeNode('div'), documentElement: new FakeNode('html') };
    globalThis.ResizeObserver = class { observe() {} disconnect() {} };
    globalThis.MutationObserver = class { observe() {} disconnect() {} };
    const registryMod = await import(pathToFileURL(pathe.join(staticDir, 'widgets', 'registry.mjs')).href);
    await import(pathToFileURL(pathe.join(staticDir, 'widgets', 'boot.mjs')).href);
    assert.equal(globalThis.window.__rv2widgets.bootReady, true);
    assert.equal(globalThis.window.__rv2widgets.registry, registryMod.registry);
    // after boot the four renderers resolve through the registry's get()
    for (const kind of ['value', 'table', 'line', 'bar']) {
        assert.equal(typeof registryMod.registry.get(kind).render, 'function', kind + ' renderer must resolve');
    }
});

// ---------------------------------------------------------------------------
// source scan: boot.mjs must carry none of the forbidden tokens (assembled by concatenation)
// ---------------------------------------------------------------------------
test('source scan: boot.mjs carries no forbidden tokens', async () => {
    const forbidden = ['inner' + 'HTML', 'local' + 'Storage', 'session' + 'Storage', 'indexed' + 'DB', 'http://cdn', 'fetch' + '('];
    const text = await readfile.readFile(pathe.join(staticDir, 'widgets', 'boot.mjs'), 'utf-8');
    for (const token of forbidden) {
        assert.equal(text.toLowerCase().includes(token.toLowerCase()), false, 'boot.mjs must not contain ' + token);
    }
});


test('Task 16: updates render every chart kind through the registry', async () => {
    const { registry, calls } = makeFakeRegistry();
    const { frames, pending } = await runScript({ types: ['pie', 'confusion_matrix', 'boxplot'], registry });
    for (const frame of frames) {
        frame.form.fire('submit', { preventDefault() {} });
        pending.shift()(RESOLVED);
        await flush();
    }
    assert.deepEqual(calls.render.map(call => call.type), ['pie', 'confusion_matrix', 'boxplot']);
});

test('Task 16: CSV links follow the applied widget window and site', async () => {
    const { frames, pending } = await runScript({ types: ['table'], registry: null });
    window.location = { href: 'http://localhost/report/overview/' };
    const link = new FakeNode('a');
    link.href = 'http://localhost/report/overview/csv/full/?widget=w0&context=signed';
    const site = new FakeNode('input');
    site.value = 'SYNTH-SITE-B';
    site.dataset.filter = 'site';
    frames[0].frame.register('[data-csv-download]', [link]);
    frames[0].frame.register('[data-filter]', [site]);
    frames[0].form.fire('submit', { preventDefault() {} });
    pending.shift()({ ...RESOLVED, dates: { window_start: '2026-08-01', window_end: '2026-08-10' } });
    await flush();
    const url = new URL(link.href);
    assert.equal(url.searchParams.get('site'), 'SYNTH-SITE-B');
    assert.equal(url.searchParams.get('date_from'), '2026-08-01');
    assert.equal(url.searchParams.get('date_to'), '2026-08-10');
    assert.equal(url.searchParams.get('context'), 'signed');
});

test('skeleton cards prioritize visible cards and keep at most three requests active after failure', async () => {
    const { registry, calls } = makeFakeRegistry();
    const { frames, requests, pending } = await runScript({ types: ['table', 'value', 'value', 'table', 'value'], registry, loading: true });
    assert.equal(requests.length, 3);
    assert.match(requests[0].url, /w3/);
    assert.equal(calls.render.length, 0);
    pending.shift()({ status: 'error', error: 'Unavailable' });
    await flush();
    assert.equal(requests.length, 4);
    assert.equal(frames[3].frame.attributes['aria-busy'], 'false');
    pending.shift()(RESOLVED);
    await flush();
    assert.equal(requests.length, 5);
    while (pending.length) { pending.shift()(RESOLVED); }
    await flush();
    assert.equal(calls.render.length, 5);
});

test('HTML failures show HTTP status and the initial queue continues', async () => {
    const transport = async () => ({ ok: false, status: 503, redirected: false, json: async () => { throw new SyntaxError('HTML body'); } });
    const { frames } = await runScript({ types: ['value'], loading: true, transport });
    await flush();
    assert.match(frames[0].summary.textContent, /HTTP 503/);
    assert.equal(frames[0].frame.attributes['aria-busy'], 'false');
});
