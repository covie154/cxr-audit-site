/*
 * Classic module entry for report pages: registers the seven shipped renderers with the registry
 * and flags the host global ready. registry.mjs already mirrors the api onto window.__rv2widgets;
 * boot only adds the idempotent registrations (registry.renderers is a Map) plus the bootReady flag
 * report.js reads before it takes the registry path. No DOM APIs besides window; no inner*HTML, no
 * storage API, no network here.
 */
import { register } from "./registry.mjs";
import * as valueRenderer from "./value.mjs";
import * as tableRenderer from "./table.mjs";
import * as lineRenderer from "./line.mjs";
import * as barRenderer from "./bar.mjs";
import * as pieRenderer from "./pie.mjs";
import * as confusionRenderer from "./confusion.mjs";
import * as boxplotRenderer from "./boxplot.mjs";

register("value", valueRenderer);
register("table", tableRenderer);
register("line", lineRenderer);
register("bar", barRenderer);
register("pie", pieRenderer);
register("confusion_matrix", confusionRenderer);
register("boxplot", boxplotRenderer);

if (typeof globalThis.window !== "undefined") {
    globalThis.window.__rv2widgets = globalThis.window.__rv2widgets || {};
    globalThis.window.__rv2widgets.bootReady = true;
}
