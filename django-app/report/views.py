"""
Views for the CXR Report Viewer app.

Generates analysis reports from database records filtered by date range,
computing the same metrics as the upload processing pipeline:
accuracy, confusion matrix, sensitivity/specificity, false negatives.
"""

import csv
import json
import statistics
from collections import defaultdict
from datetime import date, datetime, timedelta

from django.shortcuts import render
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_http_methods
from django.db.models import Q, Count, Avg
from django.contrib.auth.decorators import login_required
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.conf import settings

from upload.models import CXRStudy

# Lunit score thresholds (mirrored from combined_server.py)
THRESHOLDS = {
    'default': {
        'atelectasis': 10,
        'calcification': 10,
        'cardiomegaly': 10,
        'consolidation': 10,
        'fibrosis': 10,
        'mediastinal_widening': 10,
        'nodule': 15,
        'pleural_effusion': 10,
        'pneumoperitoneum': 10,
        'pneumothorax': 10,
    },
    'YIS': {
        'nodule': 5,
    },
}

# Map workplace codes to short names (from class_process_carpl.py)
WORKPLACE_MAP = {
    'GLCR01': 'GEY', 'KALCR01': 'KAL', 'SEMCR01': 'SEM',
    'TPYCR01': 'TPY', 'KHACR01': 'KHA', 'WDLCR01': 'WDL',
    'HOUCR01': 'HOU', 'AMKCR01': 'AMK', 'YISCR01': 'YIS',
    'SERCR01': 'SER',
}

DIAGNOSIS_FIELDS = [
    'atelectasis', 'calcification', 'cardiomegaly', 'consolidation',
    'fibrosis', 'mediastinal_widening', 'nodule', 'pleural_effusion',
    'pneumoperitoneum', 'pneumothorax',
]

DEFAULT_FROM_DATE = '2025-12-12'


# ──────────────────────────────────────────────
# Helper functions
# ──────────────────────────────────────────────

def _short_site(workplace):
    return WORKPLACE_MAP.get(workplace, 'OTH')


def _get_site_thresholds(site_short):
    """Return merged threshold dict for a site."""
    base = dict(THRESHOLDS['default'])
    if site_short in THRESHOLDS:
        for k, v in THRESHOLDS[site_short].items():
            base[k] = v
    return base


def _lunit_positive(study, thresholds):
    """Check if any Lunit score exceeds the threshold for this study."""
    for field, thresh in thresholds.items():
        val = getattr(study, field, None)
        if val is not None and val > thresh:
            return True
    return False


def _compute_metrics(studies):
    """
    Compute confusion matrix and derived metrics from a list of studies.
    Uses gt_llm as ground truth and lunit_binarised as prediction.
    """
    tp = tn = fp = fn = 0
    for s in studies:
        gt = s.gt_llm
        pred = s.lunit_binarised
        if gt is None or pred is None:
            continue
        if gt == 1 and pred == 1:
            tp += 1
        elif gt == 0 and pred == 0:
            tn += 1
        elif gt == 0 and pred == 1:
            fp += 1
        elif gt == 1 and pred == 0:
            fn += 1

    total = tp + tn + fp + fn
    accuracy = (tp + tn) / total if total else 0
    sensitivity = tp / (tp + fn) if (tp + fn) else 0
    specificity = tn / (tn + fp) if (tn + fp) else 0
    ppv = tp / (tp + fp) if (tp + fp) else 0
    npv = tn / (tn + fn) if (tn + fn) else 0
    roc_auc = (sensitivity + specificity) / 2

    return {
        'n': total,
        'tp': tp, 'tn': tn, 'fp': fp, 'fn': fn,
        'accuracy': accuracy,
        'sensitivity': sensitivity,
        'specificity': specificity,
        'ppv': ppv,
        'npv': npv,
        'roc_auc': roc_auc,
        'pct_normal': (tn + fn) / total * 100 if total else 0,
    }


