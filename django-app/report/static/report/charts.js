/**
 * Report page – chart drawing functions (Canvas 2D).
 *
 * Exports (global):
 *   drawBoxPlot(ts)              – horizontal box-and-whisker
 *   drawSiteTrendCharts(wm)      – weekly sensitivity/specificity line charts
 */

// ── Colour palette for site lines ──
const SITE_COLORS = [
    '#3b82f6', '#8b5cf6', '#f59e0b', '#10b981', '#ef4444',
    '#ec4899', '#06b6d4', '#84cc16', '#f97316', '#6366f1',
];

// ────────────────────────────────────
// Box plot (time analysis)
// ────────────────────────────────────
/**
 * Draw a single horizontal box-and-whisker plot on the given canvas.
 * @param {string} canvasId   – id of the <canvas> element
 * @param {number[]} vals     – raw values in seconds
 * @param {string} color      – CSS colour for the box
 * @param {number} scaleMaxMins – x-axis maximum in minutes
 * @param {number|null} refLineMins – optional reference line in minutes (dashed red)
 */
function drawSingleBoxPlot(canvasId, vals, color, scaleMaxMins, refLineMins) {
    const canvas = document.getElementById(canvasId);
    if (!canvas || !vals || vals.length === 0) return;
    const ctx = canvas.getContext('2d');
    const dpr = window.devicePixelRatio || 1;
    const rect = canvas.getBoundingClientRect();
    canvas.width = rect.width * dpr;
    canvas.height = rect.height * dpr;
    ctx.scale(dpr, dpr);
    const W = rect.width, H = rect.height;
    ctx.clearRect(0, 0, W, H);

    const mins = vals.map(v => v / 60);
    const scaleMax = scaleMaxMins;

    const leftPad = 30, rightPad = 30, topPad = 16, botPad = 28;
    const plotW = W - leftPad - rightPad;
    const plotH = H - topPad - botPad;
    const toX = (m) => leftPad + (m / scaleMax) * plotW;

    // Axis
    ctx.strokeStyle = '#e2e8f0'; ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(leftPad, topPad); ctx.lineTo(leftPad, H - botPad); ctx.lineTo(W - rightPad, H - botPad); ctx.stroke();

    // Tick marks
    ctx.fillStyle = '#94a3b8'; ctx.font = '11px system-ui'; ctx.textAlign = 'center';
    const tickStep = scaleMax <= 5 ? 1 : scaleMax <= 15 ? 2 : scaleMax <= 30 ? 5 : 10;
    for (let m = 0; m <= scaleMax; m += tickStep) {
        const x = toX(m);
        ctx.strokeStyle = '#f1f5f9'; ctx.beginPath(); ctx.moveTo(x, topPad); ctx.lineTo(x, H - botPad); ctx.stroke();
        ctx.fillText(m + ' min', x, H - botPad + 16);
    }

    // Reference line
    if (refLineMins != null && refLineMins <= scaleMax) {
        const xRef = toX(refLineMins);
        ctx.save();
        ctx.strokeStyle = '#dc2626'; ctx.lineWidth = 1.5; ctx.setLineDash([6, 4]);
        ctx.beginPath(); ctx.moveTo(xRef, topPad); ctx.lineTo(xRef, H - botPad); ctx.stroke();
        ctx.setLineDash([]);
        ctx.fillStyle = '#dc2626'; ctx.font = 'bold 11px system-ui'; ctx.textAlign = 'left';
        ctx.fillText(refLineMins + ' min', xRef + 4, topPad + 12);
        ctx.restore();
    }

    // Statistics
    const sorted = mins.slice().sort((a, b) => a - b);
    const n = sorted.length;
    const q1 = sorted[Math.floor(n * 0.25)];
    const med = sorted[Math.floor(n * 0.5)];
    const q3 = sorted[Math.floor(n * 0.75)];
    const iqr = q3 - q1;
    const wLo = Math.max(sorted[0], q1 - 1.5 * iqr);
    const wHi = Math.min(sorted[n - 1], q3 + 1.5 * iqr);

    const yCenter = topPad + plotH / 2;
    const boxH = Math.min(40, plotH * 0.6);

    // Whiskers
    ctx.strokeStyle = color; ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.moveTo(toX(wLo), yCenter); ctx.lineTo(toX(q1), yCenter);
    ctx.moveTo(toX(q3), yCenter); ctx.lineTo(toX(wHi), yCenter);
    ctx.moveTo(toX(wLo), yCenter - boxH / 4); ctx.lineTo(toX(wLo), yCenter + boxH / 4);
    ctx.moveTo(toX(wHi), yCenter - boxH / 4); ctx.lineTo(toX(wHi), yCenter + boxH / 4);
    ctx.stroke();

    // Box
    ctx.fillStyle = color + '22';
    ctx.fillRect(toX(q1), yCenter - boxH / 2, toX(q3) - toX(q1), boxH);
    ctx.strokeStyle = color; ctx.lineWidth = 1.5;
    ctx.strokeRect(toX(q1), yCenter - boxH / 2, toX(q3) - toX(q1), boxH);

    // Median
    ctx.strokeStyle = color; ctx.lineWidth = 2.5;
    ctx.beginPath(); ctx.moveTo(toX(med), yCenter - boxH / 2); ctx.lineTo(toX(med), yCenter + boxH / 2); ctx.stroke();

    // Outliers
    ctx.fillStyle = color;
    sorted.forEach(v => {
        if (v < wLo || v > wHi) {
            ctx.beginPath(); ctx.arc(toX(Math.min(v, scaleMax)), yCenter, 2.5, 0, Math.PI * 2); ctx.fill();
        }
    });
}

