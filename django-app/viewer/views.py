"""
Views for the CXR Database Viewer/Editor app.

Provides a paginated, sortable, searchable table view of CXRStudy records
with inline editing, detail view, CSV export, and delete capabilities.
"""

import csv
import json

from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.db.models import Q, Count, Avg
from django.core.paginator import Paginator
from django.contrib.auth.decorators import login_required, user_passes_test

from upload.models import CXRStudy


def _is_admin(user):
    return user.is_superuser or user.groups.filter(name='admins').exists()

admin_required = user_passes_test(_is_admin)


# Columns shown in the list table — order matters
TABLE_COLUMNS = [
    ('accession_no', 'Accession No'),
    ('procedure_start_date', 'Procedure Date'),
    ('created_at', 'Added'),
    ('workplace', 'Workplace'),
    ('gt_llm', 'GT LLM'),
    ('lunit_binarised', 'Lunit Bin'),
    ('gt_manual', 'Manual GT'),
    ('atelectasis', 'Atel'),
    ('calcification', 'Calc'),
    ('cardiomegaly', 'Cardio'),
    ('consolidation', 'Consol'),
    ('fibrosis', 'Fibro'),
    ('mediastinal_widening', 'Med Wid'),
    ('nodule', 'Nodule'),
    ('pleural_effusion', 'Pl Eff'),
    ('pneumoperitoneum', 'Pneumop'),
    ('pneumothorax', 'Pneumot'),
]

# All editable fields (grouped for the detail/edit modal)
FIELD_GROUPS = {
    'Identifiers': [
        'accession_no', 'study_id', 'study_id_anonymized',
    ],
    'Patient': [
        'patient_name', 'patient_id', 'patient_age', 'patient_gender',
    ],
    'Study': [
        'study_description', 'instances', 'workplace', 'medical_location_name',
    ],
    'Lunit AI Scores': [
        'abnormal', 'atelectasis', 'calcification', 'cardiomegaly',
        'consolidation', 'fibrosis', 'mediastinal_widening', 'nodule',
        'pleural_effusion', 'pneumoperitoneum', 'pneumothorax', 'tuberculosis',
    ],
    'Grading': [
        'gt_manual', 'gt_llm', 'lunit_binarised', 'llm_grade',
    ],
    'LLM Findings': [
        'atelectasis_llm', 'calcification_llm', 'cardiomegaly_llm',
        'consolidation_llm', 'fibrosis_llm', 'mediastinal_widening_llm',
        'nodule_llm', 'pleural_effusion_llm', 'pneumoperitoneum_llm',
        'pneumothorax_llm', 'tb_llm',
    ],
    'Reports': [
        'text_report', 'ai_report',
    ],
    'Timing': [
        'procedure_start_date', 'procedure_end_date',
        'time_end_to_end_seconds', 'time_to_clinical_decision_seconds',
    ],
    'Metadata': [
        'ai_priority', 'feedback', 'comments', 'status',
        'processing_batch_id', 'created_at', 'updated_at',
    ],
}

# Fields that cannot be edited through the UI
READONLY_FIELDS = {'accession_no', 'created_at', 'updated_at'}

# Sortable columns
SORTABLE_FIELDS = {col[0] for col in TABLE_COLUMNS}

# Filterable fields shown as dropdowns
FILTER_FIELDS = [
    ('workplace', 'Workplace'),
    ('gt_llm', 'GT LLM'),
    ('lunit_binarised', 'Lunit Bin'),
    ('gt_manual', 'Manual GT'),
    ('llm_grade', 'LLM Grade'),
    ('ai_priority', 'AI Priority'),
]


def _get_field_meta(field_name):
    """Return (verbose_name, field_type) for a model field."""
    try:
        field = CXRStudy._meta.get_field(field_name)
        return field.verbose_name, field.get_internal_type()
    except Exception:
        return field_name, 'CharField'


