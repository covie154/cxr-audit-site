# Unit Test Plan for PRIMER-LLM

## Overview

This document proposes a comprehensive unit test suite for the PRIMER-LLM codebase, covering the Django web application (four apps: `upload`, `viewer`, `report`, `gt`) and the FastAPI analysis backend (`cxr-audit-api`). Tests are organized by category and ranked by priority.

The codebase currently has **zero tests**. This plan focuses on practical, high-value tests that protect the most critical paths first, then expands to broader coverage.

---

## Test Categories

| Category | Description | Framework |
|----------|-------------|-----------|
| **Model tests** | Database model creation, methods, constraints | Django TestCase |
| **View tests** | HTTP responses, auth, redirects, data flow | Django TestCase + Client |
| **Utility tests** | Pure functions (metrics, formatting, helpers) | unittest / pytest |
| **API tests** | FastAPI endpoints, file handling, status codes | pytest + httpx / TestClient |
| **Integration tests** | Multi-component workflows (upload -> process -> report) | Django TestCase |

---

## Priority Levels

- **P0 (Critical)**: Core business logic that, if broken, produces wrong clinical data. Must be tested first.
- **P1 (High)**: Access control, data integrity, key user workflows.
- **P2 (Medium)**: Secondary features, edge cases, UI-facing endpoints.
- **P3 (Nice-to-have)**: Admin panel, cosmetic behavior, error messages.

---

## 1. Django `upload` App

### 1.1 Model Tests (`upload/models.py`) -- P0

| Test ID | Test Case | Description |
|---------|-----------|-------------|
| M-UP-01 | `test_cxrstudy_creation` | Create a CXRStudy with required fields; verify it saves and retrieves correctly. |
| M-UP-02 | `test_cxrstudy_bigint_primary_key` | Confirm accession_no accepts large integers (e.g. 10-digit values). |
| M-UP-03 | `test_accession_exists_true` | Insert a study, call `CXRStudy.accession_exists()` -- returns True. |
| M-UP-04 | `test_accession_exists_false` | Call `accession_exists()` with nonexistent accession -- returns False. |
| M-UP-05 | `test_get_or_none_found` | Insert a study, call `get_or_none()` -- returns the instance. |
| M-UP-06 | `test_get_or_none_missing` | Call `get_or_none()` for nonexistent accession -- returns None. |
| M-UP-07 | `test_cxrstudy_ordering` | Create multiple studies with different dates; verify default ordering is `-procedure_start_date`. |
| M-UP-08 | `test_cxrstudy_str` | Check `__str__` returns `"CXR Study <accession_no>"`. |
| M-UP-09 | `test_processingtask_creation` | Create a ProcessingTask; verify defaults (status='queued', progress_percent=0). |
| M-UP-10 | `test_processingtask_mark_completed` | Call `mark_completed()` -- status becomes 'completed', completed_at is set, progress is 100. |
| M-UP-11 | `test_processingtask_mark_failed` | Call `mark_failed('error msg')` -- status becomes 'failed', error_message is stored. |
| M-UP-12 | `test_processingtask_update_progress` | Call `update_progress()` with values -- verify all fields update correctly. |
| M-UP-13 | `test_uploadedfile_fk_cascade` | Delete a ProcessingTask -- verify associated UploadedFiles are also deleted (CASCADE). |
| M-UP-14 | `test_cxrstudy_nullable_fields` | Create a CXRStudy with only accession_no; verify all nullable fields default to None. |

### 1.2 View Tests (`upload/views.py`) -- P1

| Test ID | Test Case | Description |
|---------|-----------|-------------|
| V-UP-01 | `test_index_requires_login` | Anonymous GET to `/upload/` redirects to login. |
| V-UP-02 | `test_index_authenticated` | Logged-in GET to `/upload/` returns 200. |
| V-UP-03 | `test_tasks_list_requires_login` | Anonymous GET to `/upload/tasks/` redirects to login. |
| V-UP-04 | `test_tasks_list_shows_tasks` | Create ProcessingTasks, GET `/upload/tasks/` -- response contains task data. |
| V-UP-05 | `test_check_api_connection_returns_json` | GET `/upload/api/check-connection` returns JSON with status field. |
| V-UP-06 | `test_get_active_task_none` | No active tasks -- GET `/upload/api/active-task` returns `{"active": false}`. |
| V-UP-07 | `test_get_active_task_exists` | Create a 'processing' task -- endpoint returns task details. |
| V-UP-08 | `test_delete_task` | Create a completed task, POST delete -- task is removed from DB. |
| V-UP-09 | `test_import_data_page_loads` | GET `/upload/import/` returns 200 for authenticated user. |
| V-UP-10 | `test_is_admin_superuser` | `_is_admin()` returns True for superuser. |
| V-UP-11 | `test_is_admin_group_member` | `_is_admin()` returns True for user in 'admins' group. |
| V-UP-12 | `test_is_admin_regular_user` | `_is_admin()` returns False for regular user. |

