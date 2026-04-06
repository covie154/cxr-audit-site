# Fixes 1 & 2: Time Units in Email/Print Reports and API Pill Spacing

## Issue 1: TCD/TEE Time Units in Email and Print Reports

### Problem
The email and print (PDF) report templates displayed Time to Clinical Decision and End-to-End Time values in raw seconds (e.g. "245s"), while the main web report used the `_fmt_seconds()` helper to display human-readable min/sec format (e.g. "4m 05s"). This inconsistency made the email/print reports harder to read.

### Changes
- **`django-app/report/views.py`**: In `_build_report()`, added pre-formatted time strings to the `time_stats` dict using the existing `_fmt_seconds()` helper. New keys: `tcd_mean_fmt`, `tcd_median_fmt`, `tcd_p25_fmt`, `tcd_p75_fmt`, `tee_mean_fmt`, `tee_median_fmt`, `tee_p25_fmt`, `tee_p75_fmt`.
- **`django-app/report/templates/report/email_report.html`**: Replaced `{{ data.time_stats.tcd_mean|floatformat:0 }}s` style expressions with `{{ data.time_stats.tcd_mean_fmt }}` for all four TCD and TEE stat fields.
- **`django-app/report/templates/report/print_report.html`**: Same replacements as the email template.

### Why this approach
Django templates lack the ability to perform the seconds-to-minutes conversion inline. Rather than creating a custom template filter, pre-formatting in the view reuses the existing `_fmt_seconds()` function and keeps templates simple. The raw numeric values remain available for any JavaScript or other use.

## Issue 2: API Connected Pill Spacing

### Problem
The "API connected" status pill was positioned as a standalone element below the page subtitle, creating excessive vertical spacing between the header and the main upload card.

### Changes
- **`django-app/upload/templates/upload/upload_interface.html`**: Wrapped the `<h1>` and the API pill `<span>` in a `<div class="page-header">` flex container, placing the pill to the right of the title. Moved it above the subtitle.
- **`django-app/upload/static/upload/upload.css`**: Added `.page-header` flex container style. Removed `margin: 6px 0` from `.api-pill` and removed `margin-bottom` from `.page-title` (now handled by the parent `.page-header`).

### Reflections
- For Issue 1, the pre-formatted strings approach is clean and non-breaking. The raw seconds values are still present in the JSON for any client-side needs (e.g. box plot rendering).
- For Issue 2, placing the pill beside the header is a common UI pattern for status indicators and makes better use of horizontal space. The flex layout degrades gracefully if the pill text is long.
