import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { runInNewContext } from "node:vm";
import test from "node:test";

const source = readFileSync(new URL("../../static/report_v2/editor.js", import.meta.url), "utf8");
test("saving uses the report ID from the editor route without a report selector", async () => {
  let click, posted;
  const textarea = { value: "schema_version: 1", addEventListener() {} };
  const root = {
    querySelector: query => query.includes("yaml-textarea") ? textarea : null,
    addEventListener: (name, handler) => { if (name === "click") click = handler; },
    getAttribute: name => ({ "data-def-id": "my_report", "data-save-url": "/layout/actions/save/" })[name],
  };
  runInNewContext(source, {
    document: { querySelector: () => root, cookie: "" }, window: {},
    fetch: async (url, options) => { posted = { url, body: options.body }; return { status: 200, json: async () => ({ revision: "saved" }) }; },
  });
  click({ target: { closest: () => ({ getAttribute: () => "save" }) }, preventDefault() {} });
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(posted.url, "/layout/actions/save/");
  assert.equal(new URLSearchParams(posted.body).get("def_id"), "my_report");
});