def _fmt_seconds(seconds):
    """Format seconds as a human-readable string (e.g. '2m 30s' or '1h 15m')."""
    if seconds is None:
        return '—'
    total = int(round(seconds))
    if total < 60:
        return f'{total}s'
    minutes, secs = divmod(total, 60)
    if minutes < 60:
        return f'{minutes}m {secs:02d}s'
    hours, mins = divmod(minutes, 60)
    return f'{hours}h {mins:02d}m'


def _compute_time_stats(study_list):
    """
    Compute time analysis stats from CXRStudy records.
    Returns dict with median/P25/P75 for time_to_clinical_decision and time_end_to_end,
    plus raw values for client-side box plot rendering.
    """
    tcd_vals = sorted([s.time_to_clinical_decision_seconds for s in study_list
                if s.time_to_clinical_decision_seconds is not None])
    tee_vals = sorted([s.time_end_to_end_seconds for s in study_list
                if s.time_end_to_end_seconds is not None and s.time_end_to_end_seconds > 0])

    result = {
        'tcd_count': len(tcd_vals),
        'tee_count': len(tee_vals),
    }

    if tcd_vals:
        q = statistics.quantiles(tcd_vals, n=4) if len(tcd_vals) >= 2 else [tcd_vals[0]] * 3
        result['tcd_mean'] = statistics.mean(tcd_vals)
        result['tcd_p25'] = q[0]
        result['tcd_median'] = q[1] if len(q) > 1 else tcd_vals[0]
        result['tcd_p75'] = q[2] if len(q) > 2 else tcd_vals[-1]
        result['tcd_min'] = min(tcd_vals)
        result['tcd_max'] = max(tcd_vals)
        result['tcd_vals'] = [round(v, 1) for v in tcd_vals]
        result['tcd_more_than_5mins'] = sum(1 for v in tcd_vals if v > 300)
    else:
        result['tcd_mean'] = None
        result['tcd_p25'] = None
        result['tcd_median'] = None
        result['tcd_p75'] = None
        result['tcd_min'] = None
        result['tcd_max'] = None
        result['tcd_vals'] = []
        result['tcd_more_than_5mins'] = None

    if tee_vals:
        q = statistics.quantiles(tee_vals, n=4) if len(tee_vals) >= 2 else [tee_vals[0]] * 3
        result['tee_mean'] = statistics.mean(tee_vals)
        result['tee_p25'] = q[0]
        result['tee_median'] = q[1] if len(q) > 1 else tee_vals[0]
        result['tee_p75'] = q[2] if len(q) > 2 else tee_vals[-1]
        result['tee_min'] = min(tee_vals)
        result['tee_max'] = max(tee_vals)
        result['tee_vals'] = [round(v, 1) for v in tee_vals]
        result['tee_more_than_5mins'] = sum(1 for v in tee_vals if v > 300)
    else:
        result['tee_mean'] = None
        result['tee_p25'] = None
        result['tee_median'] = None
        result['tee_p75'] = None
        result['tee_min'] = None
        result['tee_max'] = None
        result['tee_vals'] = []
        result['tee_more_than_5mins'] = None

    return result


