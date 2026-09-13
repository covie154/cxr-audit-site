/*
 * report_v2 page behaviour.
 *
 * Two responsibilities:
 *  1. the index page's empty chart placeholder (guarded so it no-ops elsewhere);
 *  2. the report page: per-widget controls, per-widget state and STALE-SAFE async updates.
 *
 * State lives only inside this closure, so a fresh navigation always starts from the
 * server-rendered defaults; no storage API is used anywhere (a test greps for it). The
 * canonical state machine is static/report_v2/page_state.mjs (node-tested); because this file
 * is a classic script loaded without module machinery, the reducer is mirrored verbatim below
 * behind a window.__rv2 hook and kept in lock-step by the node harness.
 */
(() => {
    'use strict';

    // -- index page chart placeholder --------------------------------------------------------
    const chartContainers = document.querySelectorAll('[data-report-chart]');
    if (chartContainers.length && window.echarts) {
        const charts = Array.from(chartContainers, (container) => window.echarts.init(container));
        const renderCharts = () => {
            const styles = window.getComputedStyle(document.documentElement);
            charts.forEach((chart) => chart.setOption({
                animation: false,
                graphic: [{
                    type: 'text', left: 'center', top: 'middle',
                    style: {
                        text: 'Your report charts will appear here',
                        fill: styles.getPropertyValue('--c-text-muted').trim(),
                        font: '14px sans-serif'
                    }
                }]
            }));
        };
        renderCharts();
        const resizeObserver = new ResizeObserver(() => charts.forEach((chart) => chart.resize()));
        chartContainers.forEach((container) => resizeObserver.observe(container));
        const themeObserver = new MutationObserver (renderCharts);
        themeObserver.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
    } else if (chartContainers.length) {
        const status = document.getElementById('chartStatus');
        if (status) {
            status.textContent= 'Charts could not load. Reload the page to try again.';
        }
    }

    // -- report page -------------------------------------------------------------------------
    const root = document.querySelector('[data-report-page]');
    if (!root) {
        return;
    }

    const canonical = window.__rv2 || null;

    const baseDefaults = (extra) => Object.assign(
        { date: null, filters: {}, comparison: null, page: 1 }, extra || {});

    // Mirrors of page_state.mjs (used when the module is not loaded on this page).
    function createPageState(frames) {
        if (canonical && canonical.createPageState) { return canonical.createPageState(frames); }
        const state = { widgets: {}, droppedStale: 0 };
        frames.forEach((frame) => {
            state.widgets[frame.id] = {
                defaults: baseDefaults(frame.defaults),
                overrides: baseDefaults(frame.defaults),
                pendingSeq: -1,
                lastAppliedSeq: -1,
                lastResult: null
            };
        });
        return state;
    }
    function beginRequest(state, widgetId, seq) {
        if (canonical && canonical.beginRequest) { return canonical.beginRequest(state, widgetId, seq); }
        const widget = state.widgets[widgetId];
        if (widget) { widget.pendingSeq= seq; }
        return state;
    }
    function applyWidgetResult(state, widgetId, result, seq) {
        if (canonical && canonical.applyWidgetResult) {
            return canonical.applyWidgetResult(state, widgetId, result, seq);
        }
        const widget = state.widgets[widgetId];
        if (!widget) { return state; }
        const stillNewest = seq === widget.pendingSeq;
        const newerThanApplied = seq > widget.lastAppliedSeq;
        if (!stillNewest || !newerThanApplied) {
            state.droppedStale= (state.droppedStale || 0) + 1;
            return state;
        }
        widget.lastAppliedSeq= seq;
        widget.lastResult= result;
        return state;
    }
    function resetWidgetState(state, widgetId) {
        if (canonical && canonical.resetWidget) { return canonical.resetWidget(state, widgetId); }
        const widget = state.widgets[widgetId];
        if (widget) {
            widget.overrides = baseDefaults(widget.defaults);
            widget.pendingSeq= -1;
            widget.lastAppliedSeq= -1;
            widget.lastResult= null;
        }
        return state;
    }

    const CSRFToken = () => {
        // House idiom: hidden input when non-empty, otherwise the csrftoken= cookie.
        const holder = document.querySelector('[data-role="csrf"] [name="csrfmiddlewaretoken"]');
        if (holder && holder.value) { return holder.value; }
        const parts = String(document.cookie || '').split(';');
        for (let i = 0; i < parts.length; i += 1) {
            const pair = parts[i].trim();
            if (pair.indexOf('csrftoken=') === 0) {
                return window.decodeURIComponent(pair.substring('csrftoken='.length));
            }
        }
        return '';
    };

    const DEFAULT_EMPTY = 'No matching records in this window -- the dates or filters may exclude every record. Adjust the controls or reset them.';

    // The harness (and the browser) register the frames on the document, so the frame enumeration
    // is a document-level query; every lookup *inside* a frame stays scoped to that frame element.
    const frames = Array.from(document.querySelectorAll('.widget-frame'), (node) => {
        const placeholder = node.querySelector('[data-role="empty-message"]');
        return {
            id: node.dataset.widgetId,
            type: node.dataset.type,
            el: node,
            form: node.querySelector('[data-role="controls"]'),
            body: node.querySelector('[data-widget-body]'),
            summary: node.querySelector('.widget-summary'),
            more: node.querySelector('[data-action="more"]'),
            controls: node.querySelectorAll('.widget-controls input, .widget-controls select, .widget-controls button'),
            serverRendered: true,
            liveNode: null,
            emptyMessage: placeholder ? placeholder.textContent.trim() || DEFAULT_EMPTY : DEFAULT_EMPTY
        };
    });
    const state = createPageState(frames);
    const seqByWidget = new Map();
    const inflightByWidget = new Map();

    const el = (tag, className) => {
        const node = document.createElement(tag);
        if (className) { node.className= className; }
        return node;
    };
    const textRow = (parent, text) => {
        const cell = el('td');
        cell.textContent= text === null || text === undefined ? '—' : String(text);
        parent.append(cell);
    };

    function buildTable(rows) {
        const table = el('table', 'widget-table');
        const columnSet = new Set();
        rows.forEach((row) => Object.keys(row).forEach((key) => columnSet.add(key)));
        const columns = Array.from(columnSet);
        const head = el('tr');
        columns.forEach((key) => {
            const th = el('th');
            th.textContent= key;
            head.append(th);
        });
        const thead = el('thead');
        thead.append(head);
        const tbody = el('tbody');
        rows.forEach((row) => {
            const tr = el('tr');
            columns.forEach((key) => textRow(tr, row[key]));
            tbody.append(tr);
        });
        table.append(thead, tbody);
        return table;
    }

    function buildAggregates(aggregates) {
        const table = el('table', 'widget-table widget-table-aggregates');
        Object.entries(aggregates).forEach(([name, value]) => {
            const tr = el('tr');
            const th = el('th');
            th.textContent= name;
            const td = el('td');
            td.textContent= value !== null && typeof value === 'object'
                ? Object.entries(value).map(([k, v]) => k + '=' + v).join(', ')
                : String(value);
            tr.append(th, td);
            table.append(tr);
        });
        return table;
    }

    // Lock-step with views._summary_text: the same numbers, the same shape.
    function summaryText(payload) {
        if (payload && payload.error) { return String(payload.error); }
        const counts = (payload && payload.counts) || {};
        if (!counts.matching) { return DEFAULT_EMPTY; }
        let text = 'matching ' + counts.matching + ' of ' + counts.incoming +
            ' · ' + counts['eligible'] + ' eligible for measurement';
        const coverage = ((payload.dates || {}).coverage_note);
        if (coverage) { text += ' (' + coverage + ')'; }
        return text;
    }

    function renderFrame(frame, payload) {
        const body = frame.body;
        if (!body) { return; }
        const isChild = (node) => Array.prototype.indexOf.call(body.children, node) >= 0;
        if (frame.serverRendered) {
            // The first fresh render replaces the server-rendered initial content wholesale, so a
            // stale server message can never survive underneath the client-side result.
            Array.prototype.slice.call(body.children, 0).forEach((node) => { body.removeChild(node); });
            frame.serverRendered = false;
        }
        if (frame.liveNode && isChild(frame.liveNode)) { body.removeChild(frame.liveNode); }
        frame.liveNode = null;
        if (frame.more && isChild(frame.more)) { body.removeChild(frame.more); }
        const live = el('div', 'widget-live');
        live.setAttribute('data-live-region', '');
        const empty = !payload || payload.error || payload.empty;
        if (empty) {
            const note = el('p', 'widget-empty');
            note.textContent = payload && payload.error ? String(payload.error) : frame.emptyMessage;
            live.append(note);
        } else if (frame.type === 'table' && Array.isArray(payload.rows) && payload.rows.length) {
            live.append(buildTable(payload.rows));
        } else if (payload.aggregates && Object.keys(payload.aggregates).length) {
            live.append(buildAggregates(payload.aggregates));
        } else {
            const note = el('p', 'widget-empty');
            note.textContent = frame.emptyMessage;
            live.append(note);
        }
        body.append(live);
        frame.liveNode = live;
        if (frame.more) {
            frame.more.hidden = !(payload && payload.pagination && payload.pagination.truncated);
            body.append(frame.more);
        }
        const summary = frame.summary;
        if (summary) { summary.textContent = summaryText(payload); }
    }

    function collectOverrides(frame) {
        const overrides = baseDefaults();
        const relative = frame.el.querySelector('[data-date="relative"]');
        const start = frame.el.querySelector('[data-date="start"]');
        const end = frame.el.querySelector('[data-date="end"]');
        if (relative && relative.value) {
            overrides.date = { relative: relative.value };
        } else if (start && end && start.value && end.value) {
            overrides.date = { start: start.value, end: end.value };
        }
        frame.el.querySelectorAll('[data-filter]').forEach((input) => {
            const value = input.value === null || input.value === undefined ? '' : String(input.value).trim();
            if (value !== '') { overrides.filters[input.dataset.filter] = value; }
        });
        const comparison = frame.el.querySelector('[data-comparison]');
        if (comparison && comparison.value) { overrides.comparison = comparison.value; }
        const widget = state.widgets[frame.id];
        overrides.page = (widget && widget.overrides.page) || 1;
        return overrides;
    }

    function showStale(frame, errorText) {
        if (frame.summary) {
            frame.summary.textContent = String(errorText || 'The report version has changed.')
                + ' Reload the page for the newest published version.';
        }
        (frame.controls || []).forEach((node) => { node.disabled = true; });
    }

    function handleResult(frame, widgetId, seq, result) {
        const widget = state.widgets[widgetId];
        if (!widget || widget.pendingSeq !== seq) { return; }          // stale: never touch a newer selection
        applyWidgetResult(state, widgetId, result, seq);
        if (widget.lastAppliedSeq !== seq) { return; }                  // the reducer dropped it as stale
        inflightByWidget.delete(widgetId);
        const payload = (result && result.payload) || {};
        const status = payload.status;
        const failed = !result.ok || status === 'error' || status === 'rejected' || status === 'stale';
        if (failed) {
            if (status === 'stale') { showStale(frame, payload.error); return; }
            if (frame.summary) {
                frame.summary.textContent = String(payload.error || 'The update failed.');
            }
            return;
        }
        renderFrame(frame, payload);
    }

    function fetchFrame(frame, overrides) {
        const widgetId = frame.id;
        const seq = (seqByWidget.get(widgetId) || 0) + 1;
        seqByWidget.set(widgetId, seq);
        beginRequest(state, widgetId, seq);
        const previous = inflightByWidget.get(widgetId);
        if (previous) { previous.abort(); }
        const controller = new AbortController ();
        inflightByWidget.set(widgetId, controller);
        const body = { context: frame.el.dataset.contextToken, request_seq: seq };
        if (overrides.date) { body.date = overrides.date; }
        if (Object.keys(overrides.filters).length) { body.filters = overrides.filters; }
        if (overrides.comparison) { body.comparison = overrides.comparison; }
        if (frame.type === 'table' && overrides.page > 1) { body.page = overrides.page; }
        window.fetch(frame.el.dataset.dataUrl, {
            method: 'POST',
            credentials: 'same-origin',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': CSRFToken() },
            body: JSON.stringify(body),
            signal: controller.signal
        })
            .then((response) => response.json()
                .then((payload) => ({ ok: response.ok, status: response.status, payload })))
            .then((result) => handleResult(frame, widgetId, seq, result))
            .catch((error) => {
                if (error && error.name === 'AbortError') { return; }   // superseded by a newer request
                const widget = state.widgets[widgetId];
                if (widget && widget.pendingSeq=== seq && frame.summary) {
                    frame.summary.textContent = 'The update failed: '
                        + (error && error.message ? error.message : String(error));
                }
            });
    }

    frames.forEach((frame) => {
        const form = frame.form;
        if (!form) { return; }
        form.addEventListener('submit', (event) => {
            event.preventDefault();
            const widget = state.widgets[frame.id];
            widget.overrides = collectOverrides(frame);
            fetchFrame(frame, widget.overrides);
        });
        form.addEventListener('reset', () => {
            window.setTimeout(() => {                        // let the browser clear the controls first
                resetWidgetState(state, frame.id);
                fetchFrame(frame, state.widgets[frame.id].overrides);
            }, 0);
        });
        if (frame.more) {
            frame.more.addEventListener('click', () => {
                const widget = state.widgets[frame.id];
                widget.overrides = Object.assign({}, widget.overrides, { page: (widget.overrides.page || 1) + 1 });
                fetchFrame(frame, widget.overrides);
            });
        }
    });
})();
