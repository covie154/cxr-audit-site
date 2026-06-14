# Phase 1: Audit Logging - Context

**Gathered:** 2026-06-14
**Status:** Ready for planning

<domain>
## Phase Boundary

This phase delivers the audit logging subsystem and representative workflow coverage for ePHI-related actions. It includes separate audit storage, structured audit events, upload artifact capture, LLM call/success/failure audit categories, result CSV artifacts, application-level append-only behavior, minimal read-only audit visibility for internal review, and focused regression tests.

This phase does not deliver the full audit review UI, PostgreSQL migration, transmission security hardening, network segmentation, container minimization, or production-ready HIPAA operational evidence.

</domain>

<decisions>
## Implementation Decisions

### Event Detail Shape
- **D-01:** Each audit event must store both a human-readable final action string and structured metadata JSON.
- **D-02:** Structured metadata should capture material details such as routes, buttons, filters, date ranges, accession IDs, task IDs, filenames, counts, and artifact references.

### PHI Handling In Audit Details
- **D-03:** Audit action strings and metadata must avoid direct PHI such as patient names and raw report text.
- **D-04:** Use accession/task IDs, filenames, counts, date ranges, filter field names, hashes, and routes instead of patient names or raw report text.

### Audit Categories
- **D-05:** Phase 1 must support the audit categories `UserSelected`, `FileUpload`, `LLMCall`, `LLMSuccess`, and `LLMFailure`.
- **D-06:** `UserSelected` coverage should capture most authenticated GET/page interactions, with full action details for routes, filters, date ranges, accession/task identifiers, and similar parameters where present.

### Upload Audit Artifacts
- **D-07:** Uploaded files must be copied in full to the audit artifact directory.
- **D-08:** Uploaded artifact filenames must use a timestamp-prepended sanitized filename.
- **D-09:** Audit events for uploads must link to the captured artifact and include integrity metadata.

### LLM PHI Capture
- **D-10:** Phase 1 must preserve safe LLM metadata, prompt/response hashes where available, and successful result CSV artifacts only.
- **D-11:** Phase 1 must not store raw prompt or response artifacts. A later phase may add raw prompt/response artifacts only with explicit retention and access rules.
- **D-12:** Successful LLM batches must save result rows to a CSV audit artifact and link that artifact from the `LLMSuccess` audit event.

### Background Actor Attribution
- **D-13:** Background and LLM audit events should be attributed to the original initiating user where available.
- **D-14:** Background and LLM audit event metadata must record the task ID and make asynchronous/background timing clear.

### Audit Database
- **D-15:** Phase 1 should satisfy separate audit storage using a second SQLite database.
- **D-16:** Settings should be structured so Phase 5 can switch audit storage to PostgreSQL without redesign.

### Audit Failure Behavior
- **D-17:** Audit write failures must not block the clinical/audit user workflow in Phase 1.
- **D-18:** Audit failure telemetry should be recorded where possible, without creating recursive audit failures.

### Retention
- **D-19:** Add configurable retention settings now, such as audit event and audit artifact retention days.
- **D-20:** Cleanup enforcement can be deferred unless planning identifies a low-risk natural implementation point.

### Visibility And Mutability
- **D-21:** Add minimal read-only admin visibility for audit events so internal reviewers can confirm events without direct database access.
- **D-22:** Full audit search/filter/export UI remains v2 scope.
- **D-23:** Enforce append-only behavior at the application level in Phase 1: no normal update/delete paths, read-only admin visibility, and tests around non-mutation.
- **D-24:** DB-level append-only protections can be revisited when PostgreSQL support lands.

### Cross-Service Audit Path
- **D-25:** Keep audit DB writes owned by Django in Phase 1.
- **D-26:** Audit FastAPI and LLM activity from Django submission, status/result handling, result CSV capture, and task metadata rather than having FastAPI write directly to the audit database.

### the agent's Discretion
No areas were delegated fully to the agent. The planner may choose concrete module names, helper function names, schema field names, and test layout as long as the decisions above are honored and existing Django/FastAPI patterns are respected.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Planning And Requirements
- `.planning/PROJECT.md` - Project boundary, core value, constraints, and internal-review compliance bar.
- `.planning/REQUIREMENTS.md` - Phase 1 requirements `AUD-01` through `AUD-10`.
- `.planning/ROADMAP.md` - Phase 1 goal, success criteria, and plan breakdown.
- `.planning/STATE.md` - Current workflow position and project continuity state.

### Research
- `.planning/research/STACK.md` - Recommended audit stack, separate audit DB, artifact root, and transmission/security assumptions.
- `.planning/research/FEATURES.md` - Audit table stakes, differentiators, anti-features, and dependencies.
- `.planning/research/ARCHITECTURE.md` - Target audit subsystem, audit data flow, and suggested build order.
- `.planning/research/PITFALLS.md` - Audit-specific risks such as vague logs, PHI in ordinary logs, and same-DB audit storage.
- `.planning/research/SUMMARY.md` - Research summary and Phase 1 positioning.

