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
        const resizeHandler = new ResizeObserver(() => charts.forEach((chart) => chart.resize()));
        chartContainers.forEach((container) => resizeHandler.observe(container));
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
            defaults: node.dataset.defaultComparison === undefined ? {} : { comparison: node.dataset.defaultComparison },
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
    const displayDates = (value) => String(value).replace(/\b(\d{4})-(\d{2})-(\d{2})\b/g, '$3/$2/$1');
    const textRow = (parent, text) => {
        const cell = el('td');
        cell.textContent= text === null || text === undefined ? '—' : displayDates(text);
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
        if (coverage) { text += ' (' + displayDates(coverage) + ')'; }
        return text;
    }

    // The registry bridge: when boot.mjs has published window.__rv2widgets.registry (the shipped
    // value/table/line/bar renderers), an eligible frame is painted through it. When the host is
    // absent (node harnesses, or a failed module load) widgetRegistry() is null and the legacy
    // table/aggregates/empty path below runs byte-for-byte unchanged.
    const widgetRegistry = () => {
        const host = window.__rv2widgets;
        const reg = host && host.registry;
        return reg && typeof reg.render === 'function' && typeof reg.disposeInstance === 'function' ? reg : null;
    };

    function renderFrame(frame, payload) {
        frame.el.querySelectorAll('[data-csv-download]').forEach((link) => {
            const dates = payload.dates || {};
            link.hidden = !dates.window_start || !dates.window_end;
            if (link.hidden) { return; }
            const url = new URL(link.href, window.location.href);
            url.searchParams.set('date_from', dates.window_start);
            url.searchParams.set('date_to', dates.window_end);
            url.searchParams.delete('site');
            const site = (state.widgets[frame.id].overrides.filters || {}).site;
            if (site) { (Array.isArray(site) ? site : [site]).forEach((value) => url.searchParams.append('site', value)); }
            link.href = url.toString();
        });
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
        // Registry path (fallback-safe): dispose the previous instance once, render into the fresh
        // live node, and on any throw fall through to the legacy builder below.
        const reg = widgetRegistry();
        const kind = frame.type;
        let usedRegistry = false;
        if (reg && (kind === 'value' || kind === 'table' || kind === 'line' || kind === 'bar' || kind === 'pie' || kind === 'confusion_matrix' || kind === 'boxplot')) {
            try {
                if (frame.regInstance && !frame.regDisposed) {
                    reg.disposeInstance(frame.regInstance);
                }
                frame.regDisposed = true;
                // The shipped renderers own (and re-class) their container element (line/bar set
                // widget-chart classes on it), so they receive a dedicated mount child; the live
                // wrapper itself keeps its widget-live class + data-live-region marker intact.
                const mount = el('div', 'widget-mount');
                live.append(mount);
                const regInstance = reg.render(kind, mount, payload, { primaryOnly: kind === 'value', measurement: frame.el.dataset.measurement, hideCaption: true });
                frame.regInstance = regInstance || null;
                frame.regDisposed = false;
                usedRegistry = true;
            } catch (regError) {
                usedRegistry = false;
            }
        }
        if (!usedRegistry) {
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
        }
        body.append(live);
        frame.liveNode = live;
        renderGroups(frame, payload, false);
        if (frame.more) {
            frame.more.hidden = !(payload && payload.pagination && payload.pagination.truncated);
            body.append(frame.more);
        }
        const reference = frame.el.querySelector('[data-reference]');
        if (reference) { reference.textContent = frame.type === 'value' ? '' : (payload.caption || ''); }
        const summary = frame.summary;
        if (summary) { summary.textContent = summaryText(payload); summary.hidden = frame.type === 'value'; }
    }

    function updateGroupCount(frame) {
        const count = frame.el.querySelector('[data-group-count]');
        if (!count) { return; }
        const boxes = Array.from(frame.el.querySelectorAll('[data-group-value]'));
        count.textContent = '(' + boxes.filter((box) => box.checked).length + ' of ' + boxes.length + ')';
    }

    function renderGroups(frame, payload, reset) {
        const picker = frame.el.querySelector('[data-group-picker]');
        const select = frame.el.querySelector('[data-comparison]');
        const holder = frame.el.querySelector('[data-group-options]');
        if (!picker || !select || !holder) { return; }
        if (select.disabled) { picker.hidden = true; return; }
        if (payload && payload.group_options) { frame.groupOptions = payload.group_options; }
        const field = select.value;
        picker.hidden = !field;
        const menu = frame.el.querySelector('[data-group-menu]');
        if (!field && menu && menu.matches(':popover-open')) { menu.hidePopover(); }
        if (!field) { frame.groupField = ''; return; }
        const existing = Array.from(frame.el.querySelectorAll('[data-group-value]'));
        const chosen = !reset && frame.groupField === field
            ? new Set(existing.filter((box) => box.checked).map((box) => box.value)) : null;
        while (holder.firstChild) { holder.removeChild(holder.firstChild); }
        const legend = el('legend', 'widget-a11y');
        legend.textContent = 'Included groups';
        holder.append(legend);
        for (const value of (frame.groupOptions || {})[field] || []) {
            const label = el('label');
            const box = el('input');
            box.type = 'checkbox';
            box.value = String(value);
            box.setAttribute('data-group-value', '');
            box.checked = chosen === null || chosen.has(box.value);
            box.addEventListener('change', () => updateGroupCount(frame));
            label.append(box, document.createTextNode(String(value)));
            holder.append(label);
        }
        frame.groupField = field;
        updateGroupCount(frame);
    }

    function renderInitialFrames() {
        frames.forEach((frame) => {
            const initial = frame.el.querySelector('[data-initial-payload]');
            if (!initial) { return; }
            try {
                const payload = JSON.parse(initial.textContent);
                state.widgets[frame.id].lastResult = payload;
                renderFrame(frame, payload);
            } catch (error) { /* Keep the server-rendered content if hydration fails. */ }
        });
    }
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', renderInitialFrames, { once: true });
    } else {
        renderInitialFrames();
    }

    function dateExpression(value) {
        const text = value.trim().toUpperCase();
        const date = text.match(/^(\d{1,2})([-/])(\d{1,2})\2(\d{2}|\d{4})$/);
        return date ? (date[4].length === 2 ? '20' + date[4] : date[4]) + '-' + date[3].padStart(2, '0') + '-' + date[1].padStart(2, '0') : text;
    }

    function collectOverrides(frame) {
        const overrides = baseDefaults();
        const timeGrouping = frame.el.querySelector('[data-time-grouping]');
        if (timeGrouping) { overrides.time_grouping = timeGrouping.value; }
        const start = frame.el.querySelector('[data-date="start"]');
        const end = frame.el.querySelector('[data-date="end"]');
        if (start && end) {
            overrides.date = {
                start: dateExpression(start.value.trim() || start.defaultValue),
                end: dateExpression(end.value.trim() || end.defaultValue)
            };
        }
        frame.el.querySelectorAll('[data-filter]').forEach((input) => {
            const value = input.value === null || input.value === undefined ? '' : String(input.value).trim();
            if (value !== '') { overrides.filters[input.dataset.filter] = value; }
        });
        const comparison = frame.el.querySelector('[data-comparison]');
        if (comparison && comparison.disabled) { overrides.comparison = ""; }
        if (comparison && !comparison.disabled) {
            overrides.comparison = comparison.value;
            if (comparison.value && frame.el.querySelector('[data-group-options]')) {
                overrides.filters[comparison.value] = Array.from(frame.el.querySelectorAll('[data-group-value]'))
                    .filter((box) => box.checked).map((box) => box.value);
            }
        }
        const widget = state.widgets[frame.id];
        overrides.page = (widget && widget.overrides.page) || 1;
        return overrides;
    }

    function showStale(frame, errorText) {
        if (frame.summary) {
            frame.summary.hidden = false;
            const settings = frame.el.querySelector(".widget-settings");
            if (settings) { settings.open = true; }
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
                frame.summary.hidden = false;
                const settings = frame.el.querySelector(".widget-settings");
                if (settings) { settings.open = true; }
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
        if (Object.prototype.hasOwnProperty.call(overrides, 'time_grouping')) { body.time_grouping = overrides.time_grouping; }
        if (Object.keys(overrides.filters).length) { body.filters = overrides.filters; }
        if (overrides.comparison !== null) { body.comparison = overrides.comparison; }
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
                    frame.summary.hidden = false;
                    const settings = frame.el.querySelector(".widget-settings");
                    if (settings) { settings.open = true; }
                    frame.summary.textContent = 'The update failed: '
                        + (error && error.message ? error.message : String(error));
                }
            });
    }

    frames.forEach((frame) => {
        const form = frame.form;
        for (const bound of ['start', 'end']) {
            const input = frame.el.querySelector('[data-date="' + bound + '"]');
            const picker = frame.el.querySelector('[data-date-picker="' + bound + '"]');
            if (!input || !picker) { continue; }
            const displayDate = () => {
                const value = dateExpression(input.value);
                if (/^\d{4}-\d{2}-\d{2}$/.test(value)) { input.value = value.split('-').reverse().join('/'); }
            };
            displayDate();
            input.addEventListener('blur', displayDate);
            picker.addEventListener('click', () => {
                if (typeof picker.showPicker === 'function') {
                    try { picker.showPicker(); } catch (error) { /* Native control remains available. */ }
                }
            });
            picker.addEventListener('change', () => {
                if (picker.value) { input.value = picker.value.split('-').reverse().join('/'); }
            });
            input.addEventListener('input', () => {
                const value = dateExpression(input.value);
                picker.value = /^\d{4}-\d{2}-\d{2}$/.test(value) ? value : '';
            });
        }
        if (form) {
            form.addEventListener('submit', (event) => {
                event.preventDefault();
                const widget = state.widgets[frame.id];
                widget.overrides = collectOverrides(frame);
                fetchFrame(frame, widget.overrides);
            });
            form.addEventListener('reset', () => {
                window.setTimeout(() => {                        // let the browser clear the controls first
                    const groupSelect = frame.el.querySelector('[data-comparison]');
                if (groupSelect) { groupSelect.value = frame.defaults.comparison || ''; }
                renderGroups(frame, null, true);
                resetWidgetState(state, frame.id);
                    fetchFrame(frame, state.widgets[frame.id].overrides);
                }, 0);
            });
        }
        const groupMenu = frame.el.querySelector('[data-group-menu]');
        if (groupMenu) {
            groupMenu.addEventListener('beforetoggle', (event) => {
                if (event.newState !== 'open') { return; }
                const trigger = frame.el.querySelector('[data-group-trigger]').getBoundingClientRect();
                groupMenu.style.left = Math.max(12, Math.min(trigger.left, window.innerWidth - 252)) + 'px';
                groupMenu.style.top = Math.max(12, Math.min(trigger.bottom + 4, window.innerHeight - 236)) + 'px';
            });
        }
        const groupSelect = frame.el.querySelector('[data-comparison]');
        if (groupSelect) { groupSelect.addEventListener('change', () => renderGroups(frame, null, true)); }
        for (const [action, checked] of [['select-groups', true], ['clear-groups', false]]) {
            const button = frame.el.querySelector('[data-action="' + action + '"]');
            if (button) {
                button.addEventListener('click', () => {
                    frame.el.querySelectorAll('[data-group-value]').forEach((box) => { box.checked = checked; });
                    updateGroupCount(frame);
                });
            }
        }
        if (frame.more) {
            frame.more.addEventListener('click', () => {
                const widget = state.widgets[frame.id];
                widget.overrides = Object.assign({}, widget.overrides, { page: (widget.overrides.page || 1) + 1 });
                fetchFrame(frame, widget.overrides);
            });
        }
    });

    // -- print / email exports (Tasks 17 + 18) ----------------------------------------------
    // Blocks the export while any widget update is pending, then freezes the *server-side*
    // evaluation of every widget under the current selections. The print button opens the
    // print view; the email modal sends a legacy-style HTML email off the same snapshot.
    // The snapshot is export state only; nothing here writes it back into widget state.
    const printButton = document.querySelector('[data-action="print"]');
    const printStatus = document.querySelector('[data-role="print-status"]');
    const SNAPSHOT_URL = '/report/' + encodeURIComponent(root.dataset.slug || '') + '/snapshot/';
    const EMAIL_URL = '/report/' + encodeURIComponent(root.dataset.slug || '') + '/email/';
    const PRINT_SETTLE_MS = 15000;
    const PRINT_POLL_MS = 150;

    const updatesSettled = () => {
        if (inflightByWidget.size) { return false; }
        return frames.every((frame) => {
            const widget = state.widgets[frame.id];
            if (!widget) { return true; }
            // -1/-1 means never requested (server defaults are on screen); n/n means applied.
            return widget.pendingSeq <= widget.lastAppliedSeq;
        });
    };

    const snapshotEntries = () => frames.map((frame) => {
        const widget = state.widgets[frame.id] || { overrides: baseDefaults() };
        const overrides = widget.overrides || baseDefaults();
        const entry = { context: frame.el.dataset.contextToken };
        if (overrides.date) { entry.date = overrides.date; }
        if (Object.prototype.hasOwnProperty.call(overrides, 'time_grouping')) { entry.time_grouping = overrides.time_grouping; }
        if (overrides.filters && Object.keys(overrides.filters).length) { entry.filters = overrides.filters; }
        if (overrides.comparison !== null) { entry.comparison = overrides.comparison; }
        if (frame.type === 'table' && overrides.page > 1) { entry.page = overrides.page; }
        return entry;
    });

    const setPrintStatus = (text, href) => {
        if (!printStatus) { return; }
        while (printStatus.firstChild) { printStatus.removeChild(printStatus.firstChild); }
        if (href) {
            const link = el('a');
            link.href = href;
            link.textContent = text;
            printStatus.append(link);
        } else {
            printStatus.textContent = text || '';
        }
    };

    const openPrintView = (printUrl) => {
        const opened = window.open(printUrl, '_blank');
        if (!opened) {
            // Popup refused (common with blockers): offer a direct navigation fallback.
            setPrintStatus('The print view was blocked from opening. Open it here.', printUrl);
        }
    };

    // Shared freeze: resolves {print_url, token} once every widget update has settled.
    const postSnapshot = (onWait) => new Promise((resolve, reject) => {
        const started = Date.now();
        const attempt = (n) => {
            if (!updatesSettled()) {
                if (Date.now() - started > PRINT_SETTLE_MS) {
                    reject(new Error('Widget updates are still pending; the export was not created. ' +
                        'Try again once they finish.'));
                    return;
                }
                if (onWait) { onWait(); }
                window.setTimeout(() => { attempt(n); }, PRINT_POLL_MS);
                return;
            }
            window.fetch(SNAPSHOT_URL, {
                method: 'POST',
                credentials: 'same-origin',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': CSRFToken() },
                body: JSON.stringify({ settled: true, widgets: snapshotEntries() })
            })
                .then((response) => response.json()
                    .then((payload) => ({ ok: response.ok, status: response.status, payload })))
                .then((result) => {
                    if (result.status === 201 && result.payload.token) {
                        resolve(result.payload);
                        return;
                    }
                    if (result.status === 409 && n < 4) {
                        // The server still sees an unsettled race; wait and retry.
                        if (onWait) { onWait(); }
                        window.setTimeout(() => { attempt(n + 1); }, PRINT_POLL_MS * 4);
                        return;
                    }
                    reject(new Error((result.payload && result.payload.error) ||
                        ('The export failed (' + result.status + ').')));
                })
                .catch((error) => { reject(error); });
        };
        attempt(0);
    });

    if (printButton) {
        printButton.addEventListener('click', () => {
            printButton.disabled = true;
            postSnapshot(() => { setPrintStatus('Waiting for pending widget updates…'); })
                .then((payload) => {
                    setPrintStatus('');
                    openPrintView(payload.print_url);
                })
                .catch((error) => { setPrintStatus(error.message || String(error)); })
                .finally(() => { printButton.disabled = false; });
        });
    }

    // -- email modal (Task 18) ---------------------------------------------------------------
    const CHART_TYPES = { line: 1, bar: 1, pie: 1, boxplot: 1 };
    const emailModal = document.querySelector('[data-role="email-modal"]');
    const emailForm = document.querySelector('[data-role="email-form"]');
    const emailRecipients = document.querySelector('[data-role="email-recipients"]');
    const emailNote = document.querySelector('[data-role="email-note"]');
    const emailStatus = document.querySelector('[data-role="email-status"]');
    const emailSend = document.querySelector('[data-action="email-send"]');
    const emailCancel = document.querySelector('[data-action="email-cancel"]');
    const emailButton = document.querySelector('[data-action="email"]');

    const setEmailStatus = (text) => {
        if (emailStatus) { emailStatus.textContent = text || ''; }
    };

    // PNG captures of the live charts (only chart-typed frames with a live instance).
    // The server validates names/content/size against the snapshot; values never come
    // from the browser -- the email body is rendered from the frozen document.
    const captureChartImages = () => {
        const images = {};
        frames.forEach((frame) => {
            if (!CHART_TYPES[frame.type]) { return; }
            const chart = frame.regInstance && frame.regInstance.chart;
            if (frame.regDisposed || !chart || typeof chart.getDataURL !== 'function') { return; }
            try {
                const url = chart.getDataURL({ type: 'png', pixelRatio: 2, backgroundColor: '#ffffff' });
                if (url && url.indexOf('data:image/png;base64,') === 0) { images[frame.id] = url; }
            } catch (captureError) {
                // Not capture-ready; the email falls back to the frozen text tables.
            }
        });
        return images;
    };

    if (emailButton && emailModal && emailForm) {
        emailButton.addEventListener('click', () => {
            setEmailStatus('');
            if (emailSend) { emailSend.disabled = false; }
            emailModal.hidden = false;
            if (emailRecipients) { emailRecipients.focus(); }
        });
        const closeModal = () => {
            emailModal.hidden = true;
            setEmailStatus('');
        };
        if (emailCancel) { emailCancel.addEventListener('click', closeModal); }
        emailModal.addEventListener('click', (event) => {
            if (event.target === emailModal) { closeModal(); }
        });
        emailForm.addEventListener('submit', (event) => {
            event.preventDefault();
            const raw = (emailRecipients && emailRecipients.value) || '';
            const recipients = raw.split(/[,;\n]+/).map((item) => { return item.trim(); })
                .filter((item) => { return item !== ''; });
            if (!recipients.length) {
                setEmailStatus('Enter at least one email address.');
                return;
            }
            const note = ((emailNote && emailNote.value) || '').trim();
            if (emailSend) { emailSend.disabled = true; }   // duplicate-click prevention
            setEmailStatus('Waiting for pending widget updates…');
            postSnapshot(() => { setEmailStatus('Waiting for pending widget updates…'); })
                .then((payload) => {
                    setEmailStatus('Capturing the report…');
                    const images = captureChartImages();
                    return window.fetch(EMAIL_URL, {
                        method: 'POST',
                        credentials: 'same-origin',
                        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': CSRFToken() },
                        body: JSON.stringify({
                            snapshot: payload.token,
                            recipients: recipients,
                            note: note,
                            images: images
                        })
                    })
                        .then((response) => response.json()
                            .then((body) => ({ ok: response.ok, status: response.status, body })));
                })
                .then((result) => {
                    if (result.ok && result.body.status === 'sent') {
                        setEmailStatus('Sent to ' + (result.body.sent_to || []).join(', ') + '.');
                        window.setTimeout(() => {
                            emailModal.hidden = true;
                            setEmailStatus('');
                        }, 1200);
                        return;
                    }
                    if (result.status === 409 && result.body.status === 'duplicate') {
                        setEmailStatus('This report was already sent to these recipients from this snapshot.');
                        return;
                    }
                    setEmailStatus((result.body && result.body.error) ||
                        ('The email failed (' + result.status + ').'));
                })
                .catch((error) => {
                    setEmailStatus('The email failed: ' +
                        (error && error.message ? error.message : String(error)));
                })
                .finally(() => {
                    if (emailSend) { emailSend.disabled = false; }
                });
        });
    }
})();
