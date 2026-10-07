/* PRIMER - LLM-based Chest X-Ray Audit Tool
   Copyright (C) 2026 Goh Shu Wen
   Licensed under AGPL-3.0-or-later. See LICENSE at the repository root. */
/* report_v2 admin layout editor: framework-free, no CDN, shared YAML draft and visual layout editing.
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
  var previewDialog = root.querySelector('[data-role="preview-dialog"]');
  var validationCallout = root.querySelector('[data-role="validation-callout"]');
  var validationSummary = root.querySelector('[data-role="validation-summary"]');
  var newNameInput = root.querySelector('[data-role="new-report-name"]');
  var createDialog = root.querySelector('[data-role="create-dialog"]');
  var createForm = root.querySelector('[data-role="create-form"]');
  var templateSelect = root.querySelector('[data-role="starter-template"]');
  var deleteDialog = root.querySelector('[data-role="delete-dialog"]');
  var deleting = null;
  var deleteConfirmation = root.querySelector('[data-role="delete-confirmation"]');
  var cardSelect = root.querySelector('[data-role="preview-card"]');
  var cardTimer;
  var cardRequest = 0;

  var savedText = textarea ? textarea.value : "";
  var savedRevision = revisionNode ? revisionNode.getAttribute("data-revision") || "" : "";
  var dirty = false;
  var disposePreview = null;
  var previewRequest = 0;
  var activePreviewYaml = null;

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
      dirtyNode.textContent = dirty ? "Unsaved changes. Save to keep them." : "No unsaved changes.";
    }
  }

  function showErrors(messages) {
    var items = messages || [];
    if (validationSummary) { validationSummary.textContent = items.length ? items.length + " validation issue" + (items.length === 1 ? "" : "s") : "No errors"; }
    if (validationCallout) { validationCallout.open = items.length > 0; }
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
    var fields = new URLSearchParams();
    function add(key, value) {
      fields.set(key, value === null || value === undefined ? "" : value);
    }
    add("def_id", root.getAttribute("data-def-id") || "");
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
    return fields.toString();
  }

  function post(url, extra, signal) {
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
      body: body(extra),
      signal: signal
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
      if (textarea && textarea.value === submittedText && data.yaml_text) {
        textarea.value = data.yaml_text;
        submittedText = data.yaml_text;
        textarea.dispatchEvent(new Event("input", { bubbles: true }));
      }
      savedText = submittedText;
      var publication = root.querySelector('[data-action="publish"]');
      if (publication && data.published_version) { publication.setAttribute("data-version", data.published_version); }
      setRevision(data.revision);
      setDirty(textarea && textarea.value !== savedText);
      if (!textarea || textarea.value === submittedText) { showErrors(data.errors || []); }
      if (dirtyNode && !dirty && data.published) { dirtyNode.textContent = "Saved and published."; }
    });
  }

  function preview(extra) {
    var requestId = ++previewRequest;
    if (previewDialog && !previewDialog.open) { previewDialog.showModal(); }
    if (disposePreview) { disposePreview(); disposePreview = null; }
    var previewYaml = extra && extra.yaml_text !== undefined ? extra.yaml_text : (textarea ? textarea.value : "");
    activePreviewYaml = previewYaml;
    var previewWidget = extra && extra.widget_id !== undefined ? extra.widget_id : (cardSelect ? cardSelect.value : "");
    if (cardSelect && previewWidget) { cardSelect.value = previewWidget; }
    fill(previewOut, "Loading preview…");
    showConflict(false);
    return post(root.getAttribute("data-preview-url"), extra && (extra.yaml_text !== undefined || extra.widget_id !== undefined) ? extra : null).then(function (result) {
      if (requestId !== previewRequest) { return; }
      var data = result.data;
      if (cardSelect && data.widgets) {
        cardSelect.innerHTML = "";
        data.widgets.forEach(function (widget) {
          var option = document.createElement("option");
          option.value = widget.id; option.textContent = widget.title;
          cardSelect.appendChild(option);
        });
        previewWidget = data.widget_id || previewWidget;
        cardSelect.value = previewWidget;
      }
      showErrors(data.errors || (data.error ? [data.error] : []));
      if (!previewOut) {
        return;
      }
      if (data.card_html && window.__rv2initializeReport) {
        previewOut.style.setProperty("--report-row-height", data.row_height_px + "px");
        previewOut.innerHTML = data.card_html;
        disposePreview = window.__rv2initializeReport(previewOut, function (url, options) {
          return post(url, {
            yaml_text: previewYaml, widget_id: previewWidget,
            overrides: options.body
          }, options.signal).then(function (result) {
            var response = result.data;
            return { ok: result.status < 400 && !response.preview_error && response.valid,
              status: result.status,
              json: function () { return Promise.resolve(response.preview || {
                error: response.preview_error || response.error || (response.errors || []).join("; ")
              }); }
            };
          });
        });
      } else {
        fill(previewOut, data.preview_error || (data.errors || []).join("; ") || "Nothing to preview yet.");
      }
    });
  }

  function publish(trigger) {
    showConflict(false);
    var version = trigger.getAttribute("data-version") || "";
    var label = version ? "Unpublish" : "Publish";
    var extra = { expected_version: version };
    if (trigger.getAttribute("data-def-id")) {
      extra.def_id = trigger.getAttribute("data-def-id");
      extra.expected_revision = trigger.getAttribute("data-revision");
    }
    trigger.disabled = true;
    trigger.textContent = version ? "Unpublishing…" : "Publishing…";
    return post(root.getAttribute(version ? "data-unpublish-url" : "data-publish-url"), extra).then(function (result) {
      if (result.status >= 400) {
        showConflict(result.status === 409);
        showErrors(result.data.errors || [result.data.error || "Publication could not be changed."]);
        return;
      }
      if (version) {
        if (!textarea) { window.location.reload(); }
        else {
          trigger.setAttribute("data-version", ""); label = "Publish";
          var view = root.querySelector('[data-role="view-report"]');
          var disabledView = document.createElement("button");
          disabledView.type = "button"; disabledView.className = view.className;
          disabledView.setAttribute("data-role", "view-report"); disabledView.textContent = "View report";
          disabledView.disabled = true; view.replaceWith(disabledView);
        }
      }
      else { setDirty(false); window.location.assign(result.data.url); }
    }).catch(function () {
      showErrors(["Publication could not be changed. Try again."]);
    }).finally(function () { trigger.disabled = false; trigger.textContent = label; });
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
      showErrors(result.data.errors || (result.data.error ? [result.data.error] : []));
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
    if (!deleting || !deleteConfirmation || deleteConfirmation.value !== "delete this report") { return; }
    var button = root.querySelector('[data-action="confirm-delete"]');
    button.disabled = true;
    return post(root.getAttribute("data-delete-url"), {
      def_id: deleting.getAttribute("data-def-id"),
      expected_revision: deleting.getAttribute("data-revision"),
      expected_version: deleting.getAttribute("data-version"),
      confirmation: deleteConfirmation.value
    }).then(function (result) {
      if (result.status >= 400) {
        deleteDialog.close();
        showErrors([result.data.error || "The report could not be deleted."]);
      } else { window.location.reload(); }
    }).catch(function () {
      deleteDialog.close();
      showErrors(["The report could not be deleted. Try again."]);
    }).finally(function () { button.disabled = deleteConfirmation.value !== "delete this report"; });
  }

  function selectEditorTab(tab) {
    root.querySelectorAll('[role="tab"]').forEach(function (item) {
      var selected = item === tab;
      item.setAttribute("aria-selected", String(selected));
      item.tabIndex = selected ? 0 : -1;
      root.querySelector("#" + item.getAttribute("aria-controls")).hidden = !selected;
    });
  }

  root.addEventListener("keydown", function (event) {
    var tab = event.target.closest('[role="tab"]');
    if (!tab) { return; }
    var tabs = Array.from(root.querySelectorAll('[role="tab"]'));
    var index = tabs.indexOf(tab);
    if (event.key === "ArrowRight") { index = (index + 1) % tabs.length; }
    else if (event.key === "ArrowLeft") { index = (index + tabs.length - 1) % tabs.length; }
    else if (event.key === "Home") { index = 0; }
    else if (event.key === "End") { index = tabs.length - 1; }
    else { return; }
    event.preventDefault();
    selectEditorTab(tabs[index]);
    tabs[index].focus();
  });

  if (textarea) {
    textarea.addEventListener("input", function () {
      setDirty(textarea.value !== savedText);
      clearTimeout(cardTimer);
      ++cardRequest;
      if (validationSummary) { validationSummary.textContent = "Checking YAML…"; }
      cardTimer = setTimeout(refreshCards, 400);
    });
  }

  root.addEventListener("click", function (event) {
    var trigger = event.target && event.target.closest ? event.target.closest("[data-action]") : null;
    if (!trigger) {
      return;
    }
    if (trigger.closest && trigger.closest(".widget-frame")) { return; }
    var action = trigger.getAttribute("data-action");
    event.preventDefault();
    if (action === "editor-tab") {
      selectEditorTab(trigger);
    } else if (action === "save") {
      save();
    } else if (action === "preview") {
      preview();
    } else if (action === "close-preview") {
      ++previewRequest;
      if (disposePreview) { disposePreview(); disposePreview = null; }
      previewDialog.close();
      activePreviewYaml = null;
    } else if (action === "publish") {
      publish(trigger);
    } else if (action === "create") {
      if (!dirty || window.confirm("Leave this report with unsaved changes?")) { createDialog.showModal(); }
    } else if (action === "cancel-create") {
      createDialog.close();
    } else if (action === "delete") {
      deleting = trigger;
      root.querySelector('[data-role="delete-name"]').textContent = trigger.getAttribute("data-title");
      deleteConfirmation.value = "";
      root.querySelector('[data-action="confirm-delete"]').disabled = true;
      deleteDialog.showModal();
      deleteConfirmation.focus();
    } else if (action === "cancel-delete") {
      deleteDialog.close();
    } else if (action === "confirm-delete") {
      deleteReport();

    }
  });

  if (deleteConfirmation) {
    deleteConfirmation.addEventListener("input", function () {
      root.querySelector('[data-action="confirm-delete"]').disabled = deleteConfirmation.value !== "delete this report";
    });
  }
  if (cardSelect) { cardSelect.addEventListener("change", function () { return preview({ yaml_text: activePreviewYaml !== null ? activePreviewYaml : (textarea ? textarea.value : ""), widget_id: cardSelect.value }); }); }
  if (createForm) {
    createForm.addEventListener("submit", function (event) { event.preventDefault(); createReport(); });
  }
  if (window.PrimerVisualEditor) { window.PrimerVisualEditor(root, { post: post, preview: preview }); }
  setDirty(false);
  if (textarea && cardSelect) { refreshCards(); }
})();