### 1.3 Context Processor Tests -- P2

| Test ID | Test Case | Description |
|---------|-----------|-------------|
| C-UP-01 | `test_admin_status_superuser` | Superuser request -- context has `is_admin=True`. |
| C-UP-02 | `test_admin_status_regular_user` | Regular user request -- context has `is_admin=False`. |
| C-UP-03 | `test_admin_status_anonymous` | Anonymous request -- context has `is_admin=False`. |

---

## 2. Django `viewer` App

### 2.1 View Tests (`viewer/views.py`) -- P1

| Test ID | Test Case | Description |
|---------|-----------|-------------|
| V-VW-01 | `test_index_requires_admin` | Regular user GET `/view/` returns 302 (denied). |
| V-VW-02 | `test_index_admin_access` | Admin GET `/view/` returns 200 with paginated table. |
| V-VW-03 | `test_index_search_filters` | GET `/view/?q=searchterm` -- queryset is filtered correctly. |
| V-VW-04 | `test_index_filter_by_workplace` | GET `/view/?f_workplace=TPYCR01` -- only TPY studies returned. |
| V-VW-05 | `test_index_filter_null` | GET `/view/?f_gt_manual=__null__` -- only studies with gt_manual=None. |
| V-VW-06 | `test_index_filter_notnull` | GET `/view/?f_gt_manual=__notnull__` -- only studies with gt_manual set. |
| V-VW-07 | `test_index_sorting` | GET `/view/?sort=accession_no` -- results sorted ascending by accession_no. |
| V-VW-08 | `test_index_sorting_invalid_field` | GET `/view/?sort=invalid_field` -- falls back to `-created_at`. |
| V-VW-09 | `test_index_pagination` | Create 100 studies, GET `/view/?per_page=20` -- only 20 shown, paginator works. |
| V-VW-10 | `test_index_per_page_bounds` | per_page < 10 clamps to 10; per_page > 500 clamps to 500. |
| V-VW-11 | `test_study_detail_returns_json` | Admin GET `/view/study/<id>/` returns JSON with field groups. |
| V-VW-12 | `test_study_detail_nonexistent` | GET nonexistent study -- returns 404. |
| V-VW-13 | `test_study_update_editable_field` | POST update with `{"workplace": "NEWVAL"}` -- field is updated. |
| V-VW-14 | `test_study_update_readonly_field` | POST update with `{"accession_no": 999}` -- accession_no is NOT updated. |
| V-VW-15 | `test_study_update_invalid_json` | POST with non-JSON body -- returns 400. |
| V-VW-16 | `test_study_delete` | Admin POST `/view/study/<id>/delete/` -- study is deleted. |
| V-VW-17 | `test_bulk_delete` | POST `/view/bulk-delete/` with list of IDs -- all are deleted. |
| V-VW-18 | `test_bulk_delete_empty_list` | POST with empty accession_nos -- returns 400 error. |
| V-VW-19 | `test_export_csv` | Admin GET `/view/export/` -- response is CSV with correct content-type. |
| V-VW-20 | `test_export_csv_contains_all_fields` | CSV header row includes all model field names. |
| V-VW-21 | `test_export_csv_respects_filters` | Export with search/filter params -- CSV only contains matching records. |

---

## 3. Django `report` App

### 3.1 Utility / Helper Function Tests -- P0

These are **pure functions** that compute clinical metrics. Errors here directly produce wrong accuracy numbers in clinical reports.

