// ─── Campaign Files Management ───
window.__CAMPAIGN_FILES_JS_LOADED = true;

let _campaignFiles = [];
let _campaignFilesSyncing = false;

async function refreshCampaignFiles() {
    if (_campaignFilesSyncing) return;
    _campaignFilesSyncing = true;
    try {
        const res = await fetch(apiUrl('/api/campaign/files?role=' + apiRoleQ()), {
            headers: { Authorization: 'Bearer ' + token() },
            credentials: 'same-origin',
        });
        if (res.status === 401 && typeof logout === 'function') logout();
        if (!res.ok) return;
        const data = await res.json().catch(() => ({}));
        _campaignFiles = data.files || [];
        renderCampaignFilesTable();
    } catch (e) {
        console.warn('refreshCampaignFiles failed:', e);
    } finally {
        _campaignFilesSyncing = false;
    }
}

function renderCampaignFilesTable() {
    const container = document.getElementById('campaign-files-list');
    if (!container) return;

    if (!_campaignFiles || _campaignFiles.length === 0) {
        container.innerHTML = '<div style="text-align:center;padding:var(--space-lg);color:var(--text-secondary);">No files uploaded yet.</div>';
        return;
    }

    let html = '<div style="overflow-x:auto;">';
    html += '<table style="width:100%;border-collapse:collapse;font-size:13px;">';
    html += '<thead><tr style="border-bottom:1px solid var(--border);">';
    html += '<th style="text-align:left;padding:8px 12px;font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.06em;color:var(--text-secondary);">File Name</th>';
    html += '<th style="text-align:left;padding:8px 12px;font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.06em;color:var(--text-secondary);">Uploaded</th>';
    html += '<th style="text-align:right;padding:8px 12px;font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.06em;color:var(--text-secondary);">Leads</th>';
    html += '<th style="text-align:center;padding:8px 12px;font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.06em;color:var(--text-secondary);">Status</th>';
    html += '<th style="text-align:center;padding:8px 12px;font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.06em;color:var(--text-secondary);">Active</th>';
    html += '<th style="text-align:right;padding:8px 12px;font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.06em;color:var(--text-secondary);">Actions</th>';
    html += '</tr></thead><tbody>';

    _campaignFiles.forEach(function(f) {
        const isActive = f.is_active === 1;
        const statusBadge = getFileStatusBadge(f.status);
        const activeBadge = isActive
            ? '<span style="display:inline-block;padding:2px 8px;border-radius:12px;font-size:11px;font-weight:700;background:var(--green,#10b981);color:#fff;">Currently Running</span>'
            : '<span style="color:var(--text-tertiary);font-size:12px;">—</span>';

        const uploadDate = f.upload_date ? formatDate(f.upload_date) : '—';
        const fileName = f.original_filename || f.filename || '—';
        const totalLeads = (f.total_leads || 0).toLocaleString();

        let actions = '';
        if (isActive) {
            actions = '<span style="color:var(--green,#10b981);font-weight:700;font-size:12px;">Active</span>';
        } else {
            actions = '<button class="btn btn-ghost btn-sm" onclick="selectCampaignFile(' + f.id + ')" style="font-size:11px;padding:4px 10px;">Select</button>';
        }

        const rowBg = isActive ? 'background:rgba(16,185,129,0.06);' : '';
        html += '<tr style="border-bottom:1px solid var(--border);' + rowBg + '">';
        html += '<td style="padding:10px 12px;font-weight:600;color:var(--text);max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="' + escapeHtml(fileName) + '">' + escapeHtml(fileName) + '</td>';
        html += '<td style="padding:10px 12px;color:var(--text-secondary);font-size:12px;">' + uploadDate + '</td>';
        html += '<td style="padding:10px 12px;text-align:right;font-weight:600;color:var(--text);">' + totalLeads + '</td>';
        html += '<td style="padding:10px 12px;text-align:center;">' + statusBadge + '</td>';
        html += '<td style="padding:10px 12px;text-align:center;">' + activeBadge + '</td>';
        html += '<td style="padding:10px 12px;text-align:right;">' + actions + '</td>';
        html += '</tr>';
    });

    html += '</tbody></table></div>';
    container.innerHTML = html;
}