@login_required
@admin_required
def index(request):
    """Main database viewer page with paginated table."""
    qs = CXRStudy.objects.all()

    # --- Search ---
    search = request.GET.get('q', '').strip()
    if search:
        qs = qs.filter(
            Q(accession_no__icontains=search) |
            Q(patient_name__icontains=search) |
            Q(patient_id__icontains=search) |
            Q(text_report__icontains=search) |
            Q(workplace__icontains=search)
        )

    # --- Filters ---
    active_filters = {}
    for field_name, _ in FILTER_FIELDS:
        val = request.GET.get(f'f_{field_name}', '')
        if val != '':
            active_filters[field_name] = val
            if val == '__null__':
                qs = qs.filter(**{f'{field_name}__isnull': True})
            elif val == '__notnull__':
                qs = qs.filter(**{f'{field_name}__isnull': False})
            else:
                qs = qs.filter(**{field_name: val})

    # --- Date range filters ---
    DATE_RANGE_FIELDS = [
        ('procedure_start_date', 'Procedure Date'),
        ('created_at', 'Date Added'),
    ]
    date_filters = {}
    for field_name, label in DATE_RANGE_FIELDS:
        from_val = request.GET.get(f'd_{field_name}_from', '').strip()
        to_val = request.GET.get(f'd_{field_name}_to', '').strip()
        if from_val:
            qs = qs.filter(**{f'{field_name}__date__gte': from_val})
            date_filters[f'{field_name}_from'] = from_val
            active_filters[f'd_{field_name}_from'] = from_val
        if to_val:
            qs = qs.filter(**{f'{field_name}__date__lte': to_val})
            date_filters[f'{field_name}_to'] = to_val
            active_filters[f'd_{field_name}_to'] = to_val

    # --- Sorting ---
    sort = request.GET.get('sort', '-created_at')
    sort_field = sort.lstrip('-')
    if sort_field not in SORTABLE_FIELDS:
        sort = '-created_at'
    qs = qs.order_by(sort)

    # --- All filtered IDs (for "select all filtered" feature) ---
    all_filtered_ids = list(qs.values_list('accession_no', flat=True))

    # --- Pagination ---
    per_page = int(request.GET.get('per_page', 50))
    per_page = min(max(per_page, 10), 500)
    paginator = Paginator(qs, per_page)
    page_num = request.GET.get('page', 1)
    page = paginator.get_page(page_num)

    # --- Summary stats ---
    total = paginator.count
    stats = CXRStudy.objects.aggregate(
        total=Count('accession_no'),
        avg_abnormal=Avg('abnormal'),
        gt_llm_pos=Count('accession_no', filter=Q(gt_llm=1)),
        lunit_pos=Count('accession_no', filter=Q(lunit_binarised=1)),
    )

    # --- Filter options (distinct values) ---
    filter_options = {}
    for field_name, label in FILTER_FIELDS:
        vals = list(CXRStudy.objects
                    .values_list(field_name, flat=True)
                    .distinct()
                    .order_by(field_name))
        filter_options[field_name] = {
            'label': label,
            'values': vals,
            'selected': active_filters.get(field_name, ''),
            'has_nulls': None in vals,
        }

    context = {
        'page': page,
        'columns': TABLE_COLUMNS,
        'search': search,
        'sort': sort,
        'per_page': per_page,
        'total': total,
        'stats': stats,
        'filter_options': filter_options,
        'active_filters': active_filters,
        'date_filters': date_filters,
        'all_filtered_ids': json.dumps(all_filtered_ids),
    }
    return render(request, 'viewer/db_viewer.html', context)


@login_required
@admin_required
@require_http_methods(["GET"])
def study_detail(request, accession_no):
    """Return full study data as JSON."""
    study = get_object_or_404(CXRStudy, accession_no=accession_no)

    groups = {}
    for group_name, fields in FIELD_GROUPS.items():
        group_fields = []
        for f in fields:
            verbose, ftype = _get_field_meta(f)
            val = getattr(study, f, None)
            # Serialise datetimes
            if hasattr(val, 'isoformat'):
                val = val.isoformat()
            group_fields.append({
                'name': f,
                'label': str(verbose),
                'value': val,
                'type': ftype,
                'readonly': f in READONLY_FIELDS,
            })
        groups[group_name] = group_fields

    return JsonResponse({'accession_no': study.accession_no, 'groups': groups})


@login_required
@admin_required
@csrf_exempt
@require_http_methods(["POST"])
def study_update(request, accession_no):
    """Update editable fields on a study."""
    study = get_object_or_404(CXRStudy, accession_no=accession_no)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    updated = []
    for key, value in data.items():
        if key in READONLY_FIELDS:
            continue
        if not hasattr(study, key):
            continue
        # Coerce empty strings to None for nullable fields
        if value == '' or value is None:
            value = None
        setattr(study, key, value)
        updated.append(key)

    if updated:
        study.save(update_fields=updated + ['updated_at'])

    return JsonResponse({'success': True, 'updated_fields': updated})


@login_required
@admin_required
@csrf_exempt
@require_http_methods(["POST"])
def study_delete(request, accession_no):
    """Delete a study record."""
    study = get_object_or_404(CXRStudy, accession_no=accession_no)
    study.delete()
    return JsonResponse({'success': True})


@login_required
@admin_required
@csrf_exempt
@require_http_methods(["POST"])
def bulk_delete(request):
    """Delete multiple study records."""
    try:
        data = json.loads(request.body)
        ids = data.get('accession_nos', [])
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    if not ids:
        return JsonResponse({'error': 'No accession numbers provided'}, status=400)

    count, _ = CXRStudy.objects.filter(accession_no__in=ids).delete()
    return JsonResponse({'success': True, 'deleted': count})


@login_required
@admin_required
@require_http_methods(["GET"])
def export_csv(request):
    """Export current filtered/searched queryset as CSV download."""
    qs = CXRStudy.objects.all()

    search = request.GET.get('q', '').strip()
    if search:
        qs = qs.filter(
            Q(accession_no__icontains=search) |
            Q(patient_name__icontains=search) |
            Q(patient_id__icontains=search) |
            Q(text_report__icontains=search) |
            Q(workplace__icontains=search)
        )

    for field_name, _ in FILTER_FIELDS:
        val = request.GET.get(f'f_{field_name}', '')
        if val != '':
            if val == '__null__':
                qs = qs.filter(**{f'{field_name}__isnull': True})
            else:
                qs = qs.filter(**{field_name: val})

    sort = request.GET.get('sort', '-created_at')
    sort_field = sort.lstrip('-')
    if sort_field not in SORTABLE_FIELDS:
        sort = '-created_at'
    qs = qs.order_by(sort)

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="cxr_studies_export.csv"'

    # Use all model fields
    field_names = [f.name for f in CXRStudy._meta.get_fields() if hasattr(f, 'column')]
    writer = csv.writer(response)
    writer.writerow(field_names)

    for study in qs.iterator():
        row = []
        for f in field_names:
            val = getattr(study, f, '')
            if hasattr(val, 'isoformat'):
                val = val.isoformat()
            if val is None:
                val = ''
            row.append(val)
        writer.writerow(row)

    return response