| Test ID | Test Case | Description |
|---------|-----------|-------------|
| U-RP-01 | `test_compute_metrics_all_tp` | All studies gt=1/pred=1 -- sensitivity=1.0, specificity=0, PPV=1.0. |
| U-RP-02 | `test_compute_metrics_all_tn` | All studies gt=0/pred=0 -- specificity=1.0, sensitivity=0, NPV=1.0. |
| U-RP-03 | `test_compute_metrics_mixed` | Known confusion matrix (e.g. tp=40, tn=50, fp=5, fn=5) -- verify all metrics match hand-calculated values. |
| U-RP-04 | `test_compute_metrics_skips_none` | Studies with gt=None or pred=None are excluded from the count. |
| U-RP-05 | `test_compute_metrics_empty` | Empty list -- n=0, all metrics=0, no division-by-zero error. |
| U-RP-06 | `test_compute_metrics_roc_auc` | ROC-AUC = (sensitivity + specificity) / 2 -- verify formula. |
| U-RP-07 | `test_fmt_seconds_under_60` | `_fmt_seconds(45)` returns `'45s'`. |
| U-RP-08 | `test_fmt_seconds_minutes` | `_fmt_seconds(150)` returns `'2m 30s'`. |
| U-RP-09 | `test_fmt_seconds_hours` | `_fmt_seconds(3720)` returns `'1h 02m'`. |
| U-RP-10 | `test_fmt_seconds_none` | `_fmt_seconds(None)` returns `'---'` (em dash). |
| U-RP-11 | `test_short_site_known` | `_short_site('TPYCR01')` returns `'TPY'`. |
| U-RP-12 | `test_short_site_unknown` | `_short_site('UNKNOWN')` returns `'OTH'`. |
| U-RP-13 | `test_get_site_thresholds_default` | Default site returns all standard thresholds, nodule=15. |
| U-RP-14 | `test_get_site_thresholds_yis` | YIS site returns nodule=5, all others at default. |
| U-RP-15 | `test_lunit_positive_above_threshold` | Study with nodule=20 (thresh=15) -- returns True. |
| U-RP-16 | `test_lunit_positive_below_threshold` | All scores below threshold -- returns False. |
| U-RP-17 | `test_lunit_positive_none_scores` | All scores are None -- returns False (no crash). |
| U-RP-18 | `test_compute_time_stats_with_data` | Provide a list of studies with time values -- verify median, P25, P75, count, more_than_5mins. |
| U-RP-19 | `test_compute_time_stats_empty` | No time data -- all values are None, counts are 0. |
| U-RP-20 | `test_compute_time_stats_single_value` | Single time value -- median equals that value, quantiles handled. |
| U-RP-21 | `test_compute_weekly_site_metrics` | 3 weeks of data across 2 sites -- verify correct bucketing and per-site sensitivity/specificity. |
| U-RP-22 | `test_compute_weekly_site_metrics_empty` | No studies -- returns None. |
| U-RP-23 | `test_compute_weekly_overall_auc` | Multiple weeks -- verify AUC trend and 95% CI computation. |
| U-RP-24 | `test_compute_gt_metrics_different_fields` | Use gt_manual as GT field -- verify it reads the correct attribute. |
| U-RP-25 | `test_compute_manual_vs_llm_agreement` | Known agreement data -- verify agreement_pct and kappa. |
| U-RP-26 | `test_compute_manual_vs_llm_mcnemar` | Known discordant pairs -- verify McNemar p-value and significance. |
| U-RP-27 | `test_compute_manual_vs_llm_no_manual` | No studies have gt_manual -- returns None. |
| U-RP-28 | `test_build_report_empty` | No records -- returns summary with total=0 and no crash. |
| U-RP-29 | `test_build_report_full` | Populated studies -- verify report dict has all expected keys (overall, site_metrics, time_stats, etc.). |

### 3.2 View Tests -- P1

| Test ID | Test Case | Description |
|---------|-----------|-------------|
| V-RP-01 | `test_index_requires_login` | Anonymous GET `/report/` redirects to login. |
| V-RP-02 | `test_index_authenticated` | Logged-in GET `/report/` returns 200. |
| V-RP-03 | `test_generate_report_returns_json` | GET `/report/generate/?date_from=...&date_to=...` returns JSON with expected keys. |
| V-RP-04 | `test_generate_report_date_range` | Only studies within the date range appear in the report. |
| V-RP-05 | `test_export_report_csv` | GET `/report/export-csv/` returns CSV with correct fields. |
| V-RP-06 | `test_export_false_negatives_csv` | GET `/report/export-fn-csv/` returns CSV filtered to gt_llm=0, gt_manual=1. |
| V-RP-07 | `test_export_false_positives_csv` | GET `/report/export-fp-csv/` returns CSV filtered to gt_llm=1, gt_manual=0. |
| V-RP-08 | `test_email_report_invalid_json` | POST invalid JSON to `/report/email-report/` returns 400. |
| V-RP-09 | `test_email_report_invalid_email` | POST with invalid email address -- returns 400 with error message. |
| V-RP-10 | `test_email_report_no_recipients` | POST with empty recipients -- returns 400. |
| V-RP-11 | `test_email_report_success` | POST valid data (with mocked SMTP) -- returns `{"ok": true}`. |
| V-RP-12 | `test_download_pdf_returns_html` | POST valid report_data to `/report/download-pdf/` -- returns HTML response. |
| V-RP-13 | `test_download_pdf_no_data` | POST without report_data -- returns 400. |

