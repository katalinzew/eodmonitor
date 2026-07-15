const ALERT_TYPES = ['ALL', 'AGENT_OFFLINE', 'SERVICE_DOWN', 'EOD_MISSING', 'HEALTH_WARNING'];
const STATUSES = ['ACTIVE', 'RESOLVED', 'ALL'];
const escapeHtml = value => String(value ?? '').replace(/[&<>'"]/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' }[char]));
const fmt = value => value === null || value === undefined || value === '' ? '-' : escapeHtml(value);
let selectedStatus = 'ACTIVE';
let searchTimer;

function parseDate(value) {
    if (!value) return null;
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? null : date;
}

function dateTime(value) {
    const date = parseDate(value);
    return date ? date.toLocaleString('ro-RO', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' }) : fmt(value);
}

function durationFrom(value, resolvedAt) {
    const start = parseDate(value);
    const end = parseDate(resolvedAt) || new Date();
    if (!start) return '-';
    const minutes = Math.max(0, Math.floor((end - start) / 60000));
    if (minutes < 1) return '<1 min';
    if (minutes < 60) return `${minutes} min`;
    const hours = Math.floor(minutes / 60);
    if (hours < 24) return `${hours}h ${minutes % 60}m`;
    return `${Math.floor(hours / 24)}z ${hours % 24}h`;
}

function alertBadge(type) {
    const safeType = ALERT_TYPES.includes(type) ? type : '';
    return `<span class="alert-badge ${safeType}">${fmt(type).replaceAll('_', ' ')}</span>`;
}

function renderSummary(summary = {}) {
    const activeTotal = summary.active_total || 0;
    document.getElementById('activeTotal').textContent = activeTotal;
    document.getElementById('agentOffline').textContent = summary.agent_offline || 0;
    document.getElementById('serviceDown').textContent = summary.service_down || 0;
    document.getElementById('eodMissing').textContent = summary.eod_missing || 0;
    document.getElementById('healthWarning').textContent = summary.health_warning || 0;
    document.getElementById('navAlertCount').textContent = activeTotal;
}

function renderAlerts(alerts = []) {
    document.getElementById('resultCount').textContent = `${alerts.length} ${alerts.length === 1 ? 'alertă' : 'alerte'}`;
    document.getElementById('alertsTable').innerHTML = alerts.map(alert => {
        const resolvedAt = alert.resolved_at || '';
        return `<tr class="${alert.resolved ? 'is-resolved' : 'is-active'}">
            <td><a class="store-link" href="/store/${encodeURIComponent(alert.store_code)}">${fmt(alert.store_code)}</a><div class="store-name" title="${fmt(alert.store_name)}">${fmt(alert.store_name)} · ${fmt(alert.host)}</div></td>
            <td>${alertBadge(alert.alert_type)}</td>
            <td class="target-cell" title="${fmt(alert.target)}">${fmt(alert.target)}</td>
            <td>${dateTime(alert.first_seen_at)}</td>
            <td class="duration-cell" data-start="${fmt(alert.first_seen_at)}" data-end="${fmt(resolvedAt)}">${durationFrom(alert.first_seen_at, resolvedAt)}</td>
            <td>${alert.email_sent ? '<span class="email-badge sent">Sent</span>' : '<span class="email-badge pending">Pending</span>'}</td>
            <td>${alert.resolved ? '<span class="status-badge resolved">Resolved</span>' : '<span class="status-badge active">Active</span>'}</td>
        </tr>`;
    }).join('') || '<tr><td colspan="7" class="table-message">Nu există alerte pentru filtrele selectate.</td></tr>';
}

function refreshDurations() {
    document.querySelectorAll('.duration-cell').forEach(cell => {
        cell.textContent = durationFrom(cell.dataset.start, cell.dataset.end || null);
    });
}

function currentFilters() {
    return {
        status: selectedStatus,
        alert_type: document.getElementById('typeFilter').value,
        search: document.getElementById('searchInput').value.trim()
    };
}

function updateSelectedControls(filters) {
    document.querySelectorAll('[data-status]').forEach(button => button.classList.toggle('active', button.dataset.status === filters.status));
    document.querySelectorAll('.alert-kpi').forEach(card => card.classList.toggle('selected', card.dataset.type === filters.alert_type && filters.status === 'ACTIVE'));
}

function syncUrl(filters) {
    const params = new URLSearchParams({ status: filters.status });
    if (filters.alert_type !== 'ALL') params.set('alert_type', filters.alert_type);
    if (filters.search) params.set('search', filters.search);
    history.replaceState(null, '', `${location.pathname}?${params}`);
    updateSelectedControls(filters);
}

async function loadAlerts() {
    const live = document.getElementById('liveState');
    const filters = currentFilters();
    syncUrl(filters);
    try {
        live.classList.remove('offline');
        live.innerHTML = '<span class="live-dot"></span>Refreshing';
        const response = await fetch(`/api/alerts?${new URLSearchParams(filters)}`, { cache: 'no-store' });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const data = await response.json();
        renderSummary(data.summary);
        renderAlerts(data.alerts);
        document.getElementById('lastUpdate').textContent = dateTime(new Date());
        live.innerHTML = '<span class="live-dot"></span>Live';
    } catch (error) {
        live.classList.add('offline');
        live.innerHTML = '<span class="live-dot"></span>Disconnected';
        document.getElementById('alertsTable').innerHTML = '<tr><td colspan="7" class="table-message">Alertele nu au putut fi încărcate.</td></tr>';
        console.error('Alerts load error:', error);
    }
}

function applyUrlFilters() {
    const params = new URLSearchParams(location.search);
    const status = params.get('status');
    const type = params.get('alert_type');
    const search = params.get('search');
    if (STATUSES.includes(status)) selectedStatus = status;
    if (ALERT_TYPES.includes(type)) document.getElementById('typeFilter').value = type;
    if (search) document.getElementById('searchInput').value = search;
}

document.querySelectorAll('[data-status]').forEach(button => button.addEventListener('click', () => { selectedStatus = button.dataset.status; loadAlerts(); }));
document.querySelectorAll('.alert-kpi').forEach(card => card.addEventListener('click', () => { selectedStatus = 'ACTIVE'; document.getElementById('typeFilter').value = card.dataset.type; loadAlerts(); }));
document.getElementById('typeFilter').addEventListener('change', loadAlerts);
document.getElementById('refreshButton').addEventListener('click', loadAlerts);
document.getElementById('searchInput').addEventListener('input', () => { clearTimeout(searchTimer); searchTimer = setTimeout(loadAlerts, 250); });

applyUrlFilters();
loadAlerts();
setInterval(loadAlerts, 30000);
setInterval(refreshDurations, 60000);
