// ─── Interested Leads Feedback Manager ───

let _fbCurrentPage = 1;
let _fbSortBy = 'created_at';
let _fbSortDir = 'DESC';
let _fbSearchTimer = null;

const _fbStatusColors = {
    'Interested': 'background:rgba(52,199,89,.12);color:#34C759;',
    'Not Interested': 'background:rgba(255,59,48,.10);color:#FF3B30;',
    'Callback': 'background:rgba(255,149,0,.12);color:#CC7700;',
    'No Answer': 'background:rgba(142,142,147,.12);color:#8E8E93;',
    'Others': 'background:rgba(142,142,147,.12);color:#8E8E93;',
};

function _fbApi(path) {
    return apiUrl('/api/leads-feedback' + path);
}

function toggleCustomStatus() {
    var sel = document.getElementById('fb-status');
    var grp = document.getElementById('fb-custom-status-group');
    if (sel && grp) {
        grp.style.display = sel.value === 'Others' ? '' : 'none';
    }
}

function debounceFeedbackSearch() {
    clearTimeout(_fbSearchTimer);
    _fbSearchTimer = setTimeout(function () { loadFeedbackData(); }, 350);
}

function sortFeedback(col) {
    if (_fbSortBy === col) {
        _fbSortDir = _fbSortDir === 'ASC' ? 'DESC' : 'ASC';
    } else {
        _fbSortBy = col;
        _fbSortDir = 'ASC';
    }
    _fbCurrentPage = 1;
    loadFeedbackData();
}

async function loadFeedbackData() {
    var search = (document.getElementById('fb-search') || {}).value || '';
    var status = (document.getElementById('fb-filter-status') || {}).value || '';
    var params = new URLSearchParams({
        search: search,
        status: status,
        sort_by: _fbSortBy,
        sort_dir: _fbSortDir,
        page: _fbCurrentPage,
        page_size: 25,
    });
    try {
        var res = await fetch(_fbApi('?' + params.toString()), {
            headers: authHeaders(),
            credentials: 'same-origin',
        });
        if (!res.ok) throw new Error('HTTP ' + res.status);
        var data = await res.json();
        _renderFeedbackTable(data);
        _renderFeedbackStats(data);
    } catch (e) {
        console.error('loadFeedbackData error:', e);
        showToast('Failed to load feedback data', 'error');
    }
}

function _renderFeedbackStats(data) {
    var total = data.total || 0;
    document.getElementById('fb-total').textContent = total.toLocaleString();
    var items = data.items || [];
    var interested = 0, notInterested = 0, callbacks = 0, noAnswer = 0;
    for (var i = 0; i < items.length; i++) {
        var s = items[i].lead_status || '';
        if (s === 'Interested') interested++;
        if (s === 'Not Interested') notInterested++;
        if (s === 'Callback') callbacks++;
        if (s === 'No Answer') noAnswer++;
    }
    document.getElementById('fb-interested').textContent = interested.toLocaleString();
    document.getElementById('fb-not-interested').textContent = notInterested.toLocaleString();
    document.getElementById('fb-callback').textContent = callbacks.toLocaleString();
    document.getElementById('fb-no-answer').textContent = noAnswer.toLocaleString();
}