### Codebase Map
- `.planning/codebase/ARCHITECTURE.md` - Existing Django/FastAPI/LLM request flow and persistence boundaries.
- `.planning/codebase/INTEGRATIONS.md` - Django-to-FastAPI calls, OpenAI-compatible endpoint config, upload/file integrations, and email integration.
- `.planning/codebase/CONCERNS.md` - Current audit logging gap and HIPAA-relevant security concerns.

### Source Specification
- `../Docs & Posters/HIPAA.md` - Original HIPAA technical safeguards spec sheet and audit-control intent.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `django-app/upload/models.py` - Existing `ProcessingTask` can carry task IDs and initiating-user attribution relationships if planner chooses to extend it.
- `django-app/upload/models.py` - Existing `UploadedFile` model shows local file tracking conventions, though main upload proxy currently forwards file bytes rather than persistently storing every upload in Django media.
- `django-app/lunit_audit/settings.py` - Existing single SQLite `DATABASES` config is the place to add a second audit DB alias, audit artifact root, retention settings, and a database router.

### Established Patterns
- Django apps are registered under `django-app/lunit_audit/settings.py`; a project-owned `audit` app is consistent with existing `upload`, `viewer`, `report`, and `gt` apps.
- Browser users are session-authenticated with `@login_required`; admin-only flows use the local `admin_required` wrapper in viewer code.
- Current logging is console-oriented. Audit logging should be a structured persistence path, not an extension of ordinary console logs.
- Current deployment uses SQLite locally/production-style; Phase 1 separate audit DB should use a second SQLite file, with environment-shaped settings for later PostgreSQL.

### Integration Points
- `django-app/upload/views.py::analyze_auto_sort` - File upload proxy for automatically sorted CARPL/RIS files; needs upload artifact capture, `FileUpload`, `LLMCall`, and initiating-user/task context.
- `django-app/upload/views.py::analyze_multiple` - File upload proxy for paired CARPL/RIS uploads; needs the same upload and LLM audit handling.
- `django-app/upload/views.py::get_status` and `get_results` - User-facing task status/result endpoints; useful for `UserSelected` and result-related audit events.
- `django-app/upload/views.py::_background_poll_and_save` and `_background_fetch_and_save` - Background result handling where asynchronous events need attribution to the initiating user and task ID.
- `django-app/upload/views.py::save_results_to_database` - Persistence point for FastAPI CSV results into `CXRStudy`; useful for successful result counts and `LLMSuccess` CSV artifact linkage.
- `django-app/viewer/views.py::index`, `study_detail`, `study_update`, `study_delete`, `bulk_delete`, and `export_csv` - High-value ePHI view/edit/delete/export audit points.
- `django-app/report/views.py::export_report_csv`, `export_false_negatives_csv`, `export_false_positives_csv`, `email_report`, and `download_pdf` - Report/export/email audit points.
- `django-app/gt/views.py::download_reports`, `validate_upload`, and `apply_gt` - Manual GT download/upload/update audit points.
- `cxr-audit-api/cxr_audit/grade_batch_async.py::BatchCXRProcessor` - LLM batch processing path. Phase 1 should audit this indirectly through Django-owned submission/result handling rather than direct FastAPI audit DB writes.
- `cxr-audit-api/cxr_audit/lib_audit_cxr_v2.py::CXRClassifier` - OpenAI-compatible LLM call wrapper. Raw prompt/response artifacts are out of Phase 1, but prompt/response hashes may be captured where available through Django-owned result metadata.

</code_context>

<specifics>
## Specific Ideas

- Use readable action strings for human review while keeping structured metadata JSON for future querying and verification.
- Avoid raw PHI in audit rows even when users search by patient name or report text; prefer route, field name, hash, count, accession/task ID, or date range.
- Internal review should be possible through minimal read-only Django admin visibility rather than direct database inspection.
- Audit failure handling should favor availability in Phase 1: user workflows continue even if audit writes fail.

</specifics>

<deferred>
## Deferred Ideas

- Full audit review UI with search/filter/export remains v2 scope.
- DB-level append-only enforcement should be reconsidered after PostgreSQL support exists.
- Raw LLM prompt/response artifact retention requires a later explicit retention and access-control decision.
- Cleanup enforcement for retention settings may be deferred if it would complicate Phase 1.
- FastAPI direct audit emission or a FastAPI-to-Django audit endpoint can be reconsidered after transmission security is implemented.

</deferred>

---

*Phase: 1-Audit Logging*
*Context gathered: 2026-06-14*
