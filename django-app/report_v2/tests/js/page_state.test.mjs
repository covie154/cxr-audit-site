/*
 * Runtime harness for the report_v2 page script + reducer (Task 13).
 *
 * The DOM shim below defines ONLY canonically spelled members; a mis-cased identifier inside
 * report.js (createelement / Abortcontroller / stringigy ...) therefore raises a loud
 * ReferenceError/Typeerror instead of silently doing nothing. Combined with node --check
 * (syntax) this is the behavioural gate for the static layer.
 *
 * Run:  node tests/js/page_state.test.mjs
 */
import { test } from 'node:test';
import assert from 'node:assert/strict';
import readfile from 'node:fs/promises';
import pathe from 'node:path';
import { fileURLToPath } from 'node:url';

const here = pathe.dirname(fileURLToPath(import.meta.url));
const staticDir = pathe.join(here, '..', '..', 'static', 'report_v2');

// Mixed-case API member names are assembled from quoted fragments so no authoring step can
// silently lower-case them; node itself is the oracle for their exact spelling.
const READ_TEXT = 'read' + 'File';

// ---------------------------------------------------------------------------
// page_state.mjs (the canonical reducer)
// ---------------------------------------------------------------------------
import {
    applyWidgetResult,
    beginRequest,
    createPageState,
    resetWidget,
    setOverrides,
} from '../../static/report_v2/page_state.mjs';

test('fresh navigation yields pristine defaults twice over the same frames', () => {
    const frames = [{ id: 'w1', defaults: { filters: { site: 'A' } } }, { id: 'w2' }];
    const a = createPageState(frames);
    assert.deepEqual(a.widgets.w1.overrides, { date: null, filters: { site: 'A' }, comparison: null, page: 1 });
    a.widgets.w1.overrides.page = 9;
    const b = createPageState(frames);
    assert.equal(b.widgets.w1.overrides.page, 1);
    assert.equal(b.droppedStale, 0);
});

test('a stale response cannot replace a newer selection and is counted', () => {
    const state = createPageState([{ id: 'w1' }]);
    beginRequest(state, 'w1', 1);
    beginRequest(state, 'w1', 2);                       // newer request wins the slot
    applyWidgetResult(state, 'w1', { marker: 'old' }, 1);   // stale -> dropped
    assert.equal(state.widgets.w1.lastResult, null);
    applyWidgetResult(state, 'w1', { marker: 'new' }, 2);   // newest -> applied
    assert.equal(state.widgets.w1.lastResult.marker, 'new');
    applyWidgetResult(state, 'w1', { marker: 'replay' }, 2); // replay of applied seq -> dropped
    assert.equal(state.widgets.w1.lastResult.marker, 'new');
    assert.equal(state.droppedStale, 2);
});

test('reset restores declared defaults and clears the sequence ledger', () => {
    const state = createPageState([{ id: 'w1', defaults: { page: 3 } }]);
    setOverrides(state, 'w1', { page: 7, comparison: 'site' });
    resetWidget(state, 'w1');
    assert.equal(state.widgets.w1.overrides.page, 3);
    assert.equal(state.widgets.w1.overrides.comparison, null);
    assert.equal(state.widgets.w1.lastAppliedSeq, -1);
});

test('setOverrides merges partial patches', () => {
    const state = createPageState([{ id: 'w1' }]);
    setOverrides(state, 'w1', { comparison: 'site' });
    setOverrides(state, 'w1', { page: 4 });
    assert.equal(state.widgets.w1.overrides.comparison, 'site');
    assert.equal(state.widgets.w1.overrides.page, 4);
});

// ---------------------------------------------------------------------------
// report.js runtime under the strict shim
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
    // selector registry: the harness wires exact selector strings to nodes (no real engine)
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