function _renderFeedbackTable(data) {
    var tbody = document.getElementById('feedback-table-body');
    if (!tbody) return;
    var items = data.items || [];
    if (!items.length) {
        tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;padding:40px 12px;color:var(--text-secondary);">No feedback records found. Add your first entry above.</td></tr>';
        _renderPagination(data);
        return;
    }
    var html = '';
    for (var i = 0; i < items.length; i++) {
        var r = items[i];
        var statusStyle = _fbStatusColors[r.lead_status] || '';
        var displayStatus = escapeHtml(r.lead_status || '');
        if (r.lead_status === 'Others' && r.custom_status) {
            displayStatus += ' (' + escapeHtml(r.custom_status) + ')';
        }
        var notes = escapeHtml(r.feedback_notes || '');
        var notesShort = notes.length > 80 ? notes.substring(0, 80) + '...' : notes;
        var created = r.created_at ? _fbFormatDate(r.created_at) : '—';
        html += '<tr style="border-bottom:1px solid var(--border);transition:background .15s;" onmouseover="this.style.background=\'var(--bg-secondary)\'" onmouseout="this.style.background=\'\'">';
        html += '<td style="padding:10px 12px;font-weight:600;">' + escapeHtml(r.name || '') + '</td>';
        html += '<td style="padding:10px 12px;font-family:var(--font-mono);font-size:12px;">' + escapeHtml(r.contact_number || '') + '</td>';
        html += '<td style="padding:10px 12px;"><span style="display:inline-block;padding:4px 10px;border-radius:6px;font-size:11px;font-weight:700;white-space:nowrap;' + statusStyle + '">' + displayStatus + '</span></td>';
        html += '<td style="padding:10px 12px;font-size:12px;color:var(--text-secondary);max-width:220px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="' + notes + '">' + (notesShort || '<span style="color:var(--text-tertiary);">—</span>') + '</td>';
        html += '<td style="padding:10px 12px;font-size:12px;color:var(--text-secondary);white-space:nowrap;">' + created + '</td>';
        html += '<td style="padding:10px 12px;text-align:right;white-space:nowrap;">';
        html += '<button class="btn btn-ghost btn-sm" onclick="editFeedbackEntry(' + r.id + ')" title="Edit" style="padding:4px 8px;min-height:auto;">';
        html += '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" style="width:13px;height:13px;"><path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7" stroke-width="2"/><path d="M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5z" stroke-width="2"/></svg>';
        html += '</button> ';
        html += '<button class="btn btn-ghost btn-sm" onclick="deleteFeedbackEntry(' + r.id + ',\'' + escapeHtml((r.name || '').replace(/'/g, "\\'")) + '\')" title="Delete" style="padding:4px 8px;min-height:auto;color:var(--danger);">';
        html += '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" style="width:13px;height:13px;"><polyline points="3 6 5 6 21 6" stroke-width="2"/><path d="M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2" stroke-width="2"/></svg>';
        html += '</button>';
        html += '</td></tr>';
    }
    tbody.innerHTML = html;
    _renderPagination(data);
}

function _renderPagination(data) {
    var total = data.total || 0;
    var page = data.page || 1;
    var totalPages = data.total_pages || 1;
    var pageSize = data.page_size || 25;
    var start = total === 0 ? 0 : (page - 1) * pageSize + 1;
    var end = Math.min(page * pageSize, total);
    document.getElementById('fb-page-info').textContent = 'Showing ' + start + '–' + end + ' of ' + total + ' entries';
    var btns = document.getElementById('fb-page-buttons');
    if (!btns) return;
    var html = '';
    if (totalPages <= 1) { btns.innerHTML = ''; return; }
    html += '<button class="btn btn-ghost btn-sm" onclick="_fbGoPage(1)"' + (page <= 1 ? ' disabled' : '') + '>&laquo;</button>';
    html += '<button class="btn btn-ghost btn-sm" onclick="_fbGoPage(' + (page - 1) + ')"' + (page <= 1 ? ' disabled' : '') + '>&lsaquo;</button>';
    var startP = Math.max(1, page - 2);
    var endP = Math.min(totalPages, page + 2);
    for (var p = startP; p <= endP; p++) {
        html += '<button class="btn btn-sm' + (p === page ? ' btn-primary' : ' btn-ghost') + '" onclick="_fbGoPage(' + p + ')">' + p + '</button>';
    }
    html += '<button class="btn btn-ghost btn-sm" onclick="_fbGoPage(' + (page + 1) + ')"' + (page >= totalPages ? ' disabled' : '') + '>&rsaquo;</button>';
    html += '<button class="btn btn-ghost btn-sm" onclick="_fbGoPage(' + totalPages + ')"' + (page >= totalPages ? ' disabled' : '') + '>&raquo;</button>';
    btns.innerHTML = html;
}

function _fbGoPage(p) {
    _fbCurrentPage = p;
    loadFeedbackData();
}

function _fbFormatDate(iso) {
    if (!iso) return '—';
    try {
        var s = String(iso);
        var hasTZ = /[zZ]$|[+-]\d{2}:?\d{2}$/.test(s);
        if (!hasTZ && /\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/.test(s)) s += 'Z';
        var d = new Date(s);
        if (isNaN(d.getTime())) return iso;
        return d.toLocaleString('en-IN', {
            timeZone: 'Asia/Kolkata',
            month: 'short', day: 'numeric', year: 'numeric',
            hour: '2-digit', minute: '2-digit', hour12: true,
        });
    } catch (_) { return iso; }
}

function resetFeedbackForm() {
    document.getElementById('fb-edit-id').value = '';
    document.getElementById('fb-name').value = '';
    document.getElementById('fb-contact').value = '';
    document.getElementById('fb-status').value = '';
    document.getElementById('fb-custom-status').value = '';
    document.getElementById('fb-notes').value = '';
    document.getElementById('fb-custom-status-group').style.display = 'none';
    document.getElementById('feedback-form-title').textContent = 'Add New Feedback';
    document.getElementById('feedback-save-btn').innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" style="width:14px;height:14px;"><line x1="12" y1="5" x2="12" y2="19" stroke-width="2"/><line x1="5" y1="12" x2="19" y2="12" stroke-width="2"/></svg> Add Entry';
    document.getElementById('feedback-cancel-btn').style.display = 'none';
}

function cancelFeedbackEdit() {
    resetFeedbackForm();
}

async function saveFeedbackEntry() {
    var editId = document.getElementById('fb-edit-id').value;
    var name = (document.getElementById('fb-name').value || '').trim();
    var contact = (document.getElementById('fb-contact').value || '').trim();
    var status = (document.getElementById('fb-status').value || '').trim();
    var customStatus = (document.getElementById('fb-custom-status').value || '').trim();
    var notes = (document.getElementById('fb-notes').value || '').trim();

    if (!name) { showToast('Name is required', 'error'); document.getElementById('fb-name').focus(); return; }
    if (!contact) { showToast('Contact Number is required', 'error'); document.getElementById('fb-contact').focus(); return; }
    if (!status) { showToast('Lead Status is required', 'error'); document.getElementById('fb-status').focus(); return; }

    var body = {
        name: name,
        contact_number: contact,
        lead_status: status,
        custom_status: status === 'Others' ? customStatus : '',
        feedback_notes: notes,
    };

    try {
        var url, method;
        if (editId) {
            url = _fbApi('/' + editId);
            method = 'PATCH';
        } else {
            url = _fbApi('');
            method = 'POST';
        }
        var res = await fetch(url, {
            method: method,
            headers: authHeaders(),
            credentials: 'same-origin',
            body: JSON.stringify(body),
        });
        var data = await res.json();
        if (!res.ok) {
            showToast(data.detail || 'Failed to save', 'error');
            return;
        }
        showToast(editId ? 'Feedback updated' : 'Feedback added', 'success');
        resetFeedbackForm();
        loadFeedbackData();
    } catch (e) {
        console.error('saveFeedbackEntry error:', e);
        showToast('Network error', 'error');
    }
}

async function editFeedbackEntry(id) {
    try {
        // Fetch all and find locally, or just populate from table data
        var res = await fetch(_fbApi('?page=1&page_size=100&sort_by=id&sort_dir=DESC'), {
            headers: authHeaders(),
            credentials: 'same-origin',
        });
        if (!res.ok) return;
        var data = await res.json();
        var items = data.items || [];
        var entry = null;
        for (var i = 0; i < items.length; i++) {
            if (items[i].id === id) { entry = items[i]; break; }
        }
        if (!entry) {
            showToast('Entry not found', 'error');
            return;
        }
        document.getElementById('fb-edit-id').value = entry.id;
        document.getElementById('fb-name').value = entry.name || '';
        document.getElementById('fb-contact').value = entry.contact_number || '';
        document.getElementById('fb-status').value = entry.lead_status || '';
        document.getElementById('fb-custom-status').value = entry.custom_status || '';
        document.getElementById('fb-notes').value = entry.feedback_notes || '';
        toggleCustomStatus();
        document.getElementById('feedback-form-title').textContent = 'Edit Feedback';
        document.getElementById('feedback-save-btn').innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" style="width:14px;height:14px;"><path d="M19 21H5a2 2 0 01-2-2V5a2 2 0 012-2h11l5 5v11a2 2 0 01-2 2z" stroke-width="2"/><polyline points="17 21 17 13 7 13 7 21" stroke-width="2"/></svg> Update Entry';
        document.getElementById('feedback-cancel-btn').style.display = '';
        document.getElementById('fb-name').focus();
        window.scrollTo({ top: document.getElementById('feedback-form-card').offsetTop - 80, behavior: 'smooth' });
    } catch (e) {
        console.error('editFeedbackEntry error:', e);
    }
}

async function deleteFeedbackEntry(id, name) {
    if (!confirm('Delete feedback for "' + name + '"? This cannot be undone.')) return;
    try {
        var res = await fetch(_fbApi('/' + id), {
            method: 'DELETE',
            headers: authHeaders(),
            credentials: 'same-origin',
        });
        if (!res.ok) {
            var data = await res.json();
            showToast(data.detail || 'Failed to delete', 'error');
            return;
        }
        showToast('Feedback deleted', 'success');
        loadFeedbackData();
    } catch (e) {
        console.error('deleteFeedbackEntry error:', e);
        showToast('Network error', 'error');
    }
}

function exportFeedbackCSV() {
    var search = (document.getElementById('fb-search') || {}).value || '';
    var status = (document.getElementById('fb-filter-status') || {}).value || '';
    var params = new URLSearchParams();
    if (search) params.set('search', search);
    if (status) params.set('status', status);
    var url = _fbApi('/export' + (params.toString() ? '?' + params.toString() : ''));
    var t = token();
    if (t) url += (url.indexOf('?') >= 0 ? '&' : '?') + 'access_token=' + encodeURIComponent(t);
    window.location.href = url;
}