---

## 4. Django `gt` App

### 4.1 Utility Tests -- P1

| Test ID | Test Case | Description |
|---------|-----------|-------------|
| U-GT-01 | `test_default_friday_range` | Returns (previous_friday, last_friday) -- both are Fridays, 7 days apart. |
| U-GT-02 | `test_default_friday_range_on_friday` | When today is Friday, last_friday is one week ago. |
| U-GT-03 | `test_best_column_match_exact` | `_best_column_match(['accession_no', 'text_report'], 'accession')` returns `'accession_no'`. |
| U-GT-04 | `test_best_column_match_fuzzy` | `_best_column_match(['acc_no', 'report'], 'accession')` returns `'acc_no'`. |
| U-GT-05 | `test_read_uploaded_file_csv` | Upload a CSV InMemoryUploadedFile -- returns correct rows and columns. |
| U-GT-06 | `test_read_uploaded_file_unsupported` | Upload a `.txt` file -- raises ValueError. |
| U-GT-07 | `test_read_uploaded_file_empty` | Upload a CSV with headers only -- raises ValueError (no data rows). |

### 4.2 View Tests -- P1

| Test ID | Test Case | Description |
|---------|-----------|-------------|
| V-GT-01 | `test_index_requires_login` | Anonymous GET `/gt/` redirects to login. |
| V-GT-02 | `test_report_count` | Create studies in date range -- GET returns correct total and without_gt counts. |
| V-GT-03 | `test_report_count_missing_params` | GET without start/end -- returns 400. |
| V-GT-04 | `test_report_count_invalid_dates` | Start after end -- returns 400. |
| V-GT-05 | `test_report_count_priority_breakdown` | Create studies across priority and non-priority workplaces -- verify priority_count and other_count. |
| V-GT-06 | `test_download_reports_csv` | GET with valid params -- returns CSV with accession_no, text_report, manual_gt columns. |
| V-GT-07 | `test_download_reports_stratified_sampling` | Verify ~50/50 split between priority and other workplaces (seed is deterministic, seed=42). |
| V-GT-08 | `test_download_reports_count_clamped` | Request more reports than exist -- count clamped to total. |
| V-GT-09 | `test_download_reports_no_eligible` | No reports without gt_manual -- returns 404. |
| V-GT-10 | `test_validate_upload_csv` | POST a valid CSV file -- returns column names and suggested mappings. |
| V-GT-11 | `test_validate_upload_no_file` | POST without file -- returns 400. |
| V-GT-12 | `test_validate_upload_too_many_rows` | POST file with >10,000 rows -- returns 400 error. |
| V-GT-13 | `test_apply_gt_updates_studies` | Upload data with valid accession + gt values -- studies are updated in DB. |
| V-GT-14 | `test_apply_gt_accepts_boolean_strings` | gt values like 'true', 'false', 'yes', 'no' are accepted. |
| V-GT-15 | `test_apply_gt_invalid_gt_value` | gt value 'maybe' -- skipped with error message. |
| V-GT-16 | `test_apply_gt_nonexistent_accession` | Accession not in DB -- skipped with error message. |
| V-GT-17 | `test_apply_gt_no_session_data` | POST apply-gt without prior validate -- returns 400. |
| V-GT-18 | `test_apply_gt_clears_session` | After successful apply -- session data is cleared. |

---

## 5. FastAPI Backend (`cxr-audit-api`)

### 5.1 Helper Function Tests (`cxr_audit/helpers.py`) -- P0

