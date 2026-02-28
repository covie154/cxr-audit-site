(function() {
    const startEl   = document.getElementById('startDate');
    const endEl     = document.getElementById('endDate');
    const pctEl     = document.getElementById('pctInput');
    const countEl   = document.getElementById('countInput');
    const infoEl    = document.getElementById('reportInfo');
    const stratEl   = document.getElementById('stratifiedInfo');
    const dlBtn     = document.getElementById('downloadBtn');

    let totalReports = 0;   // total in range
    let eligibleReports = 0; // without GT (the pool we sample from)
    let priorityReports = 0; // priority workplaces (TPY/HOU/KHA/AMK)
    let otherReports = 0;    // all other workplaces
    let recommendedPct = 2;  // server-provided recommended %
    let recommendedCount = 0;
    let fetchTimer   = null;
    let updatingFrom = null;          // guards against recursive updates

    // ── Fetch report count from server ──
    function fetchReportCount() {
        const start = startEl.value;
        const end   = endEl.value;
        if (!start || !end) return;

        infoEl.className = 'report-info loading';
        infoEl.textContent = '\u{1F504} Checking reports in range\u2026';
        dlBtn.disabled = true;

        fetch(`/gt/api/report-count?start=${start}&end=${end}`)
            .then(r => r.json())
            .then(data => {
                if (data.error) {
                    infoEl.className = 'report-info error';
                    infoEl.textContent = '\u26A0\uFE0F ' + data.error;
                    totalReports = 0;
                    eligibleReports = 0;
                    priorityReports = 0;
                    otherReports = 0;
                    stratEl.style.display = 'none';
                } else {
                    totalReports = data.total;
                    eligibleReports = data.without_gt;
                    priorityReports = data.priority_count || 0;
                    otherReports = data.other_count || 0;
                    recommendedPct = data.recommended_pct || 2;
                    recommendedCount = data.recommended_count || Math.ceil(eligibleReports * 2 / 100);
                    infoEl.className = 'report-info';
                    infoEl.textContent = `\u{1F4CB} ${totalReports.toLocaleString()} report${totalReports !== 1 ? 's' : ''} found in range, ${eligibleReports.toLocaleString()} without GT.`;
                    stratEl.style.display = '';
                    stratEl.textContent = `\u{1F3E5} Sampling pool: ${priorityReports.toLocaleString()} priority (TPY/HOU/KHA/AMK) + ${otherReports.toLocaleString()} other \u2014 50/50 stratified sampling applied.`;
                }
                syncFromPct();
                updateDownloadState();
            })
            .catch(() => {
                infoEl.className = 'report-info error';
                infoEl.textContent = '\u26A0\uFE0F Failed to fetch report count.';
                totalReports = 0;
                eligibleReports = 0;
                priorityReports = 0;
                otherReports = 0;
                stratEl.style.display = 'none';
                updateDownloadState();
            });
    }

    // ── Sync helpers (with guard to avoid recursive loop) ──
    function syncFromPct() {
        if (updatingFrom === 'count') return;
        updatingFrom = 'pct';
        let pct = parseFloat(pctEl.value);
        if (isNaN(pct) || pct <= 0 || pct > 100) {
            pct = 100;
            pctEl.value = 100;
        }
        pct = Math.min(100, Math.max(1, pct));
        const count = Math.ceil(eligibleReports * pct / 100);
        countEl.value = count;
        updateDownloadState();
        updatingFrom = null;
    }

    function syncFromCount() {
        if (updatingFrom === 'pct') return;
        updatingFrom = 'count';
        let count = parseInt(countEl.value, 10);
        if (isNaN(count) || count <= 0 || eligibleReports === 0) {
            // reset to 100%
            pctEl.value = 100;
            countEl.value = eligibleReports;
            updatingFrom = null;
            updateDownloadState();
            return;
        }
        count = Math.min(count, eligibleReports);
        countEl.value = count;
        const pct = Math.ceil(count / eligibleReports * 100);
        pctEl.value = pct;
        updateDownloadState();
        updatingFrom = null;
    }

    function updateDownloadState() {
        const count = parseInt(countEl.value, 10);
        dlBtn.disabled = !(eligibleReports > 0 && !isNaN(count) && count > 0);
    }

    // ── Event listeners ──
    startEl.addEventListener('change', debounceFetch);
    endEl.addEventListener('change', debounceFetch);

    pctEl.addEventListener('input', syncFromPct);
    countEl.addEventListener('input', syncFromCount);

    function debounceFetch() {
        clearTimeout(fetchTimer);
        fetchTimer = setTimeout(fetchReportCount, 300);
    }

    dlBtn.addEventListener('click', function() {
        const start = startEl.value;
        const end   = endEl.value;
        const count = parseInt(countEl.value, 10);
        if (!start || !end || isNaN(count) || count < 1) return;
        window.location.href = `/gt/api/download-reports?start=${start}&end=${end}&count=${count}`;
    });

    // ── "Why?" rationale link ──
    const rationaleLink = document.getElementById('rationaleLink');
    if (rationaleLink) {
        rationaleLink.addEventListener('click', function(e) {
            e.preventDefault();
            alert(
                'Sample Size Rationale (Power Analysis)\n\n'
                + 'Based on 3,899 paired LLM vs human observations:\n'
                + '\u2022 Binary agreement: 89.4%  (Cohen\'s \u03BA = 0.791)\n'
                + '\u2022 LLM sensitivity: 98.2%  |  Specificity: 82.6%\n\n'
                + 'A 2% sample (~150 per ~7,000 reports) provides:\n'
                + '\u2022 95% CI for agreement within \u00B15%\n'
                + '\u2022 80% power for McNemar\'s test (detects classification bias)\n'
                + '\u2022 80% power for non-inferiority of sensitivity (\u03B4=5%)\n\n'
                + 'See documentation/sampling_280226.md for full analysis.'
            );
        });
    }

    // ── Init ──
    fetchReportCount();
})();

