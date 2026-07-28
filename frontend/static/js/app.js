// ─── Global State ───
let currentRole = 'data_edge';
const CONSOLE_SWITCHABLE_ROLES = ['buyers', 'sellers', 'rfqs'];
let allLeads = [];
let allLogs = [];
let currentFilter = 'all';
let syncInterval = null;
let campaignWorkerActive = false;

// ─── Theme Toggle ───
function toggleTheme() {
  var html = document.documentElement;
  var isDark = html.getAttribute('data-theme') === 'dark';
  html.setAttribute('data-theme', isDark ? '' : 'dark');
  localStorage.setItem('de_theme', isDark ? 'light' : 'dark');
  updateThemeUI(!isDark);
}

function updateThemeUI(isDark) {
  var lbl = document.getElementById('theme-toggle-label');
  var path = document.getElementById('theme-icon-path');
  if (!lbl || !path) return;
  lbl.textContent = isDark ? 'Light Mode' : 'Dark Mode';
  path.setAttribute('d', isDark
    ? 'M21 12.79A9 9 0 1111.21 3 7 7 0 0021 12.79z'
    : 'M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z');
}

function _clearRoleSessionSnapshots(role) {
    try {
        sessionStorage.removeItem('vernika_dash_snap_' + role);
        sessionStorage.removeItem('vernika_dash_snap_v2_' + role);
        sessionStorage.removeItem('vernika_leads_snap_' + role);
        sessionStorage.removeItem('vernika_leads_snap_v2_' + role);
    } catch (_) {}
}

function _loginRole() {
    if (typeof loginRoleFromToken === 'function') {
        const fromJwt = loginRoleFromToken();
        if (fromJwt) return fromJwt;
    }
    return normalizeRole(localStorage.getItem('vernika_role') || 'data_edge');
}

function _isDataEdgeCounselorSession() {
    return _loginRole() === 'data_edge';
}

/** After login, align UI + storage with JWT so stale ``vernika_role=sellers`` cannot hijack the dashboard. */
function _applyLockedLoginRole() {
    const sess = window.__VERN_SESSION__;
    if (sess && sess.dashboard_role && (!sess.can_switch_roles || sess.locked)) {
        currentRole = normalizeRole(sess.dashboard_role);
        localStorage.setItem('vernika_role', currentRole);
        return;
    }
    const locked =
        typeof loginRoleFromToken === 'function' ? loginRoleFromToken() : null;
    if (!locked || typeof LOCKED_CONSOLE_ROLES === 'undefined') return;
    if (!LOCKED_CONSOLE_ROLES.includes(locked)) return;
    currentRole = locked;
    localStorage.setItem('vernika_role', locked);
}

/** Role for Configuration / greeting capture APIs (visible tab, not stale toggle). */
function tuningRoleForApi() {
    if (_isDataEdgeCounselorSession()) {
        return 'data_edge';
    }
    if (CONSOLE_SWITCHABLE_ROLES.includes(currentRole)) {
        return currentRole;
    }
    const loginRole = normalizeRole(localStorage.getItem('vernika_role') || 'sellers');
    return loginRole;
}

function _initialConsoleRole() {
    const jwtRole =
        typeof loginRoleFromToken === 'function' ? loginRoleFromToken() : null;
    if (jwtRole && typeof LOCKED_CONSOLE_ROLES !== 'undefined' && LOCKED_CONSOLE_ROLES.includes(jwtRole)) {
        return jwtRole;
    }
    const stored = normalizeRole(localStorage.getItem('vernika_role') || '');
    const VALID_ALL = CONSOLE_SWITCHABLE_ROLES.concat(['data_edge', 'real_estate', 'vernikaai', 'admin']);
    if (VALID_ALL.includes(stored)) {
        return stored;
    }
    return jwtRole || 'data_edge';
}

function _updateRoleToggleVisibility() {
    const sw = document.getElementById('role-switch');
    if (!sw) return;
    const sess = window.__VERN_SESSION__;
    if (sess && sess.locked === false && sess.can_switch_roles) {
        sw.style.display = 'grid';
        return;
    }
    if (sess && (sess.locked || !sess.can_switch_roles)) {
        sw.style.display = 'none';
        return;
    }
    const hiddenRoles = ['data_edge', 'vernikaai', 'admin'];
    sw.style.display = hiddenRoles.includes(_loginRole()) ? 'none' : '';
}