| Test ID | Test Case | Description |
|---------|-----------|-------------|
| U-API-01 | `test_levenshtein_distance_identical` | Same strings -- distance=0. |
| U-API-02 | `test_levenshtein_distance_one_edit` | "cat" vs "bat" -- distance=1. |
| U-API-03 | `test_levenshtein_distance_empty` | One empty string -- distance=length of other. |
| U-API-04 | `test_closest_finding` | "cardiomegly" (typo) against findings list -- returns "cardiomegaly" (from Padchest dict). |
| U-API-05 | `test_encode_findings_text_to_index` | Textual findings mapped to correct integer indices. |
| U-API-06 | `test_encode_findings_temporal_mapping` | 'new' maps to 0, 'stable' to 3, etc. |
| U-API-07 | `test_encode_findings_device_placement` | 'malpositioned' maps to 2. |
| U-API-08 | `test_parse_list_dict_list_input` | Already a list -- returned as-is. |
| U-API-09 | `test_parse_list_dict_string_input` | Valid string repr of list -- parsed correctly. |
| U-API-10 | `test_parse_list_dict_none` | None input -- returns empty list. |
| U-API-11 | `test_parse_list_dict_nan` | NaN input -- returns empty list. |
| U-API-12 | `test_parse_list_dict_malformed` | Malformed string -- returns empty list (no crash). |

### 5.2 Grading Logic Tests (`cxr_audit/lib_audit_cxr_v2.py`) -- P0

These require mocking the OpenAI client to avoid real LLM calls.

| Test ID | Test Case | Description |
|---------|-----------|-------------|
| U-API-13 | `test_get_priorities_no_findings` | Empty findings/lines/diagnoses -- overall_max_priority=1. |
| U-API-14 | `test_get_priorities_with_findings` | A finding with priority 4 -- max_finding_priority=4. |
| U-API-15 | `test_get_priorities_uncertainty_decreases` | Finding with uncertainty=1 -- priority decremented by 1. |
| U-API-16 | `test_get_priorities_clamped_1_to_5` | Priority cannot go below 1 or above 5. |
| U-API-17 | `test_get_priorities_malpositioned_device` | Device with placement=2 -- priority forced to 5. |
| U-API-18 | `test_get_priorities_diagnosis_stable` | Diagnosis with temporal=3 (stable) -- priority decremented. |
| U-API-19 | `test_judge_grading_same_grades` | algo=3, llm=3 -- returns grade=3, choice=3 (both same). |

### 5.3 Batch Processing Tests (`cxr_audit/grade_batch_async.py`) -- P1

| Test ID | Test Case | Description |
|---------|-----------|-------------|
| U-API-20 | `test_clean_text_removes_header` | Input with "CHEST of 01-Jan-2025:" -- header removed. |
| U-API-21 | `test_clean_text_removes_accession` | Input with "Accession No:12345" -- removed. |
| U-API-22 | `test_clean_text_normalizes_newlines` | Multiple newlines collapsed to single. |
| U-API-23 | `test_extract_grade_dict` | `{'grade': 3}` -- returns 3. |
| U-API-24 | `test_extract_grade_empty` | `{}` -- returns 0. |
| U-API-25 | `test_extract_grade_non_dict` | Non-dict input -- returns 0. |
| U-API-26 | `test_extract_hybrid_result` | `{'grade': 4, 'explanation': 'text'}` -- returns (4, 'text'). |
| U-API-27 | `test_process_full_pipeline_invalid_steps` | Invalid step name -- raises ValueError. |

### 5.4 ProcessCarpl Tests (`class_process_carpl.py`) -- P0

| Test ID | Test Case | Description |
|---------|-----------|-------------|
| U-API-28 | `test_transform_workplace_known` | 'TPYCR01' -> 'TPY'. |
| U-API-29 | `test_transform_workplace_unknown` | 'XXXXX' -> 'OTH'. |
| U-API-30 | `test_fill_threshold_dict_missing` | Site dict with only 'Nodule': 5 -- remaining thresholds filled from defaults. |
| U-API-31 | `test_fill_threshold_dict_invalid_finding` | Invalid finding name -- raises ValueError. |
| U-API-32 | `test_fill_threshold_dict_invalid_value` | Non-numeric threshold -- raises ValueError. |
| U-API-33 | `test_process_stats_row_positive` | Row with one score above threshold -- returns 1. |
| U-API-34 | `test_process_stats_row_negative` | All scores below threshold -- returns 0. |
| U-API-35 | `test_process_stats_row_site_specific` | YIS site with Nodule=8 (thresh=5) -- returns 1; default site with Nodule=8 (thresh=15) -- returns 0. |
| U-API-36 | `test_highest_probability` | Row with Nodule=85 being highest -- returns "Nodule". |
| U-API-37 | `test_calculate_agreement_metrics` | Known TP/TN/FP/FN -- verify all derived metrics. |
| U-API-38 | `test_convert_to_minutes` | Timedelta of 90 seconds -- returns "1m 30s". |
| U-API-39 | `test_convert_to_minutes_nan` | NaN input -- returns NaN. |

