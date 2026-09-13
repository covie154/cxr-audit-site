/*
 * report_v2 page-state reducer (pure, DOM-free) — canonical state machine for Task-13 widgets.
 *
 * Contract (mirrored by a defensive fallback inside report.js because that file is a classic
 * script loaded without module machinery; keep both in lock-step and let the node harness
 * (tests/js/page_state.test.mjs) be the judge of truth):
 *
 *   createPageState(frames)          -> pristine state; fresh navigation therefore resets defaults
 *   beginRequest(state, id, seq)     -> marks frame `id`'s newest in-flight request `seq`
 *   applyWidgetResult(state, id, result, seq)
 *                                    -> applies a response ONLY when it is still the newest request
 *                                       for that frame AND newer than its last applied sequence;
 *                                       anything else counts as a dropped stale response
 *   resetWidget(state, id, defaults) -> restores one frame to its declared defaults (fresh page feel)
 *
 * No storage API of any kind may ever appear in this file (a test greps for it).
 */

export function createPageState(frames) {
    const state = { widgets: {}, droppedStale: 0 };
    for (const frame of frames) {
        state.widgets[frame.id] = {
            defaults: { date: null, filters: {}, comparison: null, page: 1, ...frame.defaults },
            overrides: { date: null, filters: {}, comparison: null, page: 1, ...frame.defaults },
            pendingSeq: -1,
            lastAppliedSeq: -1,
            lastResult: null,
        };
    }
    return state;
}

export function beginRequest(state, widgetId, seq) {
    const widget = state.widgets[widgetId];
    if (!widget) {
        return state;
    }
    widget.pendingSeq = seq;
    return state;
}

export function applyWidgetResult(state, widgetId, result, seq) {
    const widget = state.widgets[widgetId];
    if (!widget) {
        return state;
    }
    const isStillNewest = seq === widget.pendingSeq;
    const isNewerThanApplied = seq > widget.lastAppliedSeq;
    if (!isStillNewest || !isNewerThanApplied) {
        state.droppedStale = (state.droppedStale || 0) + 1;
        return state;
    }
    widget.lastAppliedSeq = seq;
    widget.lastResult = result;
    return state;
}

export function setOverrides(state, widgetId, overrides) {
    const widget = state.widgets[widgetId];
    if (widget) {
        widget.overrides = { ...widget.overrides, ...overrides };
    }
    return state;
}

export function resetWidget(state, widgetId) {
    const widget = state.widgets[widgetId];
    if (widget) {
        widget.overrides = { ...widget.defaults };
        widget.pendingSeq = -1;
        widget.lastAppliedSeq = -1;
        widget.lastResult = null;
    }
    return state;
}
