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
    get firstChild() { return this._children[0] || null; }
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
        if (selector === '[data-group-value]') {
            return this.descendants().filter((node) => node.attributes['data-group-value'] !== undefined);
        }
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
        createTextNode: (text) => { const node = new FakeNode('#text'); node.textContent = text; return node; },
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

async function runReportScript(withControls = true, withGroups = false) {
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
        if (withControls) { frame.register('[data-role="controls"]', form); }
        forms.push(form);
        if (type === 'table') {
            const more = new FakeNode('button');
            frame.register('[data-action="more"]', more);
        }
        if (withGroups) {
            frame.dataset.defaultComparison = 'site';
            const select = new FakeNode('select'); select.value = 'site';
            const picker = new FakeNode('details');
            const holder = new FakeNode('fieldset');
            frame.register('[data-comparison]', select);
            frame.register('[data-group-picker]', picker);
            frame.register('[data-group-options]', holder);
            frame.register('[data-group-count]', new FakeNode('span'));
            for (const action of ['select-groups', 'clear-groups']) {
                frame.register('[data-action="' + action + '"]', new FakeNode('button'));
            }
            const start = new FakeNode('input'); start.value = start.defaultValue = '2025-12-12';
            const end = new FakeNode('input'); end.value = end.defaultValue = 'D';
            frame.register('[data-date="start"]', start);
            frame.register('[data-date="end"]', end);
            frame.register('[data-date-picker="start"]', new FakeNode('input'));
            frame.register('[data-date-picker="end"]', new FakeNode('input'));
            frame.children.push(holder);
            const initial = new FakeNode('pre');
            initial.textContent = JSON.stringify({ aggregates: { n: 2 }, counts: { matching: 2, incoming: 2, eligible: 2 },
                group_options: { site: ['A', 'B'], age: ['Young', 'Older', 'Unknown'] } });
            frame.register('[data-initial-payload]', initial);
        }
        root.children.push(frame);
        frames.push({ frame, body, summary, form });
    }
    root.register('.widget-frame:not([data-decoration])', root.children);
    document.querySelector = (selector) => (selector === '[data-report-page]' ? root : null);
    const chartBox = new FakeNode('div');
    document.querySelectorAll = (selector) => (selector === '.widget-frame:not([data-decoration])' ? root.children
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

test('tables without settings still load the next page', async () => {
    const { frames, requests } = await runReportScript(false);
    frames[1].frame.querySelector('[data-action="more"]').fire('click', {});
    assert.equal(requests.length, 1);
    assert.equal(JSON.parse(requests[0].init.body).page, 2);
});


test('group selections survive date changes, reset on field changes, and remain card-local', async () => {
    const { frames, requests, pending } = await runReportScript(true, true);
    const frame = frames[0].frame;
    const other = frames[1].frame;
    let boxes = frame.querySelectorAll('[data-group-value]');
    assert.equal(boxes.length, 2);
    assert.ok(boxes.every((box) => box.checked));
    boxes[1].checked = false;
    frame.querySelector('[data-date="start"]').value = 'D-30';
    frames[0].form.fire('submit', { preventDefault() {} });
    assert.deepEqual(JSON.parse(requests[0].init.body).filters, { site: ['A'] });
    pending.shift()({ aggregates: { n: 1 }, counts: { matching: 1, incoming: 2, eligible: 1 },
        group_options: { site: ['A', 'B'], age: ['Young', 'Older', 'Unknown'] } });
    await new Promise((resolve) => setImmediate(resolve));
    boxes = frame.querySelectorAll('[data-group-value]');
    assert.deepEqual(boxes.map((box) => box.checked), [true, false]);
    assert.ok(other.querySelectorAll('[data-group-value]').every((box) => box.checked));
    const select = frame.querySelector('[data-comparison]');
    select.value = 'age'; select.fire('change');
    assert.equal(frame.querySelectorAll('[data-group-value]').length, 3);
    assert.ok(frame.querySelectorAll('[data-group-value]').every((box) => box.checked));
    frame.querySelector('[data-action="clear-groups"]').fire('click');
    frames[0].form.fire('submit', { preventDefault() {} });
    assert.deepEqual(JSON.parse(requests[1].init.body).filters, { age: [] });
    select.value = ''; select.fire('change');
    frames[0].form.fire('submit', { preventDefault() {} });
    const none = JSON.parse(requests[2].init.body);
    assert.equal(none.comparison, '');
    assert.equal(none.filters, undefined);
    assert.equal(frame.querySelector('[data-group-picker]').hidden, true);
});

test('time grouping is submitted independently of the selected date range', async () => {
    const { frames, requests } = await runReportScript(true, true);
    const windowSelect = new FakeNode('select'); windowSelect.value = 'month';
    frames[0].frame.register('[data-time-grouping]', windowSelect);
    frames[0].frame.querySelector('[data-date="start"]').value = 'Y';
    frames[0].form.fire('submit', { preventDefault() {} });
    const body = JSON.parse(requests[0].init.body);
    assert.equal(body.time_grouping, 'month');
    assert.deepEqual(body.date, { start: 'Y', end: 'D' });
    assert.equal(JSON.parse(requests[0].init.body).comparison, 'site');
});

test('blank boundaries restore YAML defaults and accept independently edited tokens', async () => {
    const { frames, requests } = await runReportScript(true, true);
    const start = frames[0].frame.querySelector('[data-date="start"]');
    const end = frames[0].frame.querySelector('[data-date="end"]');
    start.value = ' w-2 '; end.value = ' m-1 ';
    frames[0].form.fire('submit', { preventDefault() {} });
    assert.deepEqual(JSON.parse(requests[0].init.body).date, { start: 'W-2', end: 'M-1' });
    start.value = ''; end.value = '';
    frames[0].form.fire('submit', { preventDefault() {} });
    assert.deepEqual(JSON.parse(requests[1].init.body).date, { start: '2025-12-12', end: 'D' });
});

test('Overall is an explicit override of the YAML bucket', async () => {
    const { frames, requests } = await runReportScript(true, true);
    const grouping = new FakeNode('select'); grouping.value = '';
    frames[0].frame.register('[data-time-grouping]', grouping);
    frames[0].form.fire('submit', { preventDefault() {} });
    assert.equal(JSON.parse(requests[0].init.body).time_grouping, '');
});

test('day-first dates and native pickers preserve relative expressions', async () => {
    const { frames, requests } = await runReportScript(true, true);
    const frame = frames[0].frame;
    const start = frame.querySelector('[data-date="start"]');
    const end = frame.querySelector('[data-date="end"]');
    const picker = frame.querySelector('[data-date-picker="start"]');
    start.value = '03/08/2026'; end.value = '11-08-2026';
    start.fire('input');
    assert.equal(picker.value, '2026-08-03');
    frames[0].form.fire('submit', { preventDefault() {} });
    assert.deepEqual(JSON.parse(requests[0].init.body).date, { start: '2026-08-03', end: '2026-08-11' });
    picker.value = '2026-08-05'; picker.fire('change');
    assert.equal(start.value, '05/08/2026');
    start.value = 'W-2'; start.fire('input');
    assert.equal(picker.value, '');
    let opened = false; picker.showPicker = () => { opened = true; }; picker.fire('click');
    assert.equal(opened, true);
});

test('single-digit day-first dates normalize for both boundaries and pickers', async () => {
    const { frames, requests } = await runReportScript(true, true);
    const frame = frames[0].frame;
    for (const [startValue, endValue] of [['5/4/2026', '7/4/2026'], ['5-4-2026', '07-04-2026'], ['05/4/2026', '7/04/2026'], ['5/4/26', '7/4/26'], ['05-04-26', '07-04-26']]) {
        const start = frame.querySelector('[data-date="start"]');
        const end = frame.querySelector('[data-date="end"]');
        start.value = startValue; end.value = endValue;
        start.fire('input'); end.fire('input');
        assert.equal(frame.querySelector('[data-date-picker="start"]').value, '2026-04-05');
        assert.equal(frame.querySelector('[data-date-picker="end"]').value, '2026-04-07');
        frames[0].form.fire('submit', { preventDefault() {} });
        assert.deepEqual(JSON.parse(requests.at(-1).init.body).date, { start: '2026-04-05', end: '2026-04-07' });
    }
});

test('two-digit years use the 2000s and four-digit years stay literal', async () => {
    const { frames, requests } = await runReportScript(true, true);
    const frame = frames[0].frame;
    for (const [year, expected] of [['00', '2000'], ['99', '2099'], ['1999', '1999']]) {
        frame.querySelector('[data-date="start"]').value = '5/4/' + year;
        frame.querySelector('[data-date="end"]').value = '7/4/' + year;
        frames[0].form.fire('submit', { preventDefault() {} });
        assert.deepEqual(JSON.parse(requests.at(-1).init.body).date, { start: expected + '-04-05', end: expected + '-04-07' });
    }
});

test('defaults and typed fixed dates display with day-first slashes', async () => {
    const { frames } = await runReportScript(true, true);
    const start = frames[0].frame.querySelector('[data-date="start"]');
    const end = frames[0].frame.querySelector('[data-date="end"]');
    assert.equal(start.value, '12/12/2025');
    assert.equal(end.value, 'D');
    start.value = '5-4-26'; start.fire('blur');
    assert.equal(start.value, '05/04/2026');
    start.value = 'W-2'; start.fire('blur');
    assert.equal(start.value, 'W-2');
});
