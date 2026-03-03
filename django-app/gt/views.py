"""
Views for the Manual Ground Truth app.

Provides functionality to:
1. Download a random sample of CXR reports from a date range for manual cross-checking
2. Upload manually labelled reports back into the database
"""

import csv
import io
import math
import random
from datetime import date, timedelta
from difflib import SequenceMatcher

from django.db.models import Q
from django.shortcuts import render
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required

from upload.models import CXRStudy

# Workplaces for stratified 50/50 sampling
_PRIORITY_PREFIXES = ('TPY', 'HOU', 'KHA', 'AMK')

# Recommended sample percentage for manual GT audit.
# Derived from power analysis (see documentation/sampling_280226.md):
# 2% (~150 per ~7,000 reports) provides ±5% precision on a 95% CI
# for agreement, and exceeds requirements for McNemar's test and
# non-inferiority testing of LLM sensitivity.
RECOMMENDED_SAMPLE_PCT = 2


def _default_friday_range():
    """
    Return (previous_friday, last_friday) covering the past week,
    i.e. the Friday before last → last Friday.
    """
    today = date.today()
    # days_since_friday: Monday=0 … Sunday=6, Friday=4
    days_since_friday = (today.weekday() - 4) % 7
    last_friday = today - timedelta(days=days_since_friday)
    # If today IS Friday, last_friday == today; push back one week
    if last_friday == today:
        last_friday = today - timedelta(days=7)
    previous_friday = last_friday - timedelta(days=7)
    return previous_friday, last_friday


@login_required
def index(request):
    """Render the Manual GT page."""
    start, end = _default_friday_range()
    return render(request, 'gt/index.html', {
        'default_start': start.isoformat(),
        'default_end': end.isoformat(),
    })


@login_required
@require_http_methods(["GET"])
def report_count(request):
    """
    Return the total number of reports and those without GT in the given date range.
    Query params: start (YYYY-MM-DD), end (YYYY-MM-DD)
    Filters on procedure_start_date (inclusive on both ends).
    """
    start = request.GET.get('start')
    end = request.GET.get('end')
    if not start or not end:
        return JsonResponse({'error': 'start and end are required'}, status=400)

    try:
        start_date = date.fromisoformat(start)
        end_date = date.fromisoformat(end)
    except ValueError:
        return JsonResponse({'error': 'Invalid date format. Use YYYY-MM-DD.'}, status=400)

    if start_date > end_date:
        return JsonResponse({'error': 'Start date must be before or equal to end date.'}, status=400)

    # Base queryset: reports with text in the date range
    base_qs = CXRStudy.objects.filter(
        procedure_start_date__date__gte=start_date,
        procedure_start_date__date__lte=end_date,
        text_report__isnull=False,
    ).exclude(text_report='')

    total = base_qs.count()
    eligible_qs = base_qs.filter(gt_manual__isnull=True)
    without_gt = eligible_qs.count()

    # Breakdown by priority workplaces (TPY, HOU, KHA, AMK) vs rest
    priority_q = Q()
    for prefix in _PRIORITY_PREFIXES:
        priority_q |= Q(workplace__istartswith=prefix)

    priority_count = eligible_qs.filter(priority_q).count()
    other_count = eligible_qs.exclude(priority_q).count()

    recommended_count = max(1, math.ceil(without_gt * RECOMMENDED_SAMPLE_PCT / 100))

    return JsonResponse({
        'total': total,
        'without_gt': without_gt,
        'priority_count': priority_count,
        'other_count': other_count,
        'recommended_pct': RECOMMENDED_SAMPLE_PCT,
        'recommended_count': recommended_count,
    })