def _compute_weekly_site_metrics(study_list):
    """
    Group studies by ISO week and site, compute sensitivity/specificity per bucket.
    Returns { weeks: ['W01 Jan', ...], sites: ['AMK', ...], sensitivity: {site: [val,...]}, specificity: {site: [val,...]} }
    """
    # Bucket studies by (year-week, site)
    buckets = defaultdict(lambda: defaultdict(list))   # {week_key: {site: [studies]}}
    for s in study_list:
        if s.procedure_start_date is None:
            continue
        iso = s.procedure_start_date.isocalendar()
        week_key = (iso[0], iso[1])  # (year, week_number)
        site = WORKPLACE_MAP.get(s.workplace, 'OTH') if s.workplace else 'OTH'
        buckets[week_key][site].append(s)

    if not buckets:
        return None

    # Sort weeks chronologically
    sorted_weeks = sorted(buckets.keys())

    # Build human-readable week labels using the Monday of each ISO week
    week_labels = []
    for yr, wk in sorted_weeks:
        monday = datetime.strptime(f'{yr}-W{wk:02d}-1', '%G-W%V-%u').date()
        week_labels.append(monday.strftime('%d %b'))

    # Collect all sites that appear
    all_sites = sorted({site for wk_data in buckets.values() for site in wk_data})

    sensitivity = {site: [] for site in all_sites}
    specificity = {site: [] for site in all_sites}

    for week_key in sorted_weeks:
        wk_data = buckets[week_key]
        for site in all_sites:
            studies = wk_data.get(site, [])
            if studies:
                m = _compute_metrics(studies)
                # Only include if there's enough data for the metric to be meaningful
                sensitivity[site].append(round(m['sensitivity'] * 100, 1) if (m['tp'] + m['fn']) > 0 else None)
                specificity[site].append(round(m['specificity'] * 100, 1) if (m['tn'] + m['fp']) > 0 else None)
            else:
                sensitivity[site].append(None)
                specificity[site].append(None)

    return {
        'weeks': week_labels,
        'sites': all_sites,
        'sensitivity': sensitivity,
        'specificity': specificity,
    }


def _compute_weekly_overall_auc(study_list):
    """
    Compute overall ROC-AUC per ISO week (all sites combined) and
    a 95% CI based on all weeks except the last one.
    Returns None if fewer than 1 week of data.
    """
    import math as _math

    buckets = defaultdict(list)  # {(year, week): [studies]}
    for s in study_list:
        if s.procedure_start_date is None:
            continue
        iso = s.procedure_start_date.isocalendar()
        buckets[(iso[0], iso[1])].append(s)

    if not buckets:
        return None

    sorted_weeks = sorted(buckets.keys())

    week_labels = []
    auc_values = []  # one ROC-AUC per week
    for yr, wk in sorted_weeks:
        monday = datetime.strptime(f'{yr}-W{wk:02d}-1', '%G-W%V-%u').date()
        week_labels.append(monday.strftime('%d %b'))
        m = _compute_metrics(buckets[(yr, wk)])
        auc_values.append(round(m['roc_auc'] * 100, 1) if m['n'] > 0 else None)

    # 95% CI from all weeks except the last
    ci_lower = None
    ci_upper = None
    if len(sorted_weeks) >= 2:
        baseline = [v for v in auc_values[:-1] if v is not None]
        if len(baseline) >= 2:
            mean_auc = statistics.mean(baseline)
            std_auc = statistics.stdev(baseline)
            se = std_auc / _math.sqrt(len(baseline))
            ci_lower = round(mean_auc - 1.96 * se, 1)
            ci_upper = round(mean_auc + 1.96 * se, 1)

    return {
        'weeks': week_labels,
        'auc': auc_values,
        'ci_lower': ci_lower,
        'ci_upper': ci_upper,
    }


def _compute_gt_metrics(studies, gt_field, pred_field='lunit_binarised'):
    """
    Compute confusion matrix metrics using an arbitrary ground-truth field.
    Skips rows where either gt or pred is None.
    """
    tp = tn = fp = fn = 0
    for s in studies:
        gt = getattr(s, gt_field, None)
        pred = getattr(s, pred_field, None)
        if gt is None or pred is None:
            continue
        if gt == 1 and pred == 1:
            tp += 1
        elif gt == 0 and pred == 0:
            tn += 1
        elif gt == 0 and pred == 1:
            fp += 1
        elif gt == 1 and pred == 0:
            fn += 1
    total = tp + tn + fp + fn
    accuracy = (tp + tn) / total if total else 0
    sensitivity = tp / (tp + fn) if (tp + fn) else 0
    specificity = tn / (tn + fp) if (tn + fp) else 0
    ppv = tp / (tp + fp) if (tp + fp) else 0
    npv = tn / (tn + fn) if (tn + fn) else 0
    roc_auc = (sensitivity + specificity) / 2
    return {
        'n': total, 'tp': tp, 'tn': tn, 'fp': fp, 'fn': fn,
        'accuracy': accuracy, 'sensitivity': sensitivity,
        'specificity': specificity, 'ppv': ppv, 'npv': npv,
        'roc_auc': roc_auc,
        'pct_normal': (tn + fn) / total * 100 if total else 0,
    }


