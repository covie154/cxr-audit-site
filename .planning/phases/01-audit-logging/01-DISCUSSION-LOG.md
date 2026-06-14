# Phase 1: Audit Logging - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md - this log preserves the alternatives considered.

**Date:** 2026-06-14
**Phase:** 1-Audit Logging
**Areas discussed:** Event Detail Shape, LLM PHI Capture, Background Actor Attribution, Audit DB For Phase 1, Audit Coverage Strictness, Artifact Retention Boundary, User Selection Coverage, Audit Event Visibility, Audit Artifact Contents, PHI In Action Details, Audit Event Mutability, Cross-Service Audit Path

---

## Event Detail Shape

| Option | Description | Selected |
|--------|-------------|----------|
| String + structured metadata | Store a readable `action` string and a JSON metadata field for filters, date ranges, accession IDs, task IDs, filenames, counts. | yes |
| String only | Store everything in one readable final action string. | |
| Structured metadata only | Store JSON and generate readable text when displayed. | |

**User's choice:** String + structured metadata.
**Notes:** This supports both human review and future querying.

---

## LLM PHI Capture

| Option | Description | Selected |
|--------|-------------|----------|
| Safe metadata + hashes + result CSV only | Record task/batch/model/endpoint category/counts/timestamps, hash prompts/responses where available, save successful result CSV artifact, and avoid raw prompt/response artifacts in Phase 1. | yes |
| Full prompt/response artifacts | Save prompts and responses as encrypted or restricted audit artifacts. | |
| Metadata only | Record LLM call/success/failure metadata, but no prompt/response hashes. | |

**User's choice:** Safe metadata + hashes + successful result CSV only.
**Notes:** Raw prompt/response artifacts are deferred.

---

## Background Actor Attribution

| Option | Description | Selected |
|--------|-------------|----------|
| Both system actor and initiating user | Event actor is `system`, with initiating user metadata. | |
| Original user only | Attribute background events directly to the user who started the task. | yes |
| System only | Attribute background events to `system` and record task ID only. | |

**User's choice:** Original user only, but also record the task ID.
**Notes:** Metadata should still make asynchronous/background timing clear.

---

## Audit DB For Phase 1

| Option | Description | Selected |
|--------|-------------|----------|
| Second SQLite DB now, Postgres later | Add a separate audit SQLite file now, with settings structured for PostgreSQL later. | yes |
| Early PostgreSQL now | Add PostgreSQL service/config during Phase 1. | |
| Env-driven both now | Implement SQLite and PostgreSQL audit DB support in Phase 1. | |

**User's choice:** Second SQLite DB now, Postgres later.
**Notes:** This preserves the requested phase order.

---

## Audit Coverage Strictness

| Option | Description | Selected |
|--------|-------------|----------|
| Fail closed for high-risk actions only | Block high-risk actions if audit writing fails; allow low-risk navigation. | |
| Always fail closed | Any audited action fails if audit event cannot be written. | |
| Always continue | User workflow continues even if audit writing fails. | yes |

**User's choice:** Always continue.
**Notes:** Audit failures must not block clinical/audit workflows in Phase 1.

---

## Artifact Retention Boundary

| Option | Description | Selected |
|--------|-------------|----------|
| Configurable retention setting now | Add audit retention settings now; cleanup enforcement can come later. | yes |
| Indefinite retention for internal review | Keep all Phase 1 artifacts until manual cleanup. | |
| Implement cleanup now | Add a cleanup job or management command in Phase 1. | |

**User's choice:** Configurable retention setting now.
**Notes:** Cleanup enforcement can be deferred unless planning finds a low-risk natural implementation point.

---

## User Selection Coverage

| Option | Description | Selected |
|--------|-------------|----------|
| Specific ePHI-relevant interactions only | Log selected routes/buttons for meaningful ePHI interactions. | |
| Most authenticated GET/page interactions | Log nearly every authenticated page view. | yes |
| Only explicit button/form submissions | Log clicks/submissions, but not page/detail views. | |

**User's choice:** Most authenticated GET/page interactions.
**Notes:** Include full action details for routes, filters, date ranges, accession/task identifiers, and similar parameters.

---

## Audit Event Visibility

| Option | Description | Selected |
|--------|-------------|----------|
| Backend storage/tests only | No UI in Phase 1. | |
| Minimal read-only admin visibility | Register audit events in Django admin or add a simple read-only view. | yes |
| Full audit review UI | Search/filter/export audit logs in Phase 1. | |

**User's choice:** Minimal read-only admin visibility.
**Notes:** Full audit review UI remains v2 scope.

---

## Audit Artifact Contents

| Option | Description | Selected |
|--------|-------------|----------|
| Full uploaded file copy | Copy uploaded file bytes to the audit artifact directory with timestamp-prepended sanitized filename. | yes |
| Metadata/hash only | Store metadata and hash without duplicating file bytes. | |
| Configurable by environment | Default to full copy for internal review, allow metadata/hash-only mode. | |

**User's choice:** Full uploaded file copy.
**Notes:** This matches the earlier upload audit requirement.

---

## PHI In Action Details

| Option | Description | Selected |
|--------|-------------|----------|
| Avoid direct PHI in action details | Use IDs, filenames, counts, date ranges, filters, field names, hashes, and routes. | yes |
| Allow PHI when user input contains it | Include exact values such as patient names or report text when searched. | |
| Hash PHI-like values | Store hashes for patient names/report text but raw values for non-PHI filters. | |

**User's choice:** Avoid direct PHI in action details.
**Notes:** Patient names and raw report text should not be put in action strings or metadata.

---

## Audit Event Mutability

| Option | Description | Selected |
|--------|-------------|----------|
| Application-level append-only | No normal update/delete paths, read-only admin, tests around non-mutation. | yes |
| Application + SQLite trigger protections | Add triggers to block update/delete on audit tables. | |
| Document only | Treat append-only as a convention until PostgreSQL lands. | |

**User's choice:** Application-level append-only.
**Notes:** DB-level protections can be revisited with PostgreSQL.

---

## Cross-Service Audit Path

| Option | Description | Selected |
|--------|-------------|----------|
| Django-owned audit writes | Keep audit DB writes in Django and audit FastAPI/LLM through Django submission/result handling. | yes |
| FastAPI emits directly to audit DB | FastAPI writes audit events itself. | |
| FastAPI calls Django audit endpoint | Django remains audit owner, but FastAPI posts events to an internal endpoint. | |

**User's choice:** Django-owned audit writes.
**Notes:** Avoid coupling FastAPI directly to Django audit DB routing in Phase 1.

## the agent's Discretion

- Concrete module names, helper names, schema field names, and test layout are left to the planner/executor.

## Deferred Ideas

- Full audit review UI with search/filter/export.
- DB-level append-only enforcement after PostgreSQL support.
- Raw LLM prompt/response artifacts with explicit retention/access rules.
- Retention cleanup enforcement if it complicates Phase 1.
- FastAPI direct audit emission or FastAPI-to-Django audit endpoint after transmission security.