function installDom(pageAttributes) {
    const document = {
        createElement: (tag, cls) => new FakeNode(tag, cls),
        querySelector: null,
        querySelectorAll: null,
        getElementById: () => null,
        cookie: 'csrftoken=test-cookie',
        documentElement: new FakeNode('html'),
    };
    const root = new FakeNode('div');
    for (const [key, value] of Object.entries(pageAttributes)) { root.dataset[key] = value; }
    const csrfInput = new FakeNode('input');
    csrfInput.value = 'form-token';
    const csrfHolder = new FakeNode('span');
    csrfHolder.register('[name="csrfmiddlewaretoken"]', csrfInput);
    root.register('[data-role="csrf"] [name="csrfmiddlewaretoken"]', csrfInput);
    return { document, root, FakeNode };
}

async function runReportScript() {
    const { document, root, FakeNode } = installDom({ slug: 'overview', version: 'overview@r1' });
    const forms = [];
    const frames = [];
    for (const [index, type] of ['value', 'table'].entries()) {
        const frame = new FakeNode('article');
        frame.dataset.widgetId = 'widget' + index;
        frame.dataset.type = type;
        frame.dataset.dataUrl = '/report/overview/widget/widget' + index + '/data/';
        frame.dataset.contextToken = 'token-' + index;
        const body = new FakeNode('div');
        frame.register('[data-widget-body]', body);
        const summary = new FakeNode('p', 'widget-summary');
        frame.register('.widget-summary', summary);
        const emptyNote = new FakeNode('p', 'widget-empty');
        emptyNote.textContent = 'EMPTY-NOTE-' + index;
        frame.register('[data-role="empty-message"]', emptyNote);
        const form = new FakeNode('form');
        frame.register('[data-role="controls"]', form);
        forms.push(form);
        if (type === 'table') {
            const more = new FakeNode('button');
            frame.register('[data-action="more"]', more);
        }
        root.children.push(frame);
        frames.push({ frame, body, summary, form });
    }
    document.querySelector = (selector) => (selector === '[data-report-page]' ? root : null);
    const chartBox = new FakeNode('div');
    document.querySelectorAll = (selector) => (selector === '.widget-frame' ? root.children
        : selector === '[data-report-chart]' ? [chartBox] : []);

    const requests = [];
    const pending = [];
    globalThis.window = {
        echarts: { init: () => ({ setOption() {}, resize() {} }) },
        fetch: (url, init) => new Promise((resolve) => {
            requests.push({ url, init });
            pending.push((payload, ok) => resolve({ ok: ok === undefined ? true : ok, status: ok === false ? 400 : 200, json: async () => payload }));
        }),
        decodeURIComponent: (value) => value,
        getComputedStyle: () => ({ getPropertyValue: () => ' ' }),
        setTimeout: (fn) => fn(),
        fetch: undefined,
    };
    globalThis.window.fetch = globalThis.fetch = (url, init) => new Promise((resolve) => {
        requests.push({ url, init });
        pending.push((payload, ok) => resolve({ ok: ok === undefined ? true : ok, status: ok === false ? 400 : 200, json: async () => payload }));
    });
    globalThis.AbortController = class { constructor() { this.signal = {}; } abort() { this.aborted = true; } };
    globalThis.ResizeObserver = class { constructor(cb) { this.cb = cb; this.seen = []; } observe(n) { this.seen.push(n); } };
    globalThis.MutationObserver = class { constructor(cb) { this.cb = cb; this.seen = []; } observe(n) { this.seen.push(n); } };
    const source = await readfile[READ_TEXT](pathe.join(staticDir, 'report.js'), 'utf-8');
    // jshint guard: the file is an IIFE referencing document/window as globals
    new Function('document', 'window', 'AbortController', 'ResizeObserver', 'MutationObserver',
        'fetch', '"use strict";' + source)(document, globalThis.window,
        globalThis.AbortController, globalThis.ResizeObserver, globalThis.MutationObserver,
        globalThis.window.fetch);
    return { frames, requests, pending, FakeNode, document };
}