def _compute_manual_vs_llm(study_list):
    """
    For the subset of studies that have a manual GT, compute:
     - Per-site LLM-vs-Lunit metrics (gt_llm as GT)
     - Per-site Manual-vs-Lunit metrics (gt_manual as GT)
     - Overall agreement between manual GT and LLM GT
     - McNemar's test comparing the two GT methods against Lunit
    Returns None if no studies have gt_manual.
    """
    subset = [s for s in study_list if s.gt_manual is not None]
    if not subset:
        return None

    # Group by site
    workplaces = {}
    for s in subset:
        site = WORKPLACE_MAP.get(s.workplace, 'OTH') if s.workplace else 'OTH'
        workplaces.setdefault(site, []).append(s)

    llm_site = {}
    manual_site = {}
    for site in sorted(workplaces.keys()):
        llm_site[site] = _compute_gt_metrics(workplaces[site], 'gt_llm')
        manual_site[site] = _compute_gt_metrics(workplaces[site], 'gt_manual')

    llm_overall = _compute_gt_metrics(subset, 'gt_llm')
    manual_overall = _compute_gt_metrics(subset, 'gt_manual')

    # Agreement between manual GT and LLM GT
    agree_tp = agree_tn = agree_fp = agree_fn = 0
    for s in subset:
        m = s.gt_manual
        l = s.gt_llm
        if m is None or l is None:
            continue
        if m == 1 and l == 1:
            agree_tp += 1
        elif m == 0 and l == 0:
            agree_tn += 1
        elif m == 0 and l == 1:
            agree_fp += 1
        elif m == 1 and l == 0:
            agree_fn += 1
    agree_total = agree_tp + agree_tn + agree_fp + agree_fn
    agreement_pct = (agree_tp + agree_tn) / agree_total * 100 if agree_total else 0

    # Cohen's kappa
    if agree_total > 0:
        po = (agree_tp + agree_tn) / agree_total
        p_yes = ((agree_tp + agree_fp) / agree_total) * ((agree_tp + agree_fn) / agree_total)
        p_no = ((agree_tn + agree_fn) / agree_total) * ((agree_tn + agree_fp) / agree_total)
        pe = p_yes + p_no
        kappa = (po - pe) / (1 - pe) if pe < 1 else 0
    else:
        kappa = 0

    # McNemar's test: compare manual-vs-lunit correctness against llm-vs-lunit correctness
    # b = manual correct & llm incorrect, c = manual incorrect & llm correct
    b = 0  # manual correct, LLM wrong
    c = 0  # manual wrong, LLM correct
    for s in subset:
        pred = s.lunit_binarised
        gt_m = s.gt_manual
        gt_l = s.gt_llm
        if pred is None or gt_m is None or gt_l is None:
            continue
        manual_correct = (gt_m == pred)
        llm_correct = (gt_l == pred)
        if manual_correct and not llm_correct:
            b += 1
        elif not manual_correct and llm_correct:
            c += 1

    # Exact McNemar p-value using binomial distribution
    import math
    n_disc = b + c
    if n_disc > 0:
        # Two-sided exact test: p = 2 * sum of binomial(n_disc, k, 0.5) for k=0..min(b,c)
        min_bc = min(b, c)
        p_val = 0.0
        for k in range(min_bc + 1):
            p_val += math.comb(n_disc, k) * (0.5 ** n_disc)
        p_val = min(p_val * 2, 1.0)
        statistic = min_bc
    else:
        p_val = 1.0
        statistic = 0

    # ── False negatives (LLM=0, manual_gt=1) and false positives (LLM=1, manual_gt=0) ──
    fn_cases = [s for s in subset if s.gt_llm == 0 and s.gt_manual == 1]
    fp_cases = [s for s in subset if s.gt_llm == 1 and s.gt_manual == 0]

    def _case_detail(s):
        highest_finding = ''
        highest_score = 0
        for f in DIAGNOSIS_FIELDS:
            val = getattr(s, f, None) or 0
            if val > highest_score:
                highest_score = val
                highest_finding = f.replace('_', ' ').title()
        return {
            'accession_no': s.accession_no,
            'workplace': _short_site(s.workplace) if s.workplace else '—',
            'procedure_date': s.procedure_start_date.strftime('%d %b %Y') if s.procedure_start_date else '—',
            'llm_grade': s.gt_llm,
            'manual_gt': s.gt_manual,
            'highest_finding': highest_finding,
            'highest_score': round(highest_score, 1),
            'text_report': (s.text_report or '')[:200],
        }

    fn_data = [_case_detail(s) for s in fn_cases]
    fp_data = [_case_detail(s) for s in fp_cases]

    return {
        'n': len(subset),
        'llm_site': llm_site,
        'manual_site': manual_site,
        'llm_overall': llm_overall,
        'manual_overall': manual_overall,
        'agreement_pct': round(agreement_pct, 1),
        'kappa': round(kappa, 3),
        'mcnemar': {
            'b': b,
            'c': c,
            'statistic': statistic,
            'p_value': round(p_val, 6),
            'significant': p_val < 0.05,
        },
        'false_negatives': fn_data,
        'fn_count': len(fn_cases),
        'false_positives': fp_data,
        'fp_count': len(fp_cases),
    }


