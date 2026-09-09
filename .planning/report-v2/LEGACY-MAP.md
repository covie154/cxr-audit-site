# Legacy migration map

| Legacy section | Seed widgets | Treatment |
|---|---|---|
| Five summary cards | total, graded, accuracy, sensitivity, specificity | Same order; independent windows and eligible counts |
| Monospaced analysis report | none | Removed |
| Per-site table | site_metrics | Same measure family; ROC-AUC relabeled balanced accuracy |
| Weekly ROC-AUC chart | balanced_accuracy_trend | Same underlying metric family, correct label; remove calculated baseline band/banner |
| Weekly sensitivity/specificity | sensitivity_trend, specificity_trend | Site comparison defaults; weekly buckets |
| Time to Clinical Decision | clinical_decision | Summary statistics plus box plot |
| End-to-End Server Time | server_time | Summary plus box; fixed 300-second reference |
| LLM GT vs Lunit on manual subset | llm_lunit | Preserve restricted subset |
| Manual GT vs Lunit | manual_lunit | Manual reference |
| Agreement and kappa | agreement | Structured table |
| McNemar result | mcnemar | Registered paired-reference measurement; exact method verified with fixtures |
| LLM false negatives/positives vs manual | false_negatives, false_positives | Preserve analytic direction; paginated case tables; summary exports |
| CSV downloads | scoped compatibility actions | Preserve selected cohort; no implicit global date range |
| PDF/email | snapshot-based print HTML/email | Preserve existing workflows; all widget dates/filter metadata |

This is layout/feature parity, not a promise of identical clinical numbers. Uniform per-finding policies,
complete-score requirements, missing-value handling and null denominators can change outputs. The upcoming
new thresholds have not been supplied. Retain legacy defaults in the draft and do not publish them implicitly.

Source locations: django-app/report/templates/report/report.html; report/static/report/report.js,
report/static/report/charts.js; report/views.py (_compute_metrics, _compute_time_stats,
_compute_manual_vs_llm, download_pdf, email_report). No record-level data inspected.
