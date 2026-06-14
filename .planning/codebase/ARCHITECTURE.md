---
mapped_at: 2026-06-14
focus: arch
---

# Codebase Architecture

## System Shape

PRIMER-LLM is a three-tier web application with a separate analysis API and an external LLM inference service.

Request flow:

1. Browser connects to Nginx in `nginx/nginx.conf`.
2. Nginx terminates TLS and proxies to Django/Gunicorn.
3. Django handles authentication, upload UI, database browsing, reports, and manual GT workflows.
4. Django proxies analysis submissions to FastAPI in `cxr-audit-api/combined_server.py`.
5. FastAPI runs the CARPL/RIS merge and LLM grading pipeline.
6. FastAPI calls an OpenAI-compatible inference endpoint through `cxr-audit-api/cxr_audit/lib_audit_cxr_v2.py`.
7. Django background polling fetches completed results and persists them to `CXRStudy`.

## Django Layers

The Django project is in `django-app/lunit_audit/`.

Installed local apps:

- `upload`: main file upload, task tracking, FastAPI proxy, historical CSV import.
- `viewer`: admin-only database browser, inline edits, detail view, CSV export, deletion.
- `report`: report generation, metrics, CSV exports, email report, print/PDF HTML.
- `gt`: manual ground truth sample download and label upload.

URL routing starts in `django-app/lunit_audit/urls.py` and includes app URL modules for `/upload/`, `/view/`, `/report/`, and `/gt/`.

## Data Model

The core table is `CXRStudy` in `django-app/upload/models.py`.

`CXRStudy` uses `accession_no` as the primary key and stores:

- Patient identifiers and demographics.
- Study identifiers and procedure timing.
- Lunit score columns.
- Radiologist report text.
- LLM grading output.
- Manual ground truth.
- Supplemental LLM findings.
- Processing metadata.

`ProcessingTask` tracks API jobs and stores progress plus output payloads such as `txt_report`, `csv_data`, and false negatives JSON.

`UploadedFile` tracks task-associated files, but the main upload proxy mostly forwards file bytes to FastAPI rather than storing every upload in Django media.

## Background Processing

Django uses raw daemon threads in `django-app/upload/views.py`.

- `_start_background_worker()` starts one background polling thread per active task.
- `_background_poll_and_save()` polls FastAPI `/status/{task_id}`.
- `_background_fetch_and_save()` fetches results from `/results/{task_id}` and calls `save_results_to_database()`.

This is simple but process-local. With multiple Gunicorn workers, background task ownership and active task state are not globally coordinated.

## FastAPI Pipeline

`cxr-audit-api/combined_server.py` owns the HTTP API and an in-memory `processing_results` dictionary.

Important endpoints:

- `/analyze`
- `/analyze-multiple`
- `/analyze-auto-sort`
- `/status/{task_id}`
- `/results/{task_id}`
- `/tasks`
- `/tasks/{task_id}`

File sorting and validation happen in `sort_files_async()`. Actual analysis happens in `process_files_sync()`, which creates `ProcessCarpl` from `cxr-audit-api/class_process_carpl.py`.

`ProcessCarpl` loads CARPL and GE/RIS files, merges by accession number, computes Lunit binary outputs, invokes LLM grading, calculates metrics, identifies false negatives, and rearranges output columns.

## LLM Processing

`BatchCXRProcessor` in `cxr-audit-api/cxr_audit/grade_batch_async.py` performs concurrent report processing with `ThreadPoolExecutor`.

`CXRClassifier` in `cxr-audit-api/cxr_audit/lib_audit_cxr_v2.py` provides:

- Semi-algorithmic extraction and priority scoring.
- Direct LLM grading.
- Hybrid grading.
- LLM-as-judge grading.
- Supplemental Lunit-compatible findings extraction.

Prompts live in `cxr-audit-api/cxr_audit/prompts.py`.

## Persistence Boundaries

Current durable state:

- SQLite database in `django-app/db/db.sqlite3`, mounted as `django-db`.
- Django media in the `django-media` volume.
- Generated static files in container filesystem.

Current volatile state:

- FastAPI `processing_results` dictionary in process memory.
- Temporary uploaded files in OS temp directories during analysis.
- Django background thread state in process memory.

## Security Architecture

Authentication is Django session-based for browser users. Authorization is implemented by decorators:

- `@login_required` for most user-facing pages.
- `@user_passes_test(_is_admin)` for admin-only viewer and task routes.

FastAPI service-to-service authentication is optional API-key auth, controlled by `API_SECRET_KEY`.

Nginx provides TLS termination and HTTP-to-HTTPS redirect. Internal service hops are plain HTTP in the current Docker deployment.