def _build_report(studies, date_from, date_to):
    """Build the full analysis report dict from a queryset of studies."""
    study_list = list(studies)
    total = len(study_list)

    if total == 0:
        return {
            'summary': f'No records found for {date_from} to {date_to}.',
            'total': 0,
            'date_from': date_from,
            'date_to': date_to,
        }

    # ── Overall metrics ──
    overall = _compute_metrics(study_list)

    # ── Per-workplace breakdown ──
    workplaces = {}
    for s in study_list:
        site = _short_site(s.workplace) if s.workplace else 'OTH'
        workplaces.setdefault(site, []).append(s)

    site_metrics = {}
    for site in sorted(workplaces.keys()):
        site_metrics[site] = _compute_metrics(workplaces[site])

    # ── Text report (mimics txt_initial_metrics + txt_stats_accuracy) ──
    # Determine actual first/last procedure dates from the data
    proc_dates = [s.procedure_start_date for s in study_list if s.procedure_start_date is not None]
    if proc_dates:
        actual_from = min(proc_dates).strftime('%d %b %Y')
        actual_to = max(proc_dates).strftime('%d %b %Y')
    else:
        actual_from, actual_to = date_from, date_to

    txt_lines = [
        f'# REVIEW FOR PERIOD: {actual_from} to {actual_to} (n={total})',
        '',
        '=== LLM vs LUNIT ANALYSIS (BY WORKPLACE) ===',
        f'{"Site":<8} {"n":>5} {"Acc":>7} {"AUC":>7} {"Sens":>7} {"Spec":>7} {"PPV":>7} {"NPV":>7} {"TP":>5} {"TN":>5} {"FP":>5} {"FN":>5} {"%Norm":>7}',
        '-' * 94,
    ]
    for site in sorted(site_metrics.keys()):
        m = site_metrics[site]
        txt_lines.append(
            f'{site:<8} {m["n"]:>5} {m["accuracy"]:>7.3f} {m["roc_auc"]:>7.3f} '
            f'{m["sensitivity"]:>7.3f} {m["specificity"]:>7.3f} {m["ppv"]:>7.3f} '
            f'{m["npv"]:>7.3f} '
            f'{m["tp"]:>5} {m["tn"]:>5} {m["fp"]:>5} {m["fn"]:>5} {m["pct_normal"]:>6.1f}%'
        )

    txt_lines += [
        '-' * 94,
        f'OVERALL  {overall["n"]:>5} {overall["accuracy"]:>7.3f} {overall["roc_auc"]:>7.3f} '
        f'{overall["sensitivity"]:>7.3f} {overall["specificity"]:>7.3f} {overall["ppv"]:>7.3f} '
        f'{overall["npv"]:>7.3f} '
        f'{overall["tp"]:>5} {overall["tn"]:>5} {overall["fp"]:>5} {overall["fn"]:>5} {overall["pct_normal"]:>6.1f}%',
    ]

    # ── Time stats ──
    time_stats = _compute_time_stats(study_list)

    txt_lines += [
        '',
        '=== TIME ANALYSIS ===',
    ]
    if time_stats['tcd_count'] > 0:
        txt_lines += [
            f'Time to Clinical Decision (n={time_stats["tcd_count"]}):',
            f'(time from Exam End to AI Flag Received (i.e. case processed), otherwise Report TAT (i.e. case not processed))',
            f'  Median: {_fmt_seconds(time_stats["tcd_median"])}',
            f'  P25:    {_fmt_seconds(time_stats["tcd_p25"])}',
            f'  P75:    {_fmt_seconds(time_stats["tcd_p75"])}',
            f'  Range:  {_fmt_seconds(time_stats["tcd_min"])} — {_fmt_seconds(time_stats["tcd_max"])}',
            f'  >5min:  {time_stats["tcd_more_than_5mins"]} cases',
        ]
    else:
        txt_lines.append('Time to Clinical Decision: no data')

    if time_stats['tee_count'] > 0:
        txt_lines += [
            f'',
            f'End-to-End Server Time (n={time_stats["tee_count"]}):',
            f'(time from Exam End to AI Flag Received, excluding cases where the flag never made it)',
            f'  Median: {_fmt_seconds(time_stats["tee_median"])}',
            f'  P25:    {_fmt_seconds(time_stats["tee_p25"])}',
            f'  P75:    {_fmt_seconds(time_stats["tee_p75"])}',
            f'  Range:  {_fmt_seconds(time_stats["tee_min"])} — {_fmt_seconds(time_stats["tee_max"])}',
            f'  >5min:  {time_stats["tee_more_than_5mins"]} cases',
        ]
    else:
        txt_lines.append('End-to-End Server Time: no data')

    # ── Counts by gt_llm for quick summary ──
    gt_llm_pos = sum(1 for s in study_list if s.gt_llm == 1)
    lunit_pos = sum(1 for s in study_list if s.lunit_binarised == 1)
    graded = sum(1 for s in study_list if s.gt_llm is not None)

    # ── Weekly per-site metrics for trend charts ──
    weekly_metrics = _compute_weekly_site_metrics(study_list)

    # ── Weekly overall ROC-AUC trend ──
    weekly_auc = _compute_weekly_overall_auc(study_list)

    # ── Manual vs LLM GT analysis (only if manual GT exists) ──
    manual_vs_llm = _compute_manual_vs_llm(study_list)

    # Pre-format time values as min/sec strings for use in email/print templates
    time_stats['tcd_mean_fmt'] = _fmt_seconds(time_stats.get('tcd_mean'))
    time_stats['tcd_median_fmt'] = _fmt_seconds(time_stats.get('tcd_median'))
    time_stats['tcd_p25_fmt'] = _fmt_seconds(time_stats.get('tcd_p25'))
    time_stats['tcd_p75_fmt'] = _fmt_seconds(time_stats.get('tcd_p75'))
    time_stats['tee_mean_fmt'] = _fmt_seconds(time_stats.get('tee_mean'))
    time_stats['tee_median_fmt'] = _fmt_seconds(time_stats.get('tee_median'))
    time_stats['tee_p25_fmt'] = _fmt_seconds(time_stats.get('tee_p25'))
    time_stats['tee_p75_fmt'] = _fmt_seconds(time_stats.get('tee_p75'))

    return {
        'total': total,
        'date_from': date_from,
        'date_to': date_to,
        'overall': overall,
        'site_metrics': site_metrics,
        'weekly_site_metrics': weekly_metrics,
        'weekly_auc': weekly_auc,
        'time_stats': time_stats,
        'manual_vs_llm': manual_vs_llm,
        'txt_report': '\n'.join(txt_lines),
        'gt_llm_pos': gt_llm_pos,
        'lunit_pos': lunit_pos,
        'graded': graded,
        'ungraded': total - graded,
    }


