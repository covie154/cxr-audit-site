/**
 * Report page – general functions.
 *
 * Depends on:
 *   - window.REPORT_CONFIG  (set by the template: urls, csrfToken)
 *   - drawBoxPlot, drawSiteTrendCharts  (from charts.js)
 */

let currentFrom = '', currentTo = '';

async function generateReport() {
    const dateFrom = document.getElementById('dateFrom').value;
    const dateTo   = document.getElementById('dateTo').value;
    if (!dateFrom || !dateTo) { alert('Please select both dates.'); return; }

    currentFrom = dateFrom; currentTo = dateTo;
    const btn = document.getElementById('generateBtn');
    const loading = document.getElementById('loadingBar');
    const results = document.getElementById('resultsSection');

    btn.disabled = true; loading.style.display = 'block'; results.style.display = 'none';

    try {
        const r = await fetch(`${window.REPORT_CONFIG.generateUrl}?date_from=${dateFrom}&date_to=${dateTo}`);
        if (!r.ok) throw new Error(`Server error ${r.status}`);
        renderReport(await r.json());
    } catch(e) { alert('Error: ' + e.message); }
    finally { btn.disabled = false; loading.style.display = 'none'; }
}

function renderReport(data) {
    document.getElementById('resultsSection').style.display = 'block';
    const o = data.overall || {};

    // Summary cards
    document.getElementById('summaryCards').innerHTML = `
        <div class="summary-card"><div class="value">${data.total}</div><div class="label">Total Studies</div></div>
        <div class="summary-card positive"><div class="value">${data.graded ?? '—'}</div><div class="label">Graded</div></div>
        <div class="summary-card"><div class="value">${o.accuracy.toFixed(3)}</div><div class="label">Accuracy</div></div>
        <div class="summary-card"><div class="value">${o.sensitivity.toFixed(3)}</div><div class="label">Sensitivity</div></div>
        <div class="summary-card"><div class="value">${o.specificity.toFixed(3)}</div><div class="label">Specificity</div></div>`;

    // Text report
    document.getElementById('txtReport').textContent = data.txt_report || 'No report available.';

    // Site table
    const tbody = document.getElementById('siteTableBody');
    tbody.innerHTML = '';
    for (const [site, m] of Object.entries(data.site_metrics || {})) tbody.innerHTML += siteRow(site, m, false);
    if (o.n) tbody.innerHTML += siteRow('OVERALL', o, true);

    // Site trend charts (weekly)
    drawSiteTrendCharts(data.weekly_site_metrics);

    // Overall ROC-AUC trend chart
    drawAucTrendChart(data.weekly_auc);

    // Manual vs LLM GT comparison
    renderGtCompare(data.manual_vs_llm);

    // Time analysis
    const ts = data.time_stats || {};
    const timeSec = document.getElementById('timeSection');
    const timeCards = document.getElementById('timeCards');
    if ((ts.tcd_count && ts.tcd_count > 0) || (ts.tee_count && ts.tee_count > 0)) {
        timeSec.style.display = 'block';
        let html = '';
        if (ts.tcd_count > 0) {
            html += `<div class="card" style="padding:16px;">
                <div style="font-weight:700;margin-bottom:4px;">Time to Clinical Decision</div>
                <div style="font-size:.82em;color:var(--c-text-muted);margin-bottom:12px;">n = ${ts.tcd_count}</div>
                <div style="display:flex;gap:20px;align-items:baseline;">
                    <div><span style="font-size:1.4em;font-weight:700;color:var(--c-primary);">${fmtSec(ts.tcd_median)}</span><br><span style="font-size:.76em;color:var(--c-text-muted);">Median</span></div>
                    <div><span style="font-size:1.1em;font-weight:600;color:var(--c-text-muted);">${fmtSec(ts.tcd_p25)}</span><br><span style="font-size:.76em;color:var(--c-text-muted);">P25</span></div>
                    <div><span style="font-size:1.1em;font-weight:600;color:var(--c-text-muted);">${fmtSec(ts.tcd_p75)}</span><br><span style="font-size:.76em;color:var(--c-text-muted);">P75</span></div>
                </div>
            </div>`;
        }
        if (ts.tee_count > 0) {
            html += `<div class="card" style="padding:16px;">
                <div style="font-weight:700;margin-bottom:4px;">End-to-End Server Time</div>
                <div style="font-size:.82em;color:var(--c-text-muted);margin-bottom:12px;">n = ${ts.tee_count}</div>
                <div style="display:flex;gap:20px;align-items:baseline;">
                    <div><span style="font-size:1.4em;font-weight:700;color:var(--c-primary);">${fmtSec(ts.tee_median)}</span><br><span style="font-size:.76em;color:var(--c-text-muted);">Median</span></div>
                    <div><span style="font-size:1.1em;font-weight:600;color:var(--c-text-muted);">${fmtSec(ts.tee_p25)}</span><br><span style="font-size:.76em;color:var(--c-text-muted);">P25</span></div>
                    <div><span style="font-size:1.1em;font-weight:600;color:var(--c-text-muted);">${fmtSec(ts.tee_p75)}</span><br><span style="font-size:.76em;color:var(--c-text-muted);">P75</span></div>
                    <div><span style="font-size:1.1em;font-weight:700;color:var(--c-danger);">${ts.tee_more_than_5mins ?? 0}</span><br><span style="font-size:.76em;color:var(--c-text-muted);">&gt; 5 min</span></div>
                </div>
            </div>`;
        }
        timeCards.innerHTML = html;
        drawBoxPlot(ts);
    } else {
        timeSec.style.display = 'none';
    }

    document.getElementById('resultsSection').scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function siteRow(site, m, overall) {
    const cls = overall ? ' class="overall-row"' : '';
    const auc = m.roc_auc != null ? m.roc_auc.toFixed(3) : '—';
    return `<tr${cls}><td>${site}</td><td>${m.n}</td>
        <td>${m.accuracy.toFixed(3)}</td><td>${auc}</td><td>${m.sensitivity.toFixed(3)}</td>
        <td>${m.specificity.toFixed(3)}</td><td>${m.ppv.toFixed(3)}</td>
        <td>${m.npv.toFixed(3)}</td><td>${m.tp}</td><td>${m.tn}</td><td>${m.fp}</td><td>${m.fn}</td>
        <td>${m.pct_normal.toFixed(1)}%</td></tr>`;
}

function escHtml(t) {
    const d = document.createElement('div');
    d.textContent = t || '';
    return d.innerHTML;
}

function fmtSec(s) {
    if (s == null) return '—';
    const total = Math.round(s);
    if (total < 60) return total + 's';
    const mins = Math.floor(total / 60), secs = total % 60;
    if (mins < 60) return mins + 'm ' + String(secs).padStart(2, '0') + 's';
    const hrs = Math.floor(mins / 60), rm = mins % 60;
    return hrs + 'h ' + String(rm).padStart(2, '0') + 'm';
}

function downloadCSV() {
    if (!currentFrom || !currentTo) return;
    window.location.href = `${window.REPORT_CONFIG.exportCsvUrl}?date_from=${currentFrom}&date_to=${currentTo}`;
}

function downloadFnCSV() {
    if (!currentFrom || !currentTo) return;
    window.location.href = `${window.REPORT_CONFIG.exportFnCsvUrl}?date_from=${currentFrom}&date_to=${currentTo}`;
}

function downloadFpCSV() {
    if (!currentFrom || !currentTo) return;
    window.location.href = `${window.REPORT_CONFIG.exportFpCsvUrl}?date_from=${currentFrom}&date_to=${currentTo}`;
}

function renderGtCompare(mvl) {
    const sec = document.getElementById('gtCompareSection');
    if (!mvl) { sec.style.display = 'none'; return; }
    sec.style.display = 'block';

    // Info banner
    document.getElementById('gtCompareInfo').innerHTML =
        `<strong>${mvl.n}</strong> studies have manual GT. ` +
        `Agreement between Manual &amp; LLM GT: <strong>${mvl.agreement_pct}%</strong> ` +
        `(Cohen's κ = <strong>${mvl.kappa}</strong>)`;

    // LLM vs Lunit table
    const llmBody = document.getElementById('llmVsLunitBody');
    llmBody.innerHTML = '';
    for (const [site, m] of Object.entries(mvl.llm_site || {})) llmBody.innerHTML += siteRow(site, m, false);
    if (mvl.llm_overall) llmBody.innerHTML += siteRow('OVERALL', mvl.llm_overall, true);

    // Manual vs Lunit table
    const manBody = document.getElementById('manualVsLunitBody');
    manBody.innerHTML = '';
    for (const [site, m] of Object.entries(mvl.manual_site || {})) manBody.innerHTML += siteRow(site, m, false);
    if (mvl.manual_overall) manBody.innerHTML += siteRow('OVERALL', mvl.manual_overall, true);

    // McNemar card
    const mc = mvl.mcnemar || {};
    const sigClass = mc.significant ? 'color:var(--c-danger);font-weight:700;' : 'color:var(--c-success);font-weight:700;';
    document.getElementById('mcnemarCard').innerHTML =
        `<div style="font-weight:700;margin-bottom:10px;">McNemar's Test</div>` +
        `<div style="font-size:.88em;color:var(--c-text-muted);margin-bottom:12px;">` +
        `Comparing Manual GT vs LLM GT accuracy against Lunit predictions.<br>` +
        `<em>b</em> = Manual correct &amp; LLM wrong: <strong>${mc.b}</strong> &nbsp;|&nbsp; ` +
        `<em>c</em> = Manual wrong &amp; LLM correct: <strong>${mc.c}</strong></div>` +
        `<div style="display:flex;gap:28px;flex-wrap:wrap;">` +
        `<div><span style="font-size:1.2em;font-weight:700;color:var(--c-primary);">${mc.p_value}</span><br><span style="font-size:.76em;color:var(--c-text-muted);">p-value</span></div>` +
        `<div><span style="font-size:1.2em;${sigClass}">${mc.significant ? 'Yes' : 'No'}</span><br><span style="font-size:.76em;color:var(--c-text-muted);">Significant (α=0.05)</span></div>` +
        `</div>`;

    // False negatives (LLM=0, Manual GT=1)
    const fns = mvl.false_negatives || [];
    const fnSec = document.getElementById('fnSection');
    fnSec.style.display = 'block';
    if (fns.length > 0) {
        document.getElementById('fnSummary').innerHTML =
            `<strong>${mvl.fn_count}</strong> cases where LLM graded Normal (0) but Manual GT is Abnormal (1).`;
        const fb = document.getElementById('fnTableBody'); fb.innerHTML = '';
        fns.slice(0, 100).forEach(c => {
            fb.innerHTML += `<tr><td>${c.accession_no}</td><td>${c.workplace}</td><td>${c.procedure_date}</td>
                <td>${c.highest_finding}</td><td>${c.highest_score}</td><td class="report-col">${escHtml(c.text_report)}</td></tr>`;
        });
        if (fns.length > 100) fb.innerHTML += `<tr><td colspan="6" style="text-align:center;color:#94a3b8;padding:12px;">First 100 of ${fns.length}. Download CSV for all.</td></tr>`;
    } else {
        document.getElementById('fnSummary').innerHTML = '🎉 <strong>No false negatives</strong> — LLM and Manual GT agree on all positive cases.';
        document.getElementById('fnTableBody').innerHTML = '';
    }

    // False positives (LLM=1, Manual GT=0)
    const fps = mvl.false_positives || [];
    const fpSec = document.getElementById('fpSection');
    fpSec.style.display = 'block';
    if (fps.length > 0) {
        document.getElementById('fpSummary').innerHTML =
            `<strong>${mvl.fp_count}</strong> cases where LLM graded Abnormal (1) but Manual GT is Normal (0).`;
        const fpb = document.getElementById('fpTableBody'); fpb.innerHTML = '';
        fps.slice(0, 100).forEach(c => {
            fpb.innerHTML += `<tr><td>${c.accession_no}</td><td>${c.workplace}</td><td>${c.procedure_date}</td>
                <td>${c.highest_finding}</td><td>${c.highest_score}</td><td class="report-col">${escHtml(c.text_report)}</td></tr>`;
        });
        if (fps.length > 100) fpb.innerHTML += `<tr><td colspan="6" style="text-align:center;color:#94a3b8;padding:12px;">First 100 of ${fps.length}. Download CSV for all.</td></tr>`;
    } else {
        document.getElementById('fpSummary').innerHTML = '🎉 <strong>No false positives</strong> — LLM and Manual GT agree on all negative cases.';
        document.getElementById('fpTableBody').innerHTML = '';
    }

    // Download buttons for FN/FP CSVs
    const gtDlRow = document.getElementById('gtDownloadRow');
    let dlHtml = '';
    if (fns.length > 0) dlHtml += `<button class="btn btn-warning" onclick="downloadFnCSV()">📥 Download False Negatives CSV</button>`;
    if (fps.length > 0) dlHtml += `<button class="btn btn-warning" onclick="downloadFpCSV()">📥 Download False Positives CSV</button>`;
    gtDlRow.innerHTML = dlHtml;
    gtDlRow.style.display = dlHtml ? 'flex' : 'none';
}
