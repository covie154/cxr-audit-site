# Pitfalls Research: PRIMER-LLM HIPAA Compliance

**Researched:** 2026-06-14

## 1. Audit Logs That Are Too Vague

**Warning signs:**

- Events say only "viewed page" or "clicked button".
- Date ranges, filters, export types, task IDs, or accession identifiers are omitted.
- LLM batch completion is logged without the output artifact.

**Prevention:**

- Make `category` and `action_detail` required.
- Add tests for final action strings on representative clicks, date filters, uploads, exports, and LLM batches.
- Define helper functions for action detail formatting instead of hand-rolled strings in every view.

**Phase:** Audit logging.

## 2. Audit Logs Stored Beside Mutable Production Data

**Warning signs:**

- Audit events use the default database.
- Normal admin/edit code can update or delete audit rows.
- Audit artifacts are stored in the same media tree as ordinary user files.

**Prevention:**

- Use a separate `audit` database alias and database router.
- Restrict audit model admin capabilities or omit admin mutation views.
- Store artifacts under a dedicated audit artifact root.

**Phase:** Audit logging and PostgreSQL support.

## 3. Capturing PHI In The Wrong Log

**Warning signs:**

- Raw report text appears in console logs, Nginx logs, Docker logs, or exception traces.
- LLM prompts/responses are logged to stdout.
- Audit artifact paths expose patient identifiers in filenames.

**Prevention:**

- Sanitize artifact filenames.
- Store hashes and controlled artifact links in audit events.
- Keep PHI-bearing artifacts in the audit artifact root, not ordinary logs.

**Phase:** Audit logging.

## 4. Service Authentication That Fails Open

**Warning signs:**

- FastAPI accepts missing `API_SECRET_KEY` in production.
- Compose examples set secrets to `dummy` or `changeme`.
- Tests only cover development mode.

**Prevention:**

- Add explicit production-mode validation.
- Test production missing-secret failures.
- Keep development bypasses separate and obvious.

**Phase:** Transmission security.

## 5. Internal TLS Before Operational Readiness

**Warning signs:**

- mTLS is added without certificate rotation, expiry alerting, trust-store documentation, or recovery steps.
- Developers bypass TLS locally because it is hard to debug.

**Prevention:**

- Implement service secrets and network segmentation first.
- Document mTLS as a production-hardening upgrade with concrete prerequisites.

**Phase:** Transmission security and remaining controls doc.

## 6. Segmentation That Breaks Workflows

**Warning signs:**

- Django can no longer reach FastAPI.
- Healthchecks fail because they run on the wrong network.
- Databases are accidentally exposed to Nginx or host ports.

**Prevention:**

- Define intended traffic flows before editing Compose.
- Verify container DNS names after network changes.
- Add smoke tests or documented manual checks for the upload-to-analysis path.

**Phase:** Network segmentation.

## 7. Read-Only Filesystems Without Writable Paths

**Warning signs:**

- Static collection, temp uploads, Python caches, or generated CSVs fail at runtime.
- Containers are made read-only before temp and media paths are mapped.

**Prevention:**

- Inventory write paths before enabling `read_only`.
- Add explicit `tmpfs` and volume mounts.
- Stage hardening so non-root and capability drops happen before full read-only roots if needed.

**Phase:** Removal of extraneous software.

## 8. PostgreSQL Migration Without Rehearsal

**Warning signs:**

- The plan jumps directly from SQLite to production cutover.
- Validation checks compare only row counts.
- Rollback and backups are undocumented.

**Prevention:**

- Rehearse with synthetic data first.
- Validate counts, schema, key fields, representative reports, and admin/report UI behavior.
- Document backup, restore, rollback, and cutover windows.

**Phase:** PostgreSQL support and migration plan.

## 9. Overclaiming HIPAA Compliance

**Warning signs:**

- Documentation says the app is HIPAA compliant because technical controls were added.
- Administrative safeguards, risk analysis, BAAs, training, incident response, and physical safeguards are ignored.

**Prevention:**

- Phrase the milestone as technical control implementation toward HIPAA compliance.
- Track non-code and operational prerequisites in the remaining controls document.

**Phase:** Remaining controls doc.
