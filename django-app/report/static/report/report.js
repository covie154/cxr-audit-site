/**
 * Report page – general functions.
 *
 * Depends on:
 *   - window.REPORT_CONFIG  (set by the template: urls, csrfToken)
 *   - drawBoxPlot, drawSiteTrendCharts  (from charts.js)
 */

let currentFrom = '', currentTo = '';
let lastReportData = null;

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
    lastReportData = data;
    document.getElementById('resultsSection').style.display = 'block';
    document.getElementById('emailReportBtn').style.display = 'inline-flex';
    document.getElementById('downloadPdfBtn').style.display = 'inline-flex';
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
    if ((ts.tcd_count && ts.tcd_count > 0) || (ts.tee_count && ts.tee_count > 0)) {
        timeSec.style.display = 'block';
        const tcdCard = document.getElementById('tcdCard');
        const teeCard = document.getElementById('teeCard');
        if (ts.tcd_count > 0) {
            tcdCard.style.display = 'block';
            document.getElementById('tcdStats').innerHTML = `
                <div style="font-size:.78em;color:var(--c-text-muted);margin-bottom:8px;font-style:italic;">AI flag received date − End date for AI normal cases, TAT for all others (AI abnormal/not processed)</div>
                <div style="font-size:.82em;color:var(--c-text-muted);margin-bottom:12px;">n = ${ts.tcd_count}</div>
                <div style="display:flex;gap:20px;align-items:baseline;">
                    <div><span style="font-size:1.4em;font-weight:400;color:var(--c-primary);">${fmtSec(ts.tcd_mean)}</span><br><span style="font-size:.76em;color:var(--c-text-muted);">Mean</span></div>
                    <div><span style="font-size:1.4em;font-weight:700;color:var(--c-primary);">${fmtSec(ts.tcd_median)}</span><br><span style="font-size:.76em;color:var(--c-text-muted);">Median</span></div>
                    <div><span style="font-size:1.1em;font-weight:600;color:var(--c-text-muted);">${fmtSec(ts.tcd_p25)}</span><br><span style="font-size:.76em;color:var(--c-text-muted);">P25</span></div>
                    <div><span style="font-size:1.1em;font-weight:600;color:var(--c-text-muted);">${fmtSec(ts.tcd_p75)}</span><br><span style="font-size:.76em;color:var(--c-text-muted);">P75</span></div>
                </div>`;
        } else { tcdCard.style.display = 'none'; }
        if (ts.tee_count > 0) {
            teeCard.style.display = 'block';
            document.getElementById('teeStats').innerHTML = `
                <div style="font-size:.78em;color:var(--c-text-muted);margin-bottom:8px;font-style:italic;">AI flag received date − End date, if the CXR was processed</div>
                <div style="font-size:.82em;color:var(--c-text-muted);margin-bottom:12px;">n = ${ts.tee_count}</div>
                <div style="display:flex;gap:20px;align-items:baseline;">
                    <div><span style="font-size:1.4em;font-weight:400;color:var(--c-primary);">${fmtSec(ts.tee_mean)}</span><br><span style="font-size:.76em;color:var(--c-text-muted);">Mean</span></div>
                    <div><span style="font-size:1.4em;font-weight:700;color:var(--c-primary);">${fmtSec(ts.tee_median)}</span><br><span style="font-size:.76em;color:var(--c-text-muted);">Median</span></div>
                    <div><span style="font-size:1.1em;font-weight:600;color:var(--c-text-muted);">${fmtSec(ts.tee_p25)}</span><br><span style="font-size:.76em;color:var(--c-text-muted);">P25</span></div>
                    <div><span style="font-size:1.1em;font-weight:600;color:var(--c-text-muted);">${fmtSec(ts.tee_p75)}</span><br><span style="font-size:.76em;color:var(--c-text-muted);">P75</span></div>
                    <div><span style="font-size:1.1em;font-weight:700;color:var(--c-danger);">${ts.tee_more_than_5mins ?? 0}</span><br><span style="font-size:.76em;color:var(--c-text-muted);">&gt; 5 min</span></div>
                </div>`;
        } else { teeCard.style.display = 'none'; }
        drawBoxPlots(ts);
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
    if (fns.length > 0) dlHtml += `<button class="btn btn-warning" id="downloadFnCsvBtn">📥 Download False Negatives CSV</button>`;
    if (fps.length > 0) dlHtml += `<button class="btn btn-warning" id="downloadFpCsvBtn">📥 Download False Positives CSV</button>`;
    gtDlRow.innerHTML = dlHtml;
    gtDlRow.style.display = dlHtml ? 'flex' : 'none';
    // Attach event listeners to dynamically created buttons
    const fnBtn = document.getElementById('downloadFnCsvBtn');
    if (fnBtn) fnBtn.addEventListener('click', downloadFnCSV);
    const fpBtn = document.getElementById('downloadFpCsvBtn');
    if (fpBtn) fpBtn.addEventListener('click', downloadFpCSV);
}