@login_required
@require_http_methods(["GET"])
def download_reports(request):
    """
    Download a random sample of reports in the given date range as CSV.
    Query params: start, end (YYYY-MM-DD), count (int — number of reports to include).
    Returns CSV with columns: accession_no, text_report, manual_gt (blank).
    """
    start = request.GET.get('start')
    end = request.GET.get('end')
    count_str = request.GET.get('count')

    if not start or not end or not count_str:
        return JsonResponse({'error': 'start, end, and count are required'}, status=400)

    try:
        start_date = date.fromisoformat(start)
        end_date = date.fromisoformat(end)
        count = int(count_str)
    except ValueError:
        return JsonResponse({'error': 'Invalid parameter format.'}, status=400)

    if start_date > end_date:
        return JsonResponse({'error': 'Start date must be before or equal to end date.'}, status=400)
    if count < 1:
        return JsonResponse({'error': 'Count must be at least 1.'}, status=400)

    # Fetch only reports without GT filled in
    qs = CXRStudy.objects.filter(
        procedure_start_date__date__gte=start_date,
        procedure_start_date__date__lte=end_date,
        text_report__isnull=False,
        gt_manual__isnull=True,
    ).exclude(text_report='')

    total = qs.count()
    if total == 0:
        return JsonResponse({'error': 'No reports without GT found in the selected date range.'}, status=404)

    # Clamp count to total
    count = min(count, total)

    # ── Stratified sampling: 50% priority workplaces, 50% rest ──
    # Priority workplace codes start with these prefixes
    priority_q = Q()
    for prefix in _PRIORITY_PREFIXES:
        priority_q |= Q(workplace__istartswith=prefix)

    priority_pks = list(qs.filter(priority_q).values_list('accession_no', flat=True))
    other_pks = list(qs.exclude(priority_q).values_list('accession_no', flat=True))

    rng = random.Random(42)

    # Target 50/50 split; if one group is too small, backfill from the other
    half = count // 2
    other_half = count - half  # handles odd counts

    priority_take = min(half, len(priority_pks))
    other_take = min(other_half, len(other_pks))

    # Compute shortfalls before adjusting
    priority_shortfall = half - priority_take       # how many priority couldn't fill
    other_shortfall = other_half - other_take       # how many other couldn't fill

    # Backfill: give each group's shortfall to the other
    priority_take += min(other_shortfall, len(priority_pks) - priority_take)
    other_take += min(priority_shortfall, len(other_pks) - other_take)

    sampled_pks = rng.sample(priority_pks, priority_take) + rng.sample(other_pks, other_take)

    sampled = CXRStudy.objects.filter(accession_no__in=sampled_pks).order_by('procedure_start_date')

    # Build CSV response
    response = HttpResponse(content_type='text/csv')
    filename = f"gt_reports_{start}_{end}_{count}.csv"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'

    writer = csv.writer(response)
    writer.writerow(['accession_no', 'text_report', 'manual_gt'])
    for study in sampled:
        writer.writerow([study.accession_no, study.text_report or '', ''])

    return response


# ═══════════════════════════════════════════════════════════
#  Upload & Validate
# ═══════════════════════════════════════════════════════════

def _best_column_match(columns, target):
    """Return the column name most similar to *target* (case-insensitive)."""
    best, best_score = None, 0
    for col in columns:
        score = SequenceMatcher(None, col.lower(), target.lower()).ratio()
        if score > best_score:
            best, best_score = col, score
    return best


def _read_uploaded_file(uploaded_file):
    """
    Read an uploaded CSV / XLS / XLSX into a list of dicts + column names.
    Returns (rows: list[dict], columns: list[str]) or raises ValueError.
    """
    name = uploaded_file.name.lower()

    if name.endswith('.csv'):
        text = uploaded_file.read().decode('utf-8-sig')
        reader = csv.DictReader(io.StringIO(text))
        columns = reader.fieldnames or []
        rows = list(reader)
    elif name.endswith(('.xls', '.xlsx')):
        try:
            import pandas as pd
        except ImportError:
            raise ValueError('pandas is required to read Excel files. Install it with: pip install pandas openpyxl')
        df = pd.read_excel(uploaded_file, dtype=str)
        columns = list(df.columns)
        rows = df.where(df.notna(), '').to_dict(orient='records')
    else:
        raise ValueError('Unsupported file type. Only CSV, XLS and XLSX are accepted.')

    if not columns:
        raise ValueError('The file appears to be empty or has no column headers.')

    return rows, columns