# ──────────────────────────────────────────────
# Views
# ──────────────────────────────────────────────

@login_required
def index(request):
    """Render the report form page."""
    today = date.today().isoformat()
    return render(request, 'report/report.html', {
        'default_from': DEFAULT_FROM_DATE,
        'default_to': today,
    })


@login_required
@require_http_methods(["GET"])
def generate_report(request):
    """Generate report JSON for the given date range."""
    date_from = request.GET.get('date_from', DEFAULT_FROM_DATE)
    date_to = request.GET.get('date_to', date.today().isoformat())

    qs = CXRStudy.objects.all()

    # Filter by procedure_start_date if available, else created_at
    qs = qs.filter(
        Q(procedure_start_date__date__gte=date_from) &
        Q(procedure_start_date__date__lte=date_to)
    )

    report = _build_report(qs, date_from, date_to)
    return JsonResponse(report)


@login_required
@require_http_methods(["GET"])
def export_report_csv(request):
    """Export the filtered studies as CSV."""
    date_from = request.GET.get('date_from', DEFAULT_FROM_DATE)
    date_to = request.GET.get('date_to', date.today().isoformat())

    qs = CXRStudy.objects.filter(
        procedure_start_date__date__gte=date_from,
        procedure_start_date__date__lte=date_to,
    ).order_by('procedure_start_date')

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="cxr_report_{date_from}_to_{date_to}.csv"'

    fields = [
        'accession_no', 'workplace', 'procedure_start_date',
        'gt_llm', 'lunit_binarised', 'llm_grade',
        'abnormal', 'atelectasis', 'calcification', 'cardiomegaly',
        'consolidation', 'fibrosis', 'mediastinal_widening', 'nodule',
        'pleural_effusion', 'pneumoperitoneum', 'pneumothorax',
        'text_report',
    ]

    writer = csv.writer(response)
    writer.writerow(fields)
    for s in qs:
        writer.writerow([getattr(s, f, '') for f in fields])

    return response


