/* Copyright (C) 2026 Goh Shu Wen. AGPL-3.0-or-later. See LICENSE. */
import { el, clearContainer } from "./registry.mjs";

export function render(container, payload) {
    clearContainer(container);
    if (payload.static_type === "divider") { container.appendChild(el("hr")); }
    else { container.appendChild(el("p", "widget-static-text", payload.text || "")); }
    return { container, resize() {}, dispose() {} };
}
