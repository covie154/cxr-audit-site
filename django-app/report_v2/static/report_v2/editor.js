/* PRIMER - LLM-based Chest X-Ray Audit Tool
   Copyright (C) 2026 Goh Shu Wen
   Licensed under AGPL-3.0-or-later. See LICENSE at the repository root. */
/* report_v2 admin layout editor: framework-free, no CDN, no pointer-reordering editing.
 *
 * The whole job of this script is (a) track a dirty flag against the last saved revision and (b) POST the
 * YAML to the four admin endpoints carrying the CSRF token the server set. Publishing happens only on
 * an explicit Publish click; there is no automatic publish and there are no pointer-reordering handlers here.
 */
(function () {
  "use strict";

  var root = document.querySelector("[data-editor]");
  if (!root) {
    return;
  }

  var textarea = root.querySelector('[data-role="yaml-textarea"]');
  var revisionNode = root.querySelector('[data-role="revision-indicator"]');
  var dirtyNode = root.querySelector('[data-role="dirty-indicator"]');
  var conflictNode = root.querySelector('[data-role="conflict-indicator"]');
  var errorList = root.querySelector('[data-role="error-list"]');
  var errorsEmpty = root.querySelector('[data-role="errors-empty"]');
  var previewOut = root.querySelector('[data-role="preview-output"]');
  var selector = root.querySelector('[data-role="report-select"]');
  var newNameInput = root.querySelector('[data-role="new-report-name"]');
  var createDialog = root.querySelector('[data-role="create-dialog"]');
  var createForm = root.querySelector('[data-role="create-form"]');
  var templateSelect = root.querySelector('[data-role="starter-template"]');
  var deleteDialog = root.querySelector('[data-role="delete-dialog"]');
  var deleting = null;
  var cardSelect = root.querySelector('[data-role="preview-card"]');
  var cardTimer;
  var cardRequest = 0;

  var savedText = textarea ? textarea.value : "";
  var savedRevision = revisionNode ? revisionNode.getAttribute("data-revision") || "" : "";
  var dirty = false;
  var previewInstance = null;

  function token() {
    var parts = (document.cookie || "").split(";");
    for (var i = 0; i < parts.length; i += 1) {
      var pair = parts[i].trim();
      if (pair.indexOf("csrftoken=") === 0) {
        return decodeURIComponent(pair.substring("csrftoken=".length));
      }
    }
    return "";
  }

  function setDirty(flag) {
    dirty = Boolean(flag);
    if (dirtyNode) {
      dirtyNode.setAttribute("data-dirty", dirty ? "true" : "false");
      dirtyNode.textContent = dirty ? "Unsaved changes. Save draft to keep them." : "No unsaved changes.";
    }
  }

  function showErrors(messages) {
    var items = messages || [];
    if (errorList) {
      errorList.innerHTML = "";
      for (var i = 0; i < items.length; i += 1) {
        var li = document.createElement("li");
        li.className = "editor-error";
        li.textContent = String(items[i]);
        errorList.appendChild(li);
      }
    }
    if (errorsEmpty) {
      errorsEmpty.hidden = items.length > 0;
      errorsEmpty.textContent = items.length ? "" : "No validation errors.";
    }
  }

  function showConflict(active) {
    if (conflictNode) {
      conflictNode.hidden = !active;
    }
  }

  function setRevision(value) {
    savedRevision = value || savedRevision;
    if (revisionNode) {
      revisionNode.setAttribute("data-revision", savedRevision);
      revisionNode.textContent = "Revision: " + (savedRevision || "(no draft yet)") + " (Draft)";
      revisionNode.setAttribute("data-source-state", "draft");
    }
  }

  function fill(node, text) {
    if (!node) {
      return;
    }
    node.innerHTML = "";
    var para = document.createElement("p");
    para.className = "editor-empty";
    para.textContent = text;
    node.appendChild(para);
  }

  function body(extra) {
    var fields = [];
    function add(key, value) {
      fields.push(encodeURIComponent(key) + "=" + encodeURIComponent(value === null || value === undefined ? "" : value));
    }
    add("def_id", selector ? selector.value : (root.getAttribute("data-def-id") || ""));
    add("yaml_text", textarea ? textarea.value : "");
    add("expected_revision", savedRevision);
    if (cardSelect) { add("widget_id", cardSelect.value); }
    add("csrfmiddlewaretoken", token());
    if (extra) {
      for (var key in extra) {
        if (Object.prototype.hasOwnProperty.call(extra, key)) {
          add(key, extra[key]);
        }
      }
    }
    return fields.join("&");
  }

  function post(url, extra) {
    if (!url) {
      return Promise.resolve();
    }
    return fetch(url, {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/x-www-form-urlencoded; charset=utf-8",
        "X-CSRFToken": token()
      },
      body: body(extra)
    }).then(function (response) {
      return response.json().catch(function () {
        return {};
      }).then(function (data) {
        return { status: response.status, data: data || {} };
      });
    });
  }

  function save() {
    showConflict(false);
    var submittedText = textarea ? textarea.value : "";
    return post(root.getAttribute("data-save-url")).then(function (result) {
      var data = result.data;
      if (result.status === 409) {
        showConflict(true);
        setDirty(true);
        showErrors([data.error || "version conflict: reload"]);
        return;
      }
      if (result.status >= 400) {
        showErrors([data.error || "the draft could not be saved"]);
        return;
      }
      savedText = submittedText;
      setRevision(data.revision);
      setDirty(textarea && textarea.value !== savedText);
      showErrors([]);
    });
  }

  function preview() {
    showConflict(false);
    return post(root.getAttribute("data-preview-url")).then(function (result) {
      var data = result.data;
      showErrors(data.errors || (data.error ? [data.error] : []));
      if (!previewOut) {
        return;
      }
      if (previewInstance && window.__rv2widgets) {
        window.__rv2widgets.registry.disposeInstance(previewInstance);
        previewInstance = null;
      }
      if (data.preview && window.__rv2widgets && window.__rv2widgets.bootReady) {
        previewOut.innerHTML = "";
        var title = document.createElement("h3");
        title.textContent = data.widget.title || data.widget.id;
        var mount = document.createElement("div");
        mount.className = "widget-body";
        previewOut.appendChild(title);
        previewOut.appendChild(mount);
        try {
          previewInstance = window.__rv2widgets.registry.render(data.widget.type, mount, data.preview, {
            measurement: data.widget.query.measurement,
            primaryOnly: data.widget.type === "value",
            columns: data.widget.columns,
            benchmarks: data.widget.benchmarks
          });
          var counts = data.preview.counts || {};
          var summary = document.createElement("p");
          summary.className = "editor-help";
          summary.textContent = (counts.matching || 0) + " matching records · " + (counts.eligible || 0) + " eligible";
          previewOut.appendChild(summary);
        } catch (error) {
          fill(previewOut, "Preview could not render. Reload and try again.");
        }
      } else {
        fill(previewOut, data.preview_error || "Nothing to preview yet.");
      }
    });
  }

  function publish() {
    showConflict(false);
    return post(root.getAttribute("data-publish-url")).then(function (result) {
      var data = result.data;
      if (result.status === 409) {
        showConflict(true);
        showErrors([data.error || "version conflict: reload"]);
        return;
      }
      if (result.status >= 400) {
        // Rejected publish: the previously published pointer stays where it is (server-side guarantee).
        showErrors(data.errors || [data.error || "publish rejected"]);
        return;
      }
      setDirty(textarea && textarea.value !== savedText);
      showErrors([]);
      fill(previewOut, "Published " + (data.version || "") + ".");
    });
  }

  function createReport() {
    if (!newNameInput || !newNameInput.value.trim()) { return; }
    var submit = createForm.querySelector('[type="submit"]');
    submit.disabled = true;
    return post(root.getAttribute("data-new-url"), {
      name: newNameInput.value.trim(), template: templateSelect ? templateSelect.value : "blank"
    }).then(function (result) {
      if (result.status >= 400) {
        createDialog.close();
        showErrors([result.data.error || "The report could not be created."]);
      } else {
        window.location.assign(result.data.url);
      }
    }).catch(function () {
      createDialog.close();
      showErrors(["The report could not be created. Try again."]);
    }).finally(function () { submit.disabled = false; });
  }

  function refreshCards() {
    if (!cardSelect || !textarea) { return; }
    var requestId = ++cardRequest;
    return post(root.getAttribute("data-preview-url"), { list_only: "1" }).then(function (result) {
      if (requestId !== cardRequest) { return; }
      var previous = cardSelect.value;
      cardSelect.innerHTML = "";
      (result.data.widgets || []).forEach(function (widget) {
        var option = document.createElement("option");
        option.value = widget.id;
        option.textContent = widget.title;
        cardSelect.appendChild(option);
      });
      if (!cardSelect.options.length) {
        var empty = document.createElement("option");
        empty.value = "";
        empty.textContent = result.data.valid ? "No cards yet" : "Fix YAML to select cards";
        cardSelect.appendChild(empty);
      } else if (Array.from(cardSelect.options).some(function (option) { return option.value === previous; })) {
        cardSelect.value = previous;
      }
    }).catch(function () { showErrors(["Card list could not load. Try Preview again."]); });
  }

  function deleteReport() {
    if (!deleting) { return; }
    var button = root.querySelector('[data-action="confirm-delete"]');
    button.disabled = true;
    return post(root.getAttribute("data-delete-url"), {
      def_id: deleting.getAttribute("data-def-id"),
      expected_revision: deleting.getAttribute("data-revision"),
      expected_version: deleting.getAttribute("data-version")
    }).then(function (result) {
      if (result.status >= 400) {
        deleteDialog.close();
        showErrors([result.data.error || "The report could not be deleted."]);
      } else { window.location.reload(); }
    }).catch(function () {
      deleteDialog.close();
      showErrors(["The report could not be deleted. Try again."]);
    }).finally(function () { button.disabled = false; });
  }

  function renderSeedResult(result) {
    if (!result) {
      return;
    }
    var data = result.data || {};
    if (result.status >= 400) {
      // Rejected/failed seed: list the violations through the shared, textContent-safe error renderer.
      showErrors(data.errors || [data.error || "the seed could not be loaded"]);
      return;
    }
    showErrors(data.errors || []);
    if (data.status === "seeded") {
      window.location.reload();
      return;
    }
    if (previewOut) {
      // No raw server text is ever injected as HTML; fill() writes a textContent-only <p>.
      var label = data.status === "checked" ? "Seed validated (nothing written)." : "Seed drafts loaded.";
      fill(previewOut, data.def_id ? label + " " + data.def_id : label);
    }
  }

  function seedLoad(dry) {
    // The shared body() helper already carries def_id + expected_revision + csrfmiddlewaretoken; only the
    // dry_run flag is added here, so both seed actions reuse the exact same signed form encoding.
    return post(root.getAttribute(dry ? "data-seed-check-url" : "data-seed-load-url"), {
      dry_run: dry ? "1" : "0"
    }).then(renderSeedResult);
  }

  if (textarea) {
    textarea.addEventListener("input", function () {
      setDirty(textarea.value !== savedText);
      clearTimeout(cardTimer);
      ++cardRequest;
      cardTimer = setTimeout(refreshCards, 400);
    });
  }

  root.addEventListener("click", function (event) {
    var trigger = event.target && event.target.closest ? event.target.closest("[data-action]") : null;
    if (!trigger) {
      return;
    }
    var action = trigger.getAttribute("data-action");
    event.preventDefault();
    if (action === "save") {
      save();
    } else if (action === "preview") {
      preview();
    } else if (action === "publish") {
      publish();
    } else if (action === "create") {
      if (!dirty || window.confirm("Leave this report with unsaved changes?")) { createDialog.showModal(); }
    } else if (action === "cancel-create") {
      createDialog.close();
    } else if (action === "delete") {
      deleting = trigger;
      root.querySelector('[data-role="delete-name"]').textContent = trigger.getAttribute("data-title");
      deleteDialog.showModal();
    } else if (action === "cancel-delete") {
      deleteDialog.close();
    } else if (action === "confirm-delete") {
      deleteReport();
    } else if (action === "seed-check") {
      seedLoad(true);
    } else if (action === "seed-load") {
      seedLoad(false);
    }
  });

  if (createForm) {
    createForm.addEventListener("submit", function (event) { event.preventDefault(); createReport(); });
  }
  if (selector) {
    selector.addEventListener("change", function () {
      if (dirty && !window.confirm("Leave this report with unsaved changes?")) {
        selector.value = root.getAttribute("data-def-id") || "";
        return;
      }
      window.location.assign(root.getAttribute("data-editor-url") + (selector.value ? "editor/" + encodeURIComponent(selector.value) + "/" : ""));
    });
  }

  setDirty(false);
})();