/** Draws both box plots on separate canvases. TCD auto-scales from P95. */
function drawBoxPlots(ts) {
    if (ts.tcd_vals && ts.tcd_vals.length > 0) {
        // Auto-scale TCD: P95 in minutes × 1.3, rounded to nice tick value
        let tcdMax = 60;
        if (ts.tcd_p95 != null) {
            const p95m = ts.tcd_p95 / 60;
            const raw = p95m * 1.3;
            if (raw <= 5) tcdMax = 5;
            else if (raw <= 10) tcdMax = 10;
            else if (raw <= 15) tcdMax = 15;
            else if (raw <= 30) tcdMax = 30;
            else if (raw <= 60) tcdMax = 60;
            else if (raw <= 120) tcdMax = 120;
            else tcdMax = Math.ceil(raw / 60) * 60;
        }
        drawSingleBoxPlot('tcdBoxPlot', ts.tcd_vals, '#3b82f6', tcdMax, null);
    }
    if (ts.tee_vals && ts.tee_vals.length > 0)
        drawSingleBoxPlot('teeBoxPlot', ts.tee_vals, '#8b5cf6', 10, 5);
}

// ────────────────────────────────────
// Site trend line charts (weekly)
// ────────────────────────────────────
function drawSiteTrendCharts(wm) {
    const el = document.getElementById('siteCharts');
    if (!wm || !wm.weeks || wm.weeks.length === 0) { el.style.display = 'none'; return; }
    el.style.display = 'block';
    drawLineChart('sensChart', wm.weeks, wm.sites, wm.sensitivity);
    drawLineChart('specChart', wm.weeks, wm.sites, wm.specificity);
}

