import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { runInNewContext } from "node:vm";
import test from "node:test";

const source = readFileSync(new URL("../../static/report_v2/editor.js", import.meta.url), "utf8");
test("saving uses the report ID from the editor route without a report selector", async () => {
  let click, posted;
  const summary = { textContent: "" };
  const textarea = { value: "schema_version: 1", addEventListener() {} };
  const root = {
    querySelector: query => query.includes("yaml-textarea") ? textarea : query.includes("validation-summary") ? summary : null,
    addEventListener: (name, handler) => { if (name === "click") click = handler; },
    getAttribute: name => ({ "data-def-id": "my_report", "data-save-url": "/layout/actions/save/" })[name],
  };
  runInNewContext(source, {
    document: { querySelector: () => root, cookie: "" }, window: {},
    fetch: async (url, options) => { posted = { url, body: options.body }; return { status: 200, json: async () => ({ revision: "saved", errors: ["layout.height: invalid", "ci.enabled: invalid"] }) }; },
  });
  click({ target: { closest: () => ({ getAttribute: () => "save" }) }, preventDefault() {} });
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(summary.textContent, "2 validation issues");
  assert.equal(posted.url, "/layout/actions/save/");
  assert.equal(new URLSearchParams(posted.body).get("def_id"), "my_report");
});

test("selecting a card automatically requests its preview", async () => {
  let change;
  const requested = [];
  const card = { value: "first", addEventListener: (_, handler) => { change = handler; } };
  const root = {
    querySelector: query => query.includes("preview-card") ? card : null,
    addEventListener() {},
    getAttribute: name => ({ "data-def-id": "my_report", "data-preview-url": "/layout/actions/preview/" })[name],
  };
  runInNewContext(source, {
    document: { querySelector: () => root, cookie: "" }, window: {},
    fetch: async (url, options) => { requested.push(new URLSearchParams(options.body).get("widget_id")); return { status: 200, json: async () => ({}) }; },
  });
  card.value = "second";
  await change();
  card.value = "third";
  await change();
  assert.deepEqual(requested, ["second", "third"]);
});

test("an older preview response cannot replace the latest selection", async () => {
  let change;
  const pending = [];
  const summary = { textContent: "" };
  const card = { value: "first", addEventListener: (_, handler) => { change = handler; } };
  const root = {
    querySelector: query => query.includes("preview-card") ? card : query.includes("validation-summary") ? summary : null,
    addEventListener() {}, getAttribute: () => "/layout/actions/preview/",
  };
  runInNewContext(source, {
    document: { querySelector: () => root, cookie: "" }, window: {},
    fetch: () => new Promise(resolve => pending.push(resolve)),
  });
  const first = change();
  card.value = "second";
  const second = change();
  pending[1]({ status: 200, json: async () => ({ errors: [] }) });
  await second;
  pending[0]({ status: 200, json: async () => ({ errors: ["old response"] }) });
  await first;
  assert.equal(summary.textContent, "No errors");
});

test("editor tabs switch panels with clicks and keyboard without changing YAML", () => {
  const handlers = {};
  const panels = { visualEditorPanel: { hidden: false }, yamlEditorPanel: { hidden: true } };
  const tabs = Object.keys(panels).map((id, index) => ({
    selected: index === 0 ? "true" : "false", tabIndex: index === 0 ? 0 : -1,
    getAttribute: name => name === "aria-controls" ? id : "editor-tab",
    setAttribute(name, value) { if (name === "aria-selected") this.selected = value; },
    closest(selector) { return selector === ".widget-frame" ? null : this; }, focus() { this.focused = true; },
  }));
  const textarea = { value: "unsaved YAML", addEventListener() {} };
  const root = {
    querySelector: query => query.includes("yaml-textarea") ? textarea : panels[query.slice(1)] || null,
    querySelectorAll: () => tabs,
    addEventListener: (name, handler) => { handlers[name] = handler; }, getAttribute() {},
  };
  runInNewContext(source, { document: { querySelector: () => root, cookie: "" }, window: {} });
  handlers.click({ target: tabs[1], preventDefault() {} });
  assert.equal(panels.visualEditorPanel.hidden, true);
  assert.equal(panels.yamlEditorPanel.hidden, false);
  assert.equal(tabs[1].selected, "true");
  handlers.keydown({ target: tabs[1], key: "ArrowRight", preventDefault() {} });
  assert.equal(panels.visualEditorPanel.hidden, false);
  assert.equal(tabs[0].tabIndex, 0);
  assert.equal(tabs[0].focused, true);
  handlers.keydown({ target: tabs[0], key: "End", preventDefault() {} });
  assert.equal(panels.yamlEditorPanel.hidden, false);
  handlers.keydown({ target: tabs[1], key: "Home", preventDefault() {} });
  assert.equal(panels.visualEditorPanel.hidden, false);
  assert.equal(textarea.value, "unsaved YAML");
  const template = readFileSync(new URL("../../templates/report_v2/_editor_form.html", import.meta.url), "utf8");
  assert.match(template, /id="visualEditorTab" role="tab" aria-selected="true"/);
  assert.match(template, /id="yamlEditorPanel"[^>]* hidden>/);
  assert.ok(template.indexOf('id="visualEditorTab"') < template.indexOf('id="yamlEditorTab"'));
});