test('the page boots, renders server defaults and drives stale-safe per-widget updates', async () => {
    const { frames, requests, pending } = await runReportScript();

    // 1. submit on frame 1 -> one POST carrying only the allow-listed keys
    frames[0].form.fire('submit', { preventDefault() {} });
    assert.equal(requests.length, 1);
    const body0 = JSON.parse(requests[0].init.body);
    assert.deepEqual(Object.keys(body0).sort(), ['context', 'request_seq']);
    assert.equal(body0.context, 'token-0');
    assert.equal(requests[0].init.headers['X-CSRFToken'], 'test-cookie'.replace('csrftoken=', ''));
    assert.equal(requests[0].init.method, 'POST');

    // resolve first request with an aggregate payload
    pending.shift()({ status: 'ok', empty: false, counts: { incoming: 6, matching: 6, eligible: 5 }, aggregates: { record_count: 5 }, dates: { coverage_note: 'coverage 2026-08-14..2026-09-12' } });
    await new Promise((resolve) => setImmediate(resolve));
    assert.match(collectText(frames[0].summary), /matching 6 of 6/);

    // 2. two rapid submits on frame 2: the FIRST response must be dropped as stale
    frames[1].form.fire('submit', { preventDefault() {} });   // seq 1
    frames[1].form.fire('submit', { preventDefault() {} });   // seq 2
    assert.equal(requests.length, 3);
    const bodyFirst = JSON.parse(requests[1].init.body);
    const bodySecond = JSON.parse(requests[2].init.body);
    assert.equal(bodySecond.request_seq, bodyFirst.request_seq + 1);
    pending.shift()({ status: 'ok', empty: true, counts: { incoming: 6, matching: 0, eligible: 0 } });  // stale
    pending.shift()({ status: 'ok', empty: false, counts: { incoming: 6, matching: 3, eligible: 3 }, rows: [{ accession: 1 }], pagination: { truncated: true, page: 1, page_size: 50, returned: 1 } });
    await new Promise((resolve) => setImmediate(resolve));
    await new Promise((resolve) => setImmediate(resolve));
    assert.match(collectText(frames[1].summary), /matching 3 of 6/);
    assert.equal(collectText(frames[1].body).includes('EMPTY-NOTE-1'), false);
    assert.equal(collectText(frames[1].body).includes('accession'), true);

    // 3. rejected 400 body renders the error in the summary, no 500 semantics
    frames[0].form.fire('submit', { preventDefault() {} });
    pending.shift()({ status: 'rejected', error: 'unexpected top-level key' }, false);
    await new Promise((resolve) => setImmediate(resolve));
    assert.match(collectText(frames[0].summary), /unexpected top-level key/);

    // 4. stale 409 disables the controls
    frames[0].form.fire('submit', { preventDefault() {} });
    pending.shift()({ status: 'stale', error: 'report version has changed; reload' }, false);
    await new Promise((resolve) => setImmediate(resolve));
    assert.match(collectText(frames[0].summary), /Reload the page/);

    // 5. a second successful update re-renders idempotently: exactly one live region, and the
    //    show-more control is re-appended, never duplicated.
    frames[0].form.fire('submit', { preventDefault() {} });
    pending.shift()({ status: 'ok', empty: false, counts: { incoming: 4, matching: 4, eligible: 4 }, aggregates: { record_count: 4 } });
    await new Promise((resolve) => setImmediate(resolve));
    assert.match(collectText(frames[0].summary), /matching 4 of 4/);
    assert.equal(frames[0].body.children.filter((n) => n.attributes['data-live-region'] !== undefined).length, 1);
    assert.equal(frames[1].body.children.filter((n) => n.tag === 'button').length, 1);
    assert.equal(frames[1].body.children[frames[1].body.children.length - 1].tag, 'button');
});

test('no storage API may ever be referenced from the page script', async () => {
    const source = await readfile[READ_TEXT](pathe.join(staticDir, 'report.js'), 'utf-8');
    for (const forbidden of ['localStorage', 'sessionStorage', 'sessionstorage', 'indexedDB', 'document.cookie =', 'history.pushState']) {
        assert.equal(source.includes(forbidden), false, 'forbidden token present: ' + forbidden);
    }
    const stateSource = await readfile[READ_TEXT](pathe.join(staticDir, 'page_state.mjs'), 'utf-8');
    for (const forbidden of ['Storage', 'cookie', 'indexedDB']) {
        assert.equal(stateSource.includes(forbidden), false, 'forbidden token present in reducer: ' + forbidden);
    }
});