function drawAucTrendChart(wa) {
    const wrap = document.getElementById('aucTrendWrap');
    if (!wa || !wa.weeks || wa.weeks.length === 0) { wrap.style.display = 'none'; return; }
    wrap.style.display = 'block';

    const canvas = document.getElementById('aucTrendChart');
    const ctx = canvas.getContext('2d');
    const dpr = window.devicePixelRatio || 1;
    const rect = canvas.getBoundingClientRect();
    canvas.width = rect.width * dpr;
    canvas.height = rect.height * dpr;
    ctx.scale(dpr, dpr);
    const W = rect.width, H = rect.height;
    ctx.clearRect(0, 0, W, H);

    const weeks = wa.weeks;
    const auc = wa.auc;
    const n = weeks.length;
    const leftPad = 50, rightPad = 30, topPad = 16, botPad = 40;
    const plotW = W - leftPad - rightPad;
    const plotH = H - topPad - botPad;

    // Y-axis range: 0–100 %
    const toX = (i) => leftPad + (n === 1 ? plotW / 2 : (i / (n - 1)) * plotW);
    const toY = (v) => topPad + plotH - (v / 100) * plotH;

    // Grid lines
    ctx.strokeStyle = '#f1f5f9'; ctx.lineWidth = 1;
    ctx.fillStyle = '#94a3b8'; ctx.font = '10px system-ui'; ctx.textAlign = 'right';
    for (let pct = 0; pct <= 100; pct += 20) {
        const y = toY(pct);
        ctx.beginPath(); ctx.moveTo(leftPad, y); ctx.lineTo(leftPad + plotW, y); ctx.stroke();
        ctx.fillText(pct + '%', leftPad - 6, y + 3);
    }

    // Axes
    ctx.strokeStyle = '#e2e8f0'; ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(leftPad, topPad); ctx.lineTo(leftPad, H - botPad); ctx.lineTo(leftPad + plotW, H - botPad); ctx.stroke();

    // X-axis week labels
    ctx.fillStyle = '#94a3b8'; ctx.font = '10px system-ui'; ctx.textAlign = 'center';
    weeks.forEach((label, i) => {
        const x = toX(i);
        ctx.strokeStyle = '#e2e8f0'; ctx.beginPath(); ctx.moveTo(x, H - botPad); ctx.lineTo(x, H - botPad + 5); ctx.stroke();
        ctx.fillText(label, x, H - botPad + 18);
    });

    // 95% CI bands (dotted lines across full width)
    if (wa.ci_lower != null && wa.ci_upper != null) {
        ctx.save();
        ctx.setLineDash([6, 4]);
        ctx.strokeStyle = '#f59e0b'; ctx.lineWidth = 1.5;
        const yLo = toY(wa.ci_lower);
        const yHi = toY(wa.ci_upper);
        ctx.beginPath(); ctx.moveTo(leftPad, yHi); ctx.lineTo(leftPad + plotW, yHi); ctx.stroke();
        ctx.beginPath(); ctx.moveTo(leftPad, yLo); ctx.lineTo(leftPad + plotW, yLo); ctx.stroke();
        // Shaded band
        ctx.fillStyle = 'rgba(245, 158, 11, 0.07)';
        ctx.fillRect(leftPad, yHi, plotW, yLo - yHi);
        // Labels
        ctx.setLineDash([]);
        ctx.fillStyle = '#f59e0b'; ctx.font = '10px system-ui'; ctx.textAlign = 'left';
        ctx.fillText('95% CI ' + wa.ci_upper.toFixed(1) + '%', leftPad + plotW + 4, yHi + 3);
        ctx.fillText('95% CI ' + wa.ci_lower.toFixed(1) + '%', leftPad + plotW + 4, yLo + 3);
        ctx.restore();
    }

    // Data line
    const color = '#3b82f6';
    const points = [];
    auc.forEach((v, i) => { if (v != null) points.push({ x: toX(i), y: toY(v), v: v }); });
    if (points.length > 0) {
        ctx.strokeStyle = color; ctx.lineWidth = 2.5;
        ctx.beginPath();
        points.forEach((p, i) => { i === 0 ? ctx.moveTo(p.x, p.y) : ctx.lineTo(p.x, p.y); });
        ctx.stroke();

        // Dots with value labels
        ctx.fillStyle = color;
        points.forEach(p => {
            ctx.beginPath(); ctx.arc(p.x, p.y, 4, 0, Math.PI * 2); ctx.fill();
            // Value label above dot
            ctx.fillStyle = '#1e3a5f'; ctx.font = 'bold 10px system-ui'; ctx.textAlign = 'center';
            ctx.fillText(p.v.toFixed(1) + '%', p.x, p.y - 10);
            ctx.fillStyle = color;
        });
    }
}