function getFileStatusBadge(status) {
    const colors = {
        'not_started': { bg: 'var(--primary,#3b82f6)', fg: '#fff', label: 'Not Started' },
        'running': { bg: 'var(--green,#10b981)', fg: '#fff', label: 'Running' },
        'paused': { bg: '#f59e0b', fg: '#fff', label: 'Paused' },
        'completed': { bg: 'var(--text-tertiary,#9ca3af)', fg: '#fff', label: 'Completed' },
    };
    const c = colors[status] || colors['not_started'];
    return '<span style="display:inline-block;padding:2px 8px;border-radius:12px;font-size:11px;font-weight:700;background:' + c.bg + ';color:' + c.fg + ';">' + c.label + '</span>';
}

async function selectCampaignFile(fileId) {
    if (!confirm('Switch active file? This will stop any running campaign.')) return;
    try {
        const res = await fetch(apiUrl('/api/campaign/files/active?role=' + apiRoleQ()), {
            method: 'POST',
            headers: {
                Authorization: 'Bearer ' + token(),
                'Content-Type': 'application/json',
            },
            credentials: 'same-origin',
            body: JSON.stringify({ file_id: fileId }),
        });
        if (res.status === 401 && typeof logout === 'function') logout();
        if (!res.ok) {
            showToast(await parseApiErrorMessage(res), 'error');
            return;
        }
        const data = await res.json().catch(() => ({}));
        if (data.campaign_stopped) {
            showToast('Campaign stopped. New active file selected.', 'info');
        } else {
            showToast('Active file updated.', 'success');
        }
        await refreshCampaignFiles();
        if (typeof syncState === 'function') syncState();
    } catch (e) {
        showToast(e.message || 'Failed to select file', 'error');
    }
}

async function startFileCampaign(fileId) {
    try {
        const res = await fetch(apiUrl('/api/campaign/files/start?role=' + apiRoleQ()), {
            method: 'POST',
            headers: {
                Authorization: 'Bearer ' + token(),
                'Content-Type': 'application/json',
            },
            credentials: 'same-origin',
            body: JSON.stringify({ file_id: fileId }),
        });
        if (res.status === 401 && typeof logout === 'function') logout();
        if (!res.ok) {
            showToast(await parseApiErrorMessage(res), 'error');
            return;
        }
        const data = await res.json().catch(() => ({}));
        showToast('Campaign started!', 'success');
        await refreshCampaignFiles();
        if (typeof syncState === 'function') syncState();
    } catch (e) {
        showToast(e.message || 'Failed to start campaign', 'error');
    }
}

async function stopFileCampaign() {
    try {
        const res = await fetch(apiUrl('/api/campaign/files/stop?role=' + apiRoleQ()), {
            method: 'POST',
            headers: { Authorization: 'Bearer ' + token() },
            credentials: 'same-origin',
        });
        if (res.status === 401 && typeof logout === 'function') logout();
        if (!res.ok) {
            showToast(await parseApiErrorMessage(res), 'error');
            return;
        }
        showToast('Campaign stopped.', 'info');
        await refreshCampaignFiles();
        if (typeof syncState === 'function') syncState();
    } catch (e) {
        showToast(e.message || 'Failed to stop campaign', 'error');
    }
}

async function resumeFileCampaign() {
    try {
        const res = await fetch(apiUrl('/api/campaign/files/resume?role=' + apiRoleQ()), {
            method: 'POST',
            headers: { Authorization: 'Bearer ' + token() },
            credentials: 'same-origin',
        });
        if (res.status === 401 && typeof logout === 'function') logout();
        if (!res.ok) {
            showToast(await parseApiErrorMessage(res), 'error');
            return;
        }
        showToast('Campaign resumed!', 'success');
        await refreshCampaignFiles();
        if (typeof syncState === 'function') syncState();
    } catch (e) {
        showToast(e.message || 'Failed to resume campaign', 'error');
    }
}

function formatDate(dateStr) {
    try {
        const d = new Date(dateStr);
        if (isNaN(d.getTime())) return dateStr;
        const months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
        const month = months[d.getMonth()];
        const day = d.getDate();
        const hours = d.getHours();
        const mins = String(d.getMinutes()).padStart(2, '0');
        const ampm = hours >= 12 ? 'PM' : 'AM';
        const h12 = hours % 12 || 12;
        return month + ' ' + day + ', ' + h12 + ':' + mins + ' ' + ampm;
    } catch (e) {
        return dateStr;
    }
}

// Auto-refresh on page load and after upload
document.addEventListener('DOMContentLoaded', function() {
    setTimeout(refreshCampaignFiles, 1500);
});

// Hook into upload success to refresh files list
const _origUploadLeads = window.uploadLeads;
if (typeof _origUploadLeads === 'function') {
    window.uploadLeads = async function(input) {
        await _origUploadLeads.call(this, input);
        setTimeout(refreshCampaignFiles, 500);
    };
}
