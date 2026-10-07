import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { runInNewContext } from "node:vm";
import test from "node:test";

const source = readFileSync(new URL("../../static/report_v2/editor.js", import.meta.url), "utf8");
test("report selection uses the server editor URL on index and detail pages", () => {
  for (const pathname of ["/report/layout/", "/report/layout/editor/overview/"]) {
    let change, destination;
    const selector = { value: "", addEventListener: (_, handler) => { change = handler; } };
    const root = {
      querySelector: query => query.includes("report-select") ? selector : null,
      addEventListener() {},
      getAttribute: name => name === "data-editor-url" ? "/report/layout/" : null,
    };
    runInNewContext(source, {
      document: { querySelector: () => root },
      window: { location: { pathname, assign: url => { destination = url; } } },
    });
    for (const [id, expected] of [["showcase", "/report/layout/editor/showcase/"], ["new-report", "/report/layout/editor/new-report/"], ["", "/report/layout/"]]) {
      selector.value = id;
      change();
      assert.equal(destination, expected);
    }
  }
});