@login_required
@csrf_exempt
@require_http_methods(["POST"])
def validate_upload(request):
    """
    Upload a file and validate it for GT import.
    Returns column names, best-guess mappings, and row-level validation.
    """
    if 'file' not in request.FILES:
        return JsonResponse({'error': 'No file uploaded.'}, status=400)

    uploaded = request.FILES['file']

    try:
        rows, columns = _read_uploaded_file(uploaded)
    except ValueError as e:
        return JsonResponse({'error': str(e)}, status=400)

    MAX_GT_ROWS = 10000
    if len(rows) == 0:
        return JsonResponse({'error': 'The file contains no data rows.'}, status=400)
    if len(rows) > MAX_GT_ROWS:
        return JsonResponse({'error': f'File exceeds the maximum of {MAX_GT_ROWS:,} rows.'}, status=400)

    # Best-guess column mapping
    acc_guess = _best_column_match(columns, 'accession')
    gt_guess = _best_column_match(columns, 'manual_gt')

    # Store rows in session so we don't need to re-upload
    request.session['gt_upload_rows'] = rows
    request.session['gt_upload_columns'] = columns

    return JsonResponse({
        'columns': columns,
        'row_count': len(rows),
        'suggested_accession': acc_guess,
        'suggested_gt': gt_guess,
    })


@login_required
@csrf_exempt
@require_http_methods(["POST"])
def apply_gt(request):
    """
    Apply manual GT labels from the validated upload to the database.
    Expects JSON body: { accession_col: str, gt_col: str }
    Uses the rows stored in session by validate_upload.
    """
    import json

    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'error': 'Invalid JSON body.'}, status=400)

    acc_col = body.get('accession_col')
    gt_col = body.get('gt_col')
    if not acc_col or not gt_col:
        return JsonResponse({'error': 'accession_col and gt_col are required.'}, status=400)

    rows = request.session.get('gt_upload_rows')
    columns = request.session.get('gt_upload_columns')
    if not rows or not columns:
        return JsonResponse({'error': 'No validated file in session. Please validate first.'}, status=400)

    if acc_col not in columns or gt_col not in columns:
        return JsonResponse({'error': 'Selected column(s) not found in the uploaded file.'}, status=400)

    updated = 0
    skipped = 0
    errors = []

    for i, row in enumerate(rows, start=2):  # row 1 = header
        raw_acc = str(row.get(acc_col, '')).strip()
        raw_gt = str(row.get(gt_col, '')).strip()

        # --- validate accession (integer) ---
        if not raw_acc:
            skipped += 1
            errors.append(f'Row {i}: empty accession number.')
            continue
        try:
            acc_int = int(float(raw_acc))  # handles "12345.0" from Excel
        except (ValueError, OverflowError):
            skipped += 1
            errors.append(f'Row {i}: accession "{raw_acc}" is not a valid integer.')
            continue

        # --- validate gt (0 or 1) ---
        if raw_gt == '':
            skipped += 1
            errors.append(f'Row {i}: manual_gt is empty.')
            continue

        gt_lower = raw_gt.lower()
        if gt_lower in ('0', 'false', 'no'):
            gt_val = 0
        elif gt_lower in ('1', 'true', 'yes'):
            gt_val = 1
        else:
            skipped += 1
            errors.append(f'Row {i}: manual_gt "{raw_gt}" is not 0 or 1.')
            continue

        # --- update DB ---
        affected = CXRStudy.objects.filter(accession_no=acc_int).update(gt_manual=gt_val)
        if affected:
            updated += 1
        else:
            skipped += 1
            errors.append(f'Row {i}: accession {acc_int} not found in database.')

    # Clear session data
    request.session.pop('gt_upload_rows', None)
    request.session.pop('gt_upload_columns', None)

    return JsonResponse({
        'updated': updated,
        'skipped': skipped,
        'total': len(rows),
        'errors': errors[:50],  # cap to avoid huge payloads
    })
