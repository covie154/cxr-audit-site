# Documentation Fix #5: Unit Test Plan

## Summary

Proposed a comprehensive unit test plan covering 175 test cases across all Django apps (upload, viewer, report, gt) and the FastAPI backend (cxr-audit-api). The plan is written to `documentation/unit_tests_plan.md` and includes specific test IDs, descriptions, priority levels, and infrastructure recommendations.

The codebase currently has zero tests. The plan prioritizes 74 P0 (critical) tests that protect clinical metrics calculations, data model integrity, and the grading/binarization logic -- the parts of the system where errors would directly produce incorrect clinical reports.

## Approach

1. **Read every source file** in both the Django app and FastAPI backend, including:
   - All four Django apps: `upload` (models, views, admin, context_processors, utils), `viewer` (views), `report` (views with 10+ helper functions), `gt` (views with stratified sampling, file parsing, GT application)
   - The FastAPI server (`combined_server.py`), the processing pipeline (`class_process_carpl.py`), the LLM grading engine (`lib_audit_cxr_v2.py`), batch processor (`grade_batch_async.py`), helper functions (`helpers.py`), prompts (`prompts.py`), and iterative LLM module (`llm_iter.py`)
   - Django settings, URL configurations, and existing documentation files

2. **Identified testable units** by categorizing code into:
   - Pure functions (no side effects, easiest to test) -- report metrics, time formatting, Levenshtein distance, threshold filling, workplace mapping
   - Model methods (DB-dependent but straightforward) -- accession_exists, get_or_none, mark_completed, mark_failed
   - View functions (require Django test client + auth setup) -- access control, CRUD operations, CSV export, JSON API endpoints
   - External-dependency code (requires mocking) -- LLM calls, email sending, FastAPI proxy calls

3. **Assigned priorities** based on clinical impact:
   - P0 for anything that computes numbers appearing in clinical reports (sensitivity, specificity, confusion matrix, ROC-AUC, time statistics, binary conversion thresholds)
   - P1 for access control (admin-only views), data integrity (CRUD), and user-facing workflows
   - P2 for integration tests and secondary features

## Files Created

- `documentation/unit_tests_plan.md` -- The full test plan with 175 test cases
- `documentation/documentation_fixes_5.md` -- This file

## Reflections

- The **report app** has the most critical testable surface area. Its helper functions (`_compute_metrics`, `_compute_time_stats`, `_compute_weekly_site_metrics`, `_compute_manual_vs_llm`, etc.) are pure functions that take study lists and return metric dictionaries. These are ideal candidates for unit testing and should be the very first tests written.

- The **grading binarization logic** (`llm_grade > 2 -> gt_llm = 1`) is duplicated between the Django report app and the API's `ProcessCarpl` class (where it's `llm_grade > 1 -> binary 1`). This discrepancy (>2 vs >1) should be investigated -- it may be an intentional difference between the R-scale convention and the binary convention, but a test that documents the expected behavior would prevent future confusion.

- The **FastAPI backend** is harder to test in isolation because `class_process_carpl.py` initializes a global `BatchCXRProcessor` at module import time (which tries to load JSON files and connect to Ollama). Tests for this module will need careful import mocking or refactoring of the global initialization.

- Many Django views act as **proxies** to the FastAPI backend (e.g., `analyze_auto_sort`, `get_status`, `get_results`). These are best tested by mocking `requests.post`/`requests.get` at the Django level, without needing the FastAPI server running.

- The **gt app's stratified sampling** uses a fixed random seed (42), which makes the sampling deterministic and therefore testable. This is a good design choice for reproducibility.

- No existing test infrastructure (no `tests.py` files, no `conftest.py`, no CI workflow) means the first implementation step should include setting up the test directory structure and a basic CI pipeline.