### 5.5 FastAPI Endpoint Tests (`combined_server.py`) -- P1

| Test ID | Test Case | Description |
|---------|-----------|-------------|
| E-API-01 | `test_root_endpoint` | GET `/` -- returns JSON with API info and endpoints. |
| E-API-02 | `test_status_not_found` | GET `/status/nonexistent-id` -- returns 404. |
| E-API-03 | `test_results_not_found` | GET `/results/nonexistent-id` -- returns 404. |
| E-API-04 | `test_results_not_completed` | GET results for a 'processing' task -- returns 400. |
| E-API-05 | `test_delete_task` | DELETE `/tasks/id` for existing task -- returns success. |
| E-API-06 | `test_delete_task_not_found` | DELETE `/tasks/nonexistent` -- returns 404. |
| E-API-07 | `test_list_tasks` | Create several tasks -- GET `/tasks` returns them all. |
| E-API-08 | `test_api_key_required` | When API_SECRET_KEY is set, requests without X-API-Key header return 403. |
| E-API-09 | `test_api_key_valid` | Valid X-API-Key header -- request succeeds. |
| E-API-10 | `test_analyze_auto_sort_missing_files` | POST with no files -- returns 422 (validation error). |

### 5.6 Progress Callback Tests -- P2

| Test ID | Test Case | Description |
|---------|-----------|-------------|
| U-API-40 | `test_progress_callback_llm_step` | LLM step at 50% with supplemental=False -- overall progress ~ 45%. |
| U-API-41 | `test_progress_callback_lunit_step` | Lunit step at 50% with supplemental=True -- overall progress ~ 57.5%. |
| U-API-42 | `test_progress_callback_updates_dict` | Callback updates processing_results dict correctly. |

---

## 6. Integration Tests

### P2

| Test ID | Test Case | Description |
|---------|-----------|-------------|
| I-01 | `test_import_csv_to_db` | Use the upload import workflow: POST a CSV preview, then confirm -- verify studies are created in DB. |
| I-02 | `test_report_after_import` | Import studies, then generate a report -- verify metrics reflect the imported data. |
| I-03 | `test_gt_workflow_download_then_apply` | Download GT sample, fill in labels, upload back -- verify gt_manual updated on correct studies. |
| I-04 | `test_viewer_reflects_import` | Import studies -- viewer page shows them with correct counts. |
| I-05 | `test_binary_conversion_r1_r2` | Studies with llm_grade=1 or 2 -- gt_llm should be 0 (normal). |
| I-06 | `test_binary_conversion_r3_r5` | Studies with llm_grade=3, 4, or 5 -- gt_llm should be 1 (abnormal). |

---

## 7. Testing Infrastructure Recommendations

### 7.1 Framework and Tooling

- **Django tests**: Use `django.test.TestCase` (provides DB transaction rollback per test).
- **FastAPI tests**: Use `pytest` with `httpx.AsyncClient` or `fastapi.testclient.TestClient`.
- **Mocking**: Use `unittest.mock.patch` to mock:
  - External API calls (requests to FastAPI from Django views)
  - LLM/OpenAI client calls (for CXRClassifier tests)
  - Email sending (for report email tests)
  - File I/O for protected Excel files
- **Fixtures**: Create a `conftest.py` (or Django fixtures) with:
  - A factory function for creating CXRStudy instances with realistic data
  - Sample threshold dictionaries
  - Mock OpenAI response objects

### 7.2 Directory Structure