function drawLineChart(canvasId, weeks, sites, dataMap) {
    const canvas = document.getElementById(canvasId);
    const ctx = canvas.getContext('2d');
    const dpr = window.devicePixelRatio || 1;
    const rect = canvas.getBoundingClientRect();
    canvas.width = rect.width * dpr;
    canvas.height = rect.height * dpr;
    ctx.scale(dpr, dpr);
    const W = rect.width, H = rect.height;
    ctx.clearRect(0, 0, W, H);

    const n = weeks.length;
    const leftPad = 44, rightPad = 120, topPad = 16, botPad = 40;
    const plotW = W - leftPad - rightPad;
    const plotH = H - topPad - botPad;

    const toX = (i) => leftPad + (n === 1 ? plotW / 2 : (i / (n - 1)) * plotW);
    const toY = (v) => topPad + plotH - (v / 100) * plotH;

    // Grid lines
    ctx.strokeStyle = '#f1f5f9'; ctx.lineWidth = 1;
    ctx.fillStyle = '#94a3b8'; ctx.font = '10px system-ui'; ctx.textAlign = 'right';
    for (let pct = 0; pct <= 100; pct += 20) {
        const y = toY(pct);
        ctx.beginPath(); ctx.moveTo(leftPad, y); ctx.lineTo(leftPad + plotW, y); ctx.stroke();
        ctx.fillText(pct + '%', leftPad - 6, y + 3);
    }

    // Axes
    ctx.strokeStyle = '#e2e8f0'; ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(leftPad, topPad); ctx.lineTo(leftPad, H - botPad); ctx.lineTo(leftPad + plotW, H - botPad); ctx.stroke();

    // X-axis week labels
    ctx.fillStyle = '#94a3b8'; ctx.font = '10px system-ui'; ctx.textAlign = 'center';
    weeks.forEach((label, i) => {
        const x = toX(i);
        // Tick mark
        ctx.strokeStyle = '#e2e8f0'; ctx.beginPath(); ctx.moveTo(x, H - botPad); ctx.lineTo(x, H - botPad + 5); ctx.stroke();
        ctx.fillText(label, x, H - botPad + 18);
    });

    // Draw each site line
    sites.forEach((site, si) => {
        const color = SITE_COLORS[si % SITE_COLORS.length];
        const vals = dataMap[site];
        // Gather non-null points
        const points = [];
        vals.forEach((v, i) => { if (v != null) points.push({ x: toX(i), y: toY(v), v: v }); });
        if (points.length === 0) return;

        // Line
        ctx.strokeStyle = color; ctx.lineWidth = 2;
        ctx.beginPath();
        points.forEach((p, i) => { i === 0 ? ctx.moveTo(p.x, p.y) : ctx.lineTo(p.x, p.y); });
        ctx.stroke();

        // Dots
        ctx.fillStyle = color;
        points.forEach(p => {
            ctx.beginPath(); ctx.arc(p.x, p.y, 3.5, 0, Math.PI * 2); ctx.fill();
        });

        // Legend entry (right side)
        const legendY = topPad + 14 + si * 18;
        const legendX = leftPad + plotW + 14;
        ctx.fillStyle = color;
        ctx.beginPath(); ctx.arc(legendX, legendY, 4, 0, Math.PI * 2); ctx.fill();
        // Line sample
        ctx.strokeStyle = color; ctx.lineWidth = 2;
        ctx.beginPath(); ctx.moveTo(legendX + 8, legendY); ctx.lineTo(legendX + 24, legendY); ctx.stroke();
        ctx.fillStyle = color; ctx.font = '11px system-ui'; ctx.textAlign = 'left';
        ctx.fillText(site, legendX + 28, legendY + 4);
    });
}