// ═══════════════════════════════════════════════════════════
//  Box 2: Upload Labelled Reports
// ═══════════════════════════════════════════════════════════
(function() {
    const dropZone    = document.getElementById('gtFileDrop');
    const fileInput   = document.getElementById('gtFileInput');
    const fileSelDiv  = document.getElementById('gtFileSelected');
    const fileNameEl  = document.getElementById('gtFileName');
    const removeBtn   = document.getElementById('gtRemoveFile');
    const validateBtn = document.getElementById('validateBtn');
    const valMsg      = document.getElementById('validationMsg');
    const mapSection  = document.getElementById('mappingSection');
    const accSelect   = document.getElementById('accColSelect');
    const gtSelect    = document.getElementById('gtColSelect');
    const colValMsg   = document.getElementById('colValidationMsg');
    const uploadBtn   = document.getElementById('uploadBtn');
    const resultPanel = document.getElementById('resultPanel');
    const resultTitle = document.getElementById('resultTitle');
    const resultSummary = document.getElementById('resultSummary');
    const resultErrors  = document.getElementById('resultErrors');

    let selectedFile = null;
    let validatedData = null;   // { columns, row_count, suggested_accession, suggested_gt }

    // ── Drag & drop / click ──
    dropZone.addEventListener('click', () => fileInput.click());
    dropZone.addEventListener('dragover', e => { e.preventDefault(); dropZone.classList.add('dragover'); });
    dropZone.addEventListener('dragleave', () => dropZone.classList.remove('dragover'));
    dropZone.addEventListener('drop', e => {
        e.preventDefault();
        dropZone.classList.remove('dragover');
        if (e.dataTransfer.files.length) pickFile(e.dataTransfer.files[0]);
    });
    fileInput.addEventListener('change', () => {
        if (fileInput.files.length) pickFile(fileInput.files[0]);
    });

    function pickFile(file) {
        const ext = file.name.split('.').pop().toLowerCase();
        if (!['csv', 'xls', 'xlsx'].includes(ext)) {
            showValMsg('error', '\u26A0\uFE0F Unsupported file type. Only CSV, XLS and XLSX are accepted.');
            return;
        }
        selectedFile = file;
        fileNameEl.textContent = `\u{1F4C4} ${file.name} (${(file.size / 1024).toFixed(1)} KB)`;
        fileSelDiv.style.display = 'flex';
        dropZone.style.display = 'none';
        validateBtn.disabled = false;
        resetValidation();
    }

    removeBtn.addEventListener('click', () => {
        selectedFile = null;
        fileInput.value = '';
        fileSelDiv.style.display = 'none';
        dropZone.style.display = '';
        validateBtn.disabled = true;
        resetValidation();
    });

    function resetValidation() {
        validatedData = null;
        mapSection.style.display = 'none';
        valMsg.style.display = 'none';
        colValMsg.style.display = 'none';
        resultPanel.style.display = 'none';
    }

    function showValMsg(type, text) {
        valMsg.className = 'validation-msg ' + type;
        valMsg.textContent = text;
        valMsg.style.display = 'block';
    }

    // ── Validate ──
    validateBtn.addEventListener('click', () => {
        if (!selectedFile) return;
        validateBtn.disabled = true;
        showValMsg('info', '\u{1F504} Validating file\u2026');
        mapSection.style.display = 'none';
        resultPanel.style.display = 'none';

        const form = new FormData();
        form.append('file', selectedFile);

        fetch('/gt/api/validate-upload', { method: 'POST', body: form })
            .then(r => r.json().then(d => ({ ok: r.ok, data: d })))
            .then(({ ok, data }) => {
                validateBtn.disabled = false;
                if (!ok) {
                    showValMsg('error', '\u26A0\uFE0F ' + (data.error || 'Validation failed.'));
                    return;
                }
                validatedData = data;
                showValMsg('success', `\u2705 ${data.row_count} row${data.row_count !== 1 ? 's' : ''} found across ${data.columns.length} columns.`);

                // Populate selects
                populateSelect(accSelect, data.columns, data.suggested_accession);
                populateSelect(gtSelect, data.columns, data.suggested_gt);
                mapSection.style.display = 'block';
            })
            .catch(() => {
                validateBtn.disabled = false;
                showValMsg('error', '\u26A0\uFE0F Network error during validation.');
            });
    });

    function populateSelect(sel, columns, suggested) {
        sel.innerHTML = '';
        columns.forEach(col => {
            const opt = document.createElement('option');
            opt.value = col;
            opt.textContent = col;
            if (col === suggested) opt.selected = true;
            sel.appendChild(opt);
        });
    }

    // ── Upload ──
    uploadBtn.addEventListener('click', () => {
        if (!validatedData) return;
        uploadBtn.disabled = true;
        uploadBtn.textContent = '\u231B Uploading\u2026';
        resultPanel.style.display = 'none';

        fetch('/gt/api/apply-gt', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                accession_col: accSelect.value,
                gt_col: gtSelect.value,
            }),
        })
            .then(r => r.json().then(d => ({ ok: r.ok, data: d })))
            .then(({ ok, data }) => {
                uploadBtn.disabled = false;
                uploadBtn.textContent = '\u{1F4E4} Upload to Database';

                if (!ok) {
                    resultPanel.className = 'result-panel error';
                    resultTitle.textContent = '\u274C Upload Failed';
                    resultSummary.textContent = data.error || 'Unknown error.';
                    resultErrors.innerHTML = '';
                    resultPanel.style.display = 'block';
                    return;
                }

                const allGood = data.skipped === 0;
                resultPanel.className = 'result-panel ' + (allGood ? 'success' : 'error');
                resultTitle.textContent = allGood ? '\u2705 Upload Complete' : '\u26A0\uFE0F Upload Complete with Issues';
                resultSummary.textContent = `${data.updated} of ${data.total} rows updated successfully. ${data.skipped} row${data.skipped !== 1 ? 's' : ''} skipped.`;

                resultErrors.innerHTML = '';
                if (data.errors && data.errors.length) {
                    data.errors.forEach(err => {
                        const li = document.createElement('li');
                        li.textContent = err;
                        resultErrors.appendChild(li);
                    });
                }
                resultPanel.style.display = 'block';

                // Reset form for another upload
                validatedData = null;
                mapSection.style.display = 'none';
            })
            .catch(() => {
                uploadBtn.disabled = false;
                uploadBtn.textContent = '\u{1F4E4} Upload to Database';
                resultPanel.className = 'result-panel error';
                resultTitle.textContent = '\u274C Network Error';
                resultSummary.textContent = 'Failed to reach the server.';
                resultErrors.innerHTML = '';
                resultPanel.style.display = 'block';
            });
    });
})();