@login_required
@require_http_methods(["GET"])
def export_false_negatives_csv(request):
    """Export false negative cases (LLM=0, manual_gt=1) as CSV."""
    date_from = request.GET.get('date_from', DEFAULT_FROM_DATE)
    date_to = request.GET.get('date_to', date.today().isoformat())

    qs = CXRStudy.objects.filter(
        procedure_start_date__date__gte=date_from,
        procedure_start_date__date__lte=date_to,
        gt_llm=0,
        gt_manual=1,
    ).order_by('procedure_start_date')

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="false_negatives_{date_from}_to_{date_to}.csv"'

    fields = [
        'accession_no', 'workplace', 'procedure_start_date',
        'gt_llm', 'gt_manual', 'lunit_binarised',
        'atelectasis', 'calcification', 'cardiomegaly', 'consolidation',
        'fibrosis', 'mediastinal_widening', 'nodule', 'pleural_effusion',
        'pneumoperitoneum', 'pneumothorax',
        'text_report',
    ]

    writer = csv.writer(response)
    writer.writerow(fields)
    for s in qs:
        writer.writerow([getattr(s, f, '') for f in fields])

    return response


@login_required
@require_http_methods(["GET"])
def export_false_positives_csv(request):
    """Export false positive cases (LLM=1, manual_gt=0) as CSV."""
    date_from = request.GET.get('date_from', DEFAULT_FROM_DATE)
    date_to = request.GET.get('date_to', date.today().isoformat())

    qs = CXRStudy.objects.filter(
        procedure_start_date__date__gte=date_from,
        procedure_start_date__date__lte=date_to,
        gt_llm=1,
        gt_manual=0,
    ).order_by('procedure_start_date')

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="false_positives_{date_from}_to_{date_to}.csv"'

    fields = [
        'accession_no', 'workplace', 'procedure_start_date',
        'gt_llm', 'gt_manual', 'lunit_binarised',
        'atelectasis', 'calcification', 'cardiomegaly', 'consolidation',
        'fibrosis', 'mediastinal_widening', 'nodule', 'pleural_effusion',
        'pneumoperitoneum', 'pneumothorax',
        'text_report',
    ]

    writer = csv.writer(response)
    writer.writerow(fields)
    for s in qs:
        writer.writerow([getattr(s, f, '') for f in fields])

    return response


