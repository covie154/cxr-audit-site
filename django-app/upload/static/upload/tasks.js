const csrfToken = window.PAGE_CONFIG.csrfToken;
const deleteBaseUrl = window.PAGE_CONFIG.deleteBaseUrl;
let pendingDeleteId = null;

function confirmDelete(taskId) {
    pendingDeleteId = taskId;
    document.getElementById('deleteModal').classList.add('show');
}

function closeModal() {
    pendingDeleteId = null;
    document.getElementById('deleteModal').classList.remove('show');
}

async function doDelete() {
    if (!pendingDeleteId) return;
    const taskId = pendingDeleteId;
    const btn = document.getElementById('confirmDeleteBtn');
    btn.disabled = true; btn.textContent = '\u231B Deleting\u2026';

    try {
        const r = await fetch(`${deleteBaseUrl}${taskId}/delete`, {
            method: 'POST',
            headers: { 'X-CSRFToken': csrfToken }
        });
        const d = await r.json();

        if (r.ok) {
            // Remove row with animation
            const row = document.getElementById(`row-${taskId}`);
            if (row) {
                row.style.transition = 'opacity .3s';
                row.style.opacity = '0';
                setTimeout(() => row.remove(), 300);
            }
            showToast('Task deleted successfully', 'success');
            // Update count
            const remaining = document.querySelectorAll('.tasks-table tbody tr').length - 1;
            document.querySelector('.task-count').textContent =
                `${remaining} task${remaining !== 1 ? 's' : ''}`;
            if (remaining === 0) setTimeout(() => location.reload(), 400);
        } else {
            showToast(d.error || 'Delete failed', 'error');
        }
    } catch(e) {
        showToast(`Error: ${e.message}`, 'error');
    }

    closeModal();
    btn.disabled = false; btn.textContent = '\u{1F5D1} Delete';
}

// Close modal on overlay click
document.getElementById('deleteModal').addEventListener('click', function(e) {
    if (e.target === this) closeModal();
});

// Wire up delete buttons via event delegation
document.addEventListener('click', function(e) {
    const deleteBtn = e.target.closest('[data-task-id]');
    if (deleteBtn) confirmDelete(deleteBtn.dataset.taskId);
});

// Wire up modal buttons
document.getElementById('cancelDeleteBtn').addEventListener('click', closeModal);
document.getElementById('confirmDeleteBtn').addEventListener('click', doDelete);

function showToast(msg, type) {
    const t = document.getElementById('toast');
    t.textContent = msg;
    t.className = `toast toast-${type} show`;
    setTimeout(() => t.classList.remove('show'), 3000);
}