// ── Download PDF ──

function captureChartImages() {
    const charts = {};
    const ids = ['aucTrendChart', 'sensChart', 'specChart', 'tcdBoxPlot', 'teeBoxPlot'];
    ids.forEach(id => {
        const canvas = document.getElementById(id);
        if (canvas && canvas.width > 0 && canvas.offsetParent !== null) {
            try { charts[id] = canvas.toDataURL('image/png'); } catch(e) { /* skip */ }
        }
    });
    return charts;
}

async function downloadPDF() {
    if (!lastReportData) { alert('Generate a report first.'); return; }
    const btn = document.getElementById('downloadPdfBtn');
    btn.disabled = true;
    btn.textContent = '⏳ Preparing…';
    try {
        const chartImages = captureChartImages();
        const r = await fetch(window.REPORT_CONFIG.downloadPdfUrl, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': window.REPORT_CONFIG.csrfToken,
            },
            body: JSON.stringify({ report_data: lastReportData, chart_images: chartImages }),
        });
        if (!r.ok) throw new Error(`Server error ${r.status}`);
        const blob = await r.blob();
        const url = URL.createObjectURL(blob);
        const w = window.open(url, '_blank');
        if (w) {
            w.addEventListener('afterprint', () => URL.revokeObjectURL(url));
            // Some browsers need a brief delay before print()
            w.addEventListener('load', () => setTimeout(() => w.print(), 400));
        } else {
            // Popup blocked — fall back to direct download link
            const a = document.createElement('a');
            a.href = url; a.target = '_blank'; a.click();
        }
    } catch (e) { alert('PDF error: ' + e.message); }
    finally {
        btn.disabled = false;
        btn.textContent = '📄 Download PDF';
    }
}

// ── Email modal functions ──

const EMAIL_STORAGE_KEY = 'primer_email_recipients';

function openEmailModal() {
    if (!lastReportData) { alert('Generate a report first.'); return; }
    document.getElementById('emailStatus').textContent = '';
    document.getElementById('emailStatus').className = 'email-status';
    document.getElementById('sendEmailBtn').disabled = false;

    // Restore saved recipients
    const saved = localStorage.getItem(EMAIL_STORAGE_KEY);
    if (saved) document.getElementById('emailRecipients').value = saved;

    document.getElementById('emailModal').classList.add('open');
    document.getElementById('emailRecipients').focus();
}

function closeEmailModal() {
    document.getElementById('emailModal').classList.remove('open');
}

async function sendEmailReport() {
    const recipients = document.getElementById('emailRecipients').value.trim();
    if (!recipients) {
        showEmailStatus('Please enter at least one email address.', 'error');
        return;
    }

    // Persist recipients for next time
    localStorage.setItem(EMAIL_STORAGE_KEY, recipients);

    const note = document.getElementById('emailNote').value.trim();

    const btn = document.getElementById('sendEmailBtn');
    btn.disabled = true;
    btn.textContent = 'Sending…';
    showEmailStatus('Sending report…', 'info');

    try {
        const r = await fetch(window.REPORT_CONFIG.emailReportUrl, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': window.REPORT_CONFIG.csrfToken,
            },
            body: JSON.stringify({
                recipients: recipients,
                report_data: lastReportData,
                note: note,
            }),
        });
        const result = await r.json();
        if (result.ok) {
            showEmailStatus(`Report sent to ${result.sent_to.join(', ')}`, 'success');
            setTimeout(closeEmailModal, 2500);
        } else {
            showEmailStatus(result.error || 'Unknown error.', 'error');
        }
    } catch (e) {
        showEmailStatus('Network error: ' + e.message, 'error');
    } finally {
        btn.disabled = false;
        btn.textContent = 'Send';
    }
}

function showEmailStatus(msg, type) {
    const el = document.getElementById('emailStatus');
    el.textContent = msg;
    el.className = 'email-status ' + (type || '');
}

// ── Wire up event listeners (replaces inline onclick) ──
document.getElementById('generateBtn').addEventListener('click', generateReport);
document.getElementById('downloadCsvBtn').addEventListener('click', downloadCSV);
document.getElementById('downloadPdfBtn').addEventListener('click', downloadPDF);
document.getElementById('emailReportBtn').addEventListener('click', openEmailModal);
document.getElementById('closeEmailModalBtn').addEventListener('click', closeEmailModal);
document.getElementById('cancelEmailBtn').addEventListener('click', closeEmailModal);
document.getElementById('sendEmailBtn').addEventListener('click', sendEmailReport);