@login_required
@require_http_methods(["POST"])
def email_report(request):
    """Send the generated report as a styled HTML email to the provided addresses."""
    import re

    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'ok': False, 'error': 'Invalid JSON.'}, status=400)

    recipients_raw = body.get('recipients', '')
    report_data = body.get('report_data')
    note = body.get('note', '').strip()

    if not report_data:
        return JsonResponse({'ok': False, 'error': 'No report data provided.'}, status=400)

    # Parse comma/semicolon/newline-separated email addresses
    recipients = [e.strip() for e in re.split(r'[,;\n]+', recipients_raw) if e.strip()]
    # Basic email validation
    email_re = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')
    invalid = [e for e in recipients if not email_re.match(e)]
    if invalid:
        return JsonResponse({'ok': False, 'error': f'Invalid email(s): {", ".join(invalid)}'}, status=400)
    if not recipients:
        return JsonResponse({'ok': False, 'error': 'No recipients provided.'}, status=400)

    date_from = report_data.get('date_from', '?')
    date_to = report_data.get('date_to', '?')
    subject = f'PRIMER-LLM CXR Analysis Report \u2014 {date_from} to {date_to}'

    # Render the HTML email template
    html_content = render_to_string('report/email_report.html', {
        'data': report_data,
        'date_from': date_from,
        'date_to': date_to,
        'note': note,
    })

    # Plain-text fallback is just the txt_report
    text_content = report_data.get('txt_report', 'See HTML version of this email.')

    try:
        msg = EmailMultiAlternatives(
            subject=subject,
            body=text_content,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=recipients,
        )
        msg.attach_alternative(html_content, 'text/html')
        msg.send(fail_silently=False)
    except Exception as exc:
        return JsonResponse({'ok': False, 'error': f'Email send failed: {exc}'}, status=500)

    return JsonResponse({'ok': True, 'sent_to': recipients})


@login_required
@require_http_methods(["POST"])
def download_pdf(request):
    """Render the report as a print-ready HTML page (for browser Save-as-PDF)."""
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return HttpResponse('Invalid JSON.', status=400)

    report_data = body.get('report_data')
    if not report_data:
        return HttpResponse('No report data provided.', status=400)

    date_from = report_data.get('date_from', '?')
    date_to = report_data.get('date_to', '?')

    # Chart images captured client-side as base64 data URLs
    chart_images = body.get('chart_images', {})

    html = render_to_string('report/print_report.html', {
        'data': report_data,
        'date_from': date_from,
        'date_to': date_to,
        'chart_images': chart_images,
    })

    response = HttpResponse(html, content_type='text/html')
    return response
