const csrfToken = window.PAGE_CONFIG.csrfToken;
const previewUrl = window.PAGE_CONFIG.previewUrl;
const importUrl = window.PAGE_CONFIG.importUrl;

const zone = document.getElementById('uploadZone');
const fileInput = document.getElementById('fileInput');
const previewCard = document.getElementById('previewCard');
const resultCard = document.getElementById('resultCard');
let currentPreview = null;  // stores the preview response

// ── Drag & drop ──
zone.addEventListener('click', () => fileInput.click());
zone.addEventListener('dragover', e => { e.preventDefault(); zone.classList.add('dragover'); });
zone.addEventListener('dragleave', () => zone.classList.remove('dragover'));
zone.addEventListener('drop', e => {
    e.preventDefault();
    zone.classList.remove('dragover');
    if (e.dataTransfer.files.length) {
        fileInput.files = e.dataTransfer.files;
        handleFile(e.dataTransfer.files[0]);
    }
});
fileInput.addEventListener('change', () => {
    if (fileInput.files.length) handleFile(fileInput.files[0]);
});

function handleFile(file) {
    if (!file.name.toLowerCase().endsWith('.csv')) {
        showToast('Please select a CSV file', 'error');
        return;
    }
    zone.classList.add('has-file');
    document.getElementById('zoneText').textContent = `\u{1F4C4} ${file.name} (${formatSize(file.size)})`;
    previewFile(file);
}

function clearFile() {
    fileInput.value = '';
    zone.classList.remove('has-file');
    document.getElementById('zoneText').textContent = 'Drop a CSV file here or click to browse';
    previewCard.classList.remove('visible');
    resultCard.classList.remove('visible');
    currentPreview = null;
}

// Wire up clear and import buttons
document.getElementById('clearFileBtn').addEventListener('click', clearFile);
document.getElementById('btnImport').addEventListener('click', doImport);

async function previewFile(file) {
    previewCard.classList.add('visible');
    resultCard.classList.remove('visible');
    document.getElementById('importLoading').classList.add('visible');
    document.querySelector('.preview-body').style.display = 'none';

    const form = new FormData();
    form.append('file', file);
    form.append('mode', document.getElementById('importMode').value);

    try {
        const res = await fetch(previewUrl, {
            method: 'POST',
            headers: { 'X-CSRFToken': csrfToken },
            body: form
        });
        const data = await res.json();
        if (!res.ok) {
            showToast(data.error || 'Preview failed', 'error');
            previewCard.classList.remove('visible');
            return;
        }
        currentPreview = data;
        renderPreview(data);
    } catch (err) {
        showToast('Network error: ' + err.message, 'error');
        previewCard.classList.remove('visible');
    }
}

function renderPreview(data) {
    document.getElementById('importLoading').classList.remove('visible');
    document.querySelector('.preview-body').style.display = '';

    document.getElementById('statTotal').textContent = data.total_rows.toLocaleString();
    document.getElementById('statNew').textContent = data.new_count.toLocaleString();
    document.getElementById('statSkip').textContent = data.duplicate_count.toLocaleString();
    document.getElementById('statInvalid').textContent = data.invalid_count.toLocaleString();

    // Warnings
    const warnList = document.getElementById('warnList');
    warnList.innerHTML = '';
    if (data.warnings && data.warnings.length) {
        data.warnings.forEach(w => {
            const li = document.createElement('li');
            li.textContent = w;
            warnList.appendChild(li);
        });
        warnList.style.display = '';
    } else {
        warnList.style.display = 'none';
    }

    // Column mapping
    const tbody = document.getElementById('colMapBody');
    tbody.innerHTML = '';
    let mapped = 0;
    data.column_mapping.forEach(([csvCol, dbField]) => {
        const tr = document.createElement('tr');
        if (dbField) {
            mapped++;
            tr.innerHTML = `<td>${csvCol}</td><td class="map-arrow">\u2192</td><td class="map-yes">${dbField}</td>`;
        } else {
            tr.innerHTML = `<td>${csvCol}</td><td class="map-arrow">\u2192</td><td class="map-no">ignored</td>`;
        }
        tbody.appendChild(tr);
    });
    document.getElementById('mappedCount').textContent = mapped;
    document.getElementById('totalCols').textContent = data.column_mapping.length;

    // Import button
    const newCount = data.new_count + (document.getElementById('importMode').value === 'update' ? data.duplicate_count : 0);
    const actionCount = document.getElementById('importMode').value === 'update'
        ? data.new_count + data.duplicate_count
        : data.new_count;
    document.getElementById('btnImportCount').textContent = `(${actionCount.toLocaleString()})`;
    document.getElementById('btnImport').disabled = actionCount === 0;
    document.getElementById('importHint').textContent = actionCount === 0
        ? 'Nothing to import \u2014 all rows are duplicates or invalid.'
        : '';
}

async function doImport() {
    if (!fileInput.files.length) {
        showToast('No file selected', 'error');
        return;
    }
    const btn = document.getElementById('btnImport');
    btn.disabled = true;
    btn.textContent = '\u231B Importing\u2026';

    const form = new FormData();
    form.append('file', fileInput.files[0]);
    form.append('mode', document.getElementById('importMode').value);

    try {
        const res = await fetch(importUrl, {
            method: 'POST',
            headers: { 'X-CSRFToken': csrfToken },
            body: form
        });
        const data = await res.json();
        if (!res.ok) {
            showToast(data.error || 'Import failed', 'error');
            btn.disabled = false;
            btn.innerHTML = '\u{1F4E5} Import';
            return;
        }
        showResult(data);
    } catch (err) {
        showToast('Network error: ' + err.message, 'error');
        btn.disabled = false;
        btn.innerHTML = '\u{1F4E5} Import';
    }
}

function showResult(data) {
    const body = document.getElementById('resultBody');
    const ok = !data.error;
    body.innerHTML = `
        <div class="result-icon">${ok ? '\u2705' : '\u274C'}</div>
        <p><strong>${ok ? 'Import complete!' : 'Import failed'}</strong></p>
        ${ok ? `
            <p>\u2705 <strong>${data.new_count.toLocaleString()}</strong> new records added</p>
            ${data.updated_count ? `<p>\u{1F504} <strong>${data.updated_count.toLocaleString()}</strong> existing records updated</p>` : ''}
            <p>\u23ED\uFE0F <strong>${data.skipped_count.toLocaleString()}</strong> duplicates skipped</p>
            <p>\u26A0\uFE0F <strong>${data.invalid_count.toLocaleString()}</strong> invalid rows skipped</p>
        ` : `<p>${data.error}</p>`}
    `;
    resultCard.classList.add('visible');
    previewCard.classList.remove('visible');
    if (ok) showToast(`Imported ${data.new_count} records successfully`, 'success');
}

// Re-preview when mode changes
document.getElementById('importMode').addEventListener('change', () => {
    if (fileInput.files.length) previewFile(fileInput.files[0]);
});

// ── Helpers ──
function formatSize(bytes) {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / 1048576).toFixed(1) + ' MB';
}

function showToast(msg, type) {
    const t = document.getElementById('toast');
    t.textContent = msg;
    t.className = 'toast toast-' + type + ' show';
    setTimeout(() => t.classList.remove('show'), 3500);
}