function updateRoleSwitchUI() {
    document.querySelectorAll('.role-switch-btn').forEach(function (btn) {
        const r = btn.getAttribute('data-role');
        btn.classList.toggle('active', r === currentRole);
        btn.setAttribute('aria-pressed', r === currentRole ? 'true' : 'false');
    });
    const toolbar = document.querySelector('.mobile-toolbar-title');
    if (toolbar) {
        const labels = {
            data_edge: 'Data Edge',
            sellers: 'Sellers',
            buyers: 'Buyers',
            rfqs: 'RFQ',
        };
        toolbar.textContent = labels[currentRole] || 'PitchX';
    }
    _updateRoleToggleVisibility();
}

function switchRole(role) {
    const next = normalizeRole(role);
    if (!CONSOLE_SWITCHABLE_ROLES.includes(next)) return;
    if (next === currentRole) return;

    currentRole = next;
    localStorage.setItem('vernika_role', currentRole);

    const p = document.getElementById('tuning-prompt');
    const r = document.getElementById('tuning-rag');
    const g = document.getElementById('tuning-greeting');
    if (p) p.value = '';
    if (r) r.value = '';
    if (g) g.value = '';

    allLeads = [];
    allLogs = [];
    currentFilter = 'all';
    campaignWorkerActive = false;

    updateRoleLabels();
    updateRoleSwitchUI();

    if (typeof loadTuning === 'function') loadTuning();
    if (typeof loadCases === 'function') loadCases();
    if (typeof loadSchedules === 'function') loadSchedules();
    if (typeof loadInboundCallbacks === 'function') loadInboundCallbacks();
    if (typeof loadRecentManualCalls === 'function') loadRecentManualCalls();
    if (typeof syncState === 'function') syncState();

    if (typeof showToast === 'function') {
        const label = { buyers: 'Buyers', sellers: 'Sellers', rfqs: 'RFQ' }[currentRole] || currentRole;
        showToast('Switched to ' + label, 'info', 2200);
    }
}

// ─── Initialization ───
document.addEventListener('DOMContentLoaded', () => {
    if (!token()) { window.location.href = '/login'; return; }

    (async function initConsole() {
        try {
            if (typeof bootstrapConsoleSession === 'function') {
                await bootstrapConsoleSession();
            }
        } catch (err) {
            console.error('Session bootstrap failed:', err);
            _applyLockedLoginRole();
            currentRole = _initialConsoleRole();
        }
        _applyLockedLoginRole();
        if (!window.__VERN_SESSION__) {
            currentRole = _initialConsoleRole();
            _applyLockedLoginRole();
        }
        const VALID_ALL = CONSOLE_SWITCHABLE_ROLES.concat(['data_edge', 'real_estate', 'vernikaai', 'admin']);
        if (
            currentRole !== 'data_edge' &&
            !VALID_ALL.includes(currentRole)
        ) {
            currentRole = 'data_edge';
            localStorage.setItem('vernika_role', currentRole);
        }

        updateRoleLabels();
        updateRoleSwitchUI();
        _updateRoleToggleVisibility();

        var savedTheme = localStorage.getItem('de_theme') || 'light';
        document.documentElement.setAttribute('data-theme', savedTheme === 'dark' ? 'dark' : '');
        updateThemeUI(savedTheme === 'dark');

        if (typeof restoreDashboardSnapshotFromSession === 'function') {
            restoreDashboardSnapshotFromSession();
        }
        if (typeof restoreLeadTablesFromSession === 'function') {
            restoreLeadTablesFromSession();
        }

        try {
            initCharts();
        } catch (err) {
            console.error('Chart init failed — stats will still load:', err);
            if (typeof showToast === 'function') {
                showToast('Charts failed to load (check network/CDN). KPI numbers will still sync.', 'warning', 6500);
            }
        }

        loadTuning();
        loadCases();
        _initScheduleDefaults();
        loadSchedules();

        setInterval(loadSchedules, 30000);
        syncState();
        syncInterval = setInterval(syncState, 15000);

        document.addEventListener('visibilitychange', () => {
            if (document.hidden) {
                if (syncInterval) { clearInterval(syncInterval); syncInterval = null; }
            } else {
                if (!syncInterval) {
                    syncState();
                    syncInterval = setInterval(syncState, 15000);
                }
            }
        });

        const settingsUrlEl = document.getElementById('settings-url');
        if (settingsUrlEl) {
            settingsUrlEl.textContent = window.location.origin;
        }

        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') closeMobileSidebar();
        });
        window.addEventListener('resize', () => {
            if (window.innerWidth > 900) closeMobileSidebar();
        });
    })();
});

