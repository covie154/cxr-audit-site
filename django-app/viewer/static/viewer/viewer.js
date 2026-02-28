const csrfToken = window.PAGE_CONFIG.csrfToken;
const ALL_FILTERED_IDS = window.PAGE_CONFIG.allFilteredIds;
let currentAccession = null;

// ──── Sorting ────
function setSort(field) {
    const form = document.getElementById('filterForm');
    const si = form.querySelector('input[name="sort"]');
    si.value = (si.value === field) ? '-' + field : field;
    form.submit();
}

// ──── Selection ────
let allFilteredSelected = false;

function toggleSelectAll(master) {
    document.querySelectorAll('.row-cb').forEach(cb => cb.checked = master.checked);
    allFilteredSelected = false;
    updateSelection();
}

function selectAllFiltered() {
    document.querySelectorAll('.row-cb').forEach(cb => cb.checked = true);
    document.getElementById('selectAll').checked = true;
    allFilteredSelected = true;
    updateSelection();
}

function updateSelection() {
    const checked = document.querySelectorAll('.row-cb:checked');
    const btn = document.getElementById('bulkDeleteBtn');
    const cnt = document.getElementById('selCount');
    const n = allFilteredSelected ? ALL_FILTERED_IDS.length : checked.length;
    cnt.textContent = n;
    btn.style.display = n > 0 ? 'inline-flex' : 'none';

    document.querySelectorAll('tbody tr').forEach(tr => {
        const cb = tr.querySelector('.row-cb');
        if (cb) tr.classList.toggle('selected', cb.checked);
    });

    if (allFilteredSelected && checked.length < document.querySelectorAll('.row-cb').length) {
        allFilteredSelected = false;
        cnt.textContent = checked.length;
        if (!checked.length) btn.style.display = 'none';
    }
}

// ──── Detail modal ────
async function openDetail(accNo) {
    currentAccession = accNo;
    document.getElementById('modalTitle').textContent = 'Study ' + accNo;
    document.getElementById('modalBody').innerHTML = '<p style="text-align:center;padding:30px;color:#94a3b8;">Loading\u2026</p>';
    document.getElementById('detailModal').classList.add('open');

    try {
        const r = await fetch(`/view/study/${accNo}/`);
        if (!r.ok) throw new Error('Not found');
        renderDetail(await r.json());
    } catch(e) {
        document.getElementById('modalBody').innerHTML = `<p style="color:var(--c-danger);">Error: ${e.message}</p>`;
    }
}

function renderDetail(data) {
    let html = '';
    for (const [group, fields] of Object.entries(data.groups)) {
        html += `<div class="field-group"><h3>${group}</h3><div class="field-grid">`;
        for (const f of fields) {
            const ro = f.readonly ? 'readonly' : '';
            const val = f.value != null ? f.value : '';
            const isLong = f.type === 'TextField' || f.name.includes('report');
            const cls = isLong ? ' full-width' : '';
            html += `<div class="field-item${cls}"><label>${f.label}</label>`;
            html += isLong
                ? `<textarea data-field="${f.name}" ${ro}>${val}</textarea>`
                : `<input data-field="${f.name}" value="${String(val).replace(/"/g,'&quot;')}" ${ro}>`;
            html += '</div>';
        }
        html += '</div></div>';
    }
    document.getElementById('modalBody').innerHTML = html;
}

function closeModal() { document.getElementById('detailModal').classList.remove('open'); currentAccession = null; }
document.getElementById('detailModal').addEventListener('click', function(e) { if (e.target === this) closeModal(); });
document.addEventListener('keydown', e => { if (e.key === 'Escape') closeModal(); });

// ──── Save ────
async function saveDetail() {
    if (!currentAccession) return;
    const payload = {};
    document.querySelectorAll('#modalBody [data-field]').forEach(el => {
        if (el.readOnly) return;
        payload[el.dataset.field] = el.tagName === 'TEXTAREA' ? el.value : el.value;
    });

    try {
        const r = await fetch(`/view/study/${currentAccession}/update/`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
            body: JSON.stringify(payload),
        });
        const res = await r.json();
        if (res.success) { showToast(`Updated ${res.updated_fields.length} field(s)`, 'success'); closeModal(); setTimeout(() => location.reload(), 600); }
        else showToast(res.error || 'Update failed', 'error');
    } catch(e) { showToast('Network error: ' + e.message, 'error'); }
}

// ──── Delete ────
async function deleteStudy(accNo) {
    if (!confirm(`Delete study ${accNo}?`)) return;
    try {
        const r = await fetch(`/view/study/${accNo}/delete/`, { method: 'POST', headers: { 'X-CSRFToken': csrfToken } });
        const res = await r.json();
        if (res.success) { showToast('Deleted', 'success'); document.querySelector(`tr[data-id="${accNo}"]`)?.remove(); }
        else showToast(res.error || 'Failed', 'error');
    } catch(e) { showToast('Network error: ' + e.message, 'error'); }
}

async function bulkDelete() {
    const ids = allFilteredSelected
        ? ALL_FILTERED_IDS
        : Array.from(document.querySelectorAll('.row-cb:checked')).map(cb => Number(cb.value));
    if (!ids.length) return;
    if (!confirm(`Delete ${ids.length} record(s)?`)) return;

    try {
        const r = await fetch('/view/bulk-delete/', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
            body: JSON.stringify({ accession_nos: ids }),
        });
        const res = await r.json();
        if (res.success) { showToast(`Deleted ${res.deleted}`, 'success'); setTimeout(() => location.reload(), 600); }
        else showToast(res.error || 'Failed', 'error');
    } catch(e) { showToast('Network error: ' + e.message, 'error'); }
}

// ──── Event delegation for table actions ────
document.querySelector('.table-wrap').addEventListener('click', function(e) {
    const editBtn = e.target.closest('[data-action="edit"]');
    if (editBtn) { openDetail(Number(editBtn.dataset.accession)); return; }

    const delBtn = e.target.closest('[data-action="delete"]');
    if (delBtn) { deleteStudy(Number(delBtn.dataset.accession)); return; }

    const rowCb = e.target.closest('.row-cb');
    if (rowCb) { updateSelection(); return; }
});

// ──── Sortable headers via event delegation ────
document.querySelector('thead').addEventListener('click', function(e) {
    const th = e.target.closest('[data-sort]');
    if (th) setSort(th.dataset.sort);
});

// ──── Filter selects auto-submit ────
document.querySelectorAll('#filterForm select[name^="f_"], #filterForm select[name="per_page"]').forEach(sel => {
    sel.addEventListener('change', () => document.getElementById('filterForm').submit());
});

// ──── Select all checkbox ────
document.getElementById('selectAll').addEventListener('click', function() { toggleSelectAll(this); });

// ──── Toolbar buttons ────
document.getElementById('selectAllFilteredBtn').addEventListener('click', selectAllFiltered);
document.getElementById('bulkDeleteBtn').addEventListener('click', bulkDelete);

// ──── Modal buttons ────
document.querySelectorAll('[data-action="close-modal"]').forEach(btn => {
    btn.addEventListener('click', closeModal);
});
document.getElementById('saveDetailBtn').addEventListener('click', saveDetail);

// ──── Toast ────
function showToast(msg, type) {
    const t = document.getElementById('toast');
    t.textContent = msg;
    t.className = 'toast toast-' + type + ' show';
    setTimeout(() => t.classList.remove('show'), 3000);
}