```
django-app/
  upload/tests/
    __init__.py
    test_models.py          # M-UP-* tests
    test_views.py           # V-UP-* tests
    test_context_processors.py  # C-UP-* tests
  viewer/tests/
    __init__.py
    test_views.py           # V-VW-* tests
  report/tests/
    __init__.py
    test_helpers.py         # U-RP-* tests (pure functions)
    test_views.py           # V-RP-* tests
  gt/tests/
    __init__.py
    test_helpers.py         # U-GT-* tests
    test_views.py           # V-GT-* tests
  tests/
    __init__.py
    test_integration.py     # I-* tests
    factories.py            # Shared test data factories

cxr-audit-api/
  tests/
    __init__.py
    test_helpers.py         # U-API-01 to U-API-12
    test_classifier.py      # U-API-13 to U-API-19 (mocked LLM)
    test_batch_processor.py # U-API-20 to U-API-27
    test_process_carpl.py   # U-API-28 to U-API-39
    test_endpoints.py       # E-API-* tests
    test_progress.py        # U-API-40 to U-API-42
    conftest.py             # Shared fixtures
```

### 7.3 Test Data Factory Example

```python
# django-app/tests/factories.py
from datetime import datetime, timedelta
from django.utils import timezone
from upload.models import CXRStudy

def make_study(accession_no, **overrides):
    """Create a CXRStudy with sensible defaults."""
    defaults = {
        'accession_no': accession_no,
        'workplace': 'TPYCR01',
        'procedure_start_date': timezone.now() - timedelta(days=1),
        'gt_llm': 1,
        'lunit_binarised': 1,
        'llm_grade': 3,
        'abnormal': 50.0,
        'atelectasis': 5.0,
        'calcification': 2.0,
        'cardiomegaly': 8.0,
        'consolidation': 3.0,
        'fibrosis': 1.0,
        'mediastinal_widening': 0.5,
        'nodule': 12.0,
        'pleural_effusion': 4.0,
        'pneumoperitoneum': 0.1,
        'pneumothorax': 0.2,
        'tuberculosis': 0.3,
        'text_report': 'Normal chest. No focal lung lesion.',
    }
    defaults.update(overrides)
    return CXRStudy.objects.create(**defaults)
```

### 7.4 Running Tests

```bash
# Django tests
cd django-app
python manage.py test                      # all tests
python manage.py test report.tests         # single app
python manage.py test report.tests.test_helpers.TestComputeMetrics  # single class

# FastAPI tests
cd cxr-audit-api
pytest tests/                              # all API tests
pytest tests/test_helpers.py -v            # single module
```

### 7.5 CI Integration

Add a GitHub Actions workflow (`.github/workflows/test.yml`) that:
1. Sets up Python 3.11+
2. Installs dependencies for both django-app and cxr-audit-api
3. Runs Django migrations on a test SQLite DB
4. Runs `python manage.py test` for Django
5. Runs `pytest` for FastAPI
6. Reports test results as a PR check

### 7.6 Implementation Priorities

**Phase 1 (immediate)** -- P0 tests:
- Report helper functions (U-RP-01 through U-RP-29): these are pure functions, easy to test, protect the most critical clinical metrics.
- Model tests (M-UP-01 through M-UP-14): foundational data layer.
- API helper functions (U-API-01 through U-API-12): pure functions, no mocking needed.
- ProcessCarpl threshold/binarization logic (U-API-28 through U-API-39).

**Phase 2 (soon after)** -- P1 tests:
- All view tests that verify access control (login_required, admin_required).
- GT workflow tests (validate, apply, stratified sampling).
- FastAPI endpoint tests.

**Phase 3 (ongoing)** -- P2/P3 tests:
- Integration tests.
- Context processor tests.
- Progress callback tests.

---

## Summary

| Category | P0 | P1 | P2 | P3 | Total |
|----------|----|----|----|----|-------|
| Model tests | 14 | - | - | - | 14 |
| View tests (upload) | - | 12 | 3 | - | 15 |
| View tests (viewer) | - | 21 | - | - | 21 |
| View tests (report) | - | 13 | - | - | 13 |
| View tests (gt) | - | 18 | - | - | 18 |
| Report helpers | 29 | - | - | - | 29 |
| GT helpers | - | 7 | - | - | 7 |
| API helpers | 12 | - | - | - | 12 |
| API grading logic | 7 | - | - | - | 7 |
| API batch processing | - | 8 | - | - | 8 |
| API ProcessCarpl | 12 | - | - | - | 12 |
| API endpoints | - | 10 | - | - | 10 |
| API progress | - | - | 3 | - | 3 |
| Integration tests | - | - | 6 | - | 6 |
| **Total** | **74** | **89** | **12** | **0** | **175** |

The 74 P0 tests should be implemented first; they cover the clinical metrics calculations, data model integrity, and grading logic that form the backbone of the system.