// ─── Sidebar & Navigation ───
/** Scroll to greeting + prerecord controls (Configuration tab). */
function openPreRecordSetup() {
    showPageNav('tuning', document.getElementById('nav-tuning'));
    closeMobileSidebar();
    setTimeout(() => {
        const g = document.getElementById('tuning-greeting');
        const card = document.getElementById('tuning-greeting-card');
        (card || g)?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }, 80);
}

function closeMobileSidebar() {
    const shell = document.getElementById('app-shell');
    const backdrop = document.getElementById('sidebar-backdrop');
    if (shell) shell.classList.remove('sidebar-open');
    if (backdrop) backdrop.classList.remove('visible');
    document.body.classList.remove('nav-drawer-open');
}

function toggleMobileSidebar(ev) {
    if (ev) ev.stopPropagation();
    const shell = document.getElementById('app-shell');
    if (!shell) return;
    const open = !shell.classList.contains('sidebar-open');
    shell.classList.toggle('sidebar-open', open);
    const backdrop = document.getElementById('sidebar-backdrop');
    if (backdrop) backdrop.classList.toggle('visible', open);
    document.body.classList.toggle('nav-drawer-open', open);
}

function showPageNav(pageId, navEl) {
    showPage(pageId, navEl);
    closeMobileSidebar();
    if (pageId === 'agents') loadAgents();
    if (pageId === 'feedback' && typeof loadFeedbackData === 'function') {
        loadFeedbackData();
    }
}

function showPage(pageId, navEl) {
    document.querySelectorAll('.page-section').forEach(s => s.classList.remove('active'));
    document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
    const el = document.getElementById('page-' + pageId);
    if (el) el.classList.add('active');
    if (navEl) navEl.classList.add('active');
    if (pageId === 'manual' && typeof loadRecentManualCalls === 'function') {
        loadRecentManualCalls();
    }
}

function updateRoleLabels() {
    const ROLE_LABELS = {
        sellers: 'Sellers',
        buyers: 'Buyers',
        rfqs: 'RFQ',
        data_edge: 'Data Edge',
        real_estate: 'Real Estate',
        vernikaai: 'VernikaAI',
        admin: 'Admin'
    };
    const label = ROLE_LABELS[currentRole] || (currentRole.charAt(0).toUpperCase() + currentRole.slice(1));

    const elIds = ['role-badge', 'role-label-dash', 'tuning-role-label', 'test-role-label', 'manual-role-label', 'cases-role-label'];
    elIds.forEach(id => {
        const el = document.getElementById(id);
        if (el) el.textContent = label;
    });

    const badge = document.getElementById('role-badge');
    const sess = window.__VERN_SESSION__;
    if (badge && sess && sess.email) {
        badge.textContent = label + ' · ' + String(sess.email).split('@')[0];
        badge.title = sess.email;
    }

    updateRoleSwitchUI();

    const agentsNav = document.getElementById('nav-agents');
    if (agentsNav) {
        agentsNav.style.display = 'none';
    }
}

function logout() {
    if (syncInterval) clearInterval(syncInterval);
    localStorage.removeItem('vernika_token');
    localStorage.removeItem('vernika_role');
    try {
        CONSOLE_SWITCHABLE_ROLES.concat(['data_edge']).forEach(_clearRoleSessionSnapshots);
    } catch (_) {}
    window.location.href = '/login';
}

function openModal(id) {
    const el = document.getElementById(id);
    if (el) {
        el.classList.add('active');
        el.classList.add('open');
    }
}
function closeModal(id) {
    const el = document.getElementById(id);
    if (el) {
        el.classList.remove('active');
        el.classList.remove('open');
    }
}

(function patchCaseModalOpen() {
    const base = typeof openModal === 'function' ? openModal : null;
    if (!base) return;
    window.openModal = function patchedOpenModal(id) {
        if (id === 'modal-case') {
            const hid = document.getElementById('case-edit-id');
            if (hid && !String(hid.value || '').trim()) {
                try {
                    _resetCaseModal();
                } catch (_) {}
            }
        }
        return base(id);
    };
})();
