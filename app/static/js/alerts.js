function fmt(value) {
    return value === null || value === undefined || value === '' ? '-' : value;
}

function dateTime(value) {
    if (!value) return '-';

    const d = new Date(value);

    if (isNaN(d)) {
        return value;
    }

    return d.toLocaleString('ro-RO');
}

function durationFrom(value, resolvedAt) {
    if (!value) return '-';

    const start = new Date(value);
    const end = resolvedAt ? new Date(resolvedAt) : new Date();

    if (isNaN(start) || isNaN(end)) return '-';

    const diffMs = Math.max(0, end - start);
    const mins = Math.floor(diffMs / 60000);

    if (mins < 1) return '<1 min';
    if (mins < 60) return mins + ' min';

    const h = Math.floor(mins / 60);
    const m = mins % 60;

    if (h < 24) return `${h}h ${m}m`;

    const d = Math.floor(h / 24);
    const rh = h % 24;

    return `${d}d ${rh}h`;
}

function alertBadge(type) {
    return `<span class="alert-badge ${type}">${fmt(type)}</span>`;
}

function statusBadge(resolved) {
    if (resolved) {
        return '<span class="status-badge resolved">Resolved</span>';
    }

    return '<span class="status-badge active">Active</span>';
}

function emailBadge(sent) {
    if (sent) {
        return '<span class="email-badge sent">Sent</span>';
    }

    return '<span class="email-badge pending">Pending</span>';
}

async function loadAlerts() {
    const live = document.getElementById('liveState');

    const status = document.getElementById('statusFilter').value;
    const alertType = document.getElementById('typeFilter').value;
    const search = document.getElementById('searchInput').value.trim();

    const params = new URLSearchParams({
        status: status,
        alert_type: alertType,
        search: search
    });

    try {
        live.classList.remove('offline');
        live.innerHTML = '<span class="live-dot"></span>Refreshing';

        const response = await fetch('/api/alerts?' + params.toString());

        if (!response.ok) {
            throw new Error('HTTP ' + response.status);
        }

        const data = await response.json();

        renderSummary(data.summary);
        renderAlerts(data.alerts);

        live.classList.remove('offline');
        live.innerHTML = '<span class="live-dot"></span>Live';

    } catch (error) {
        live.classList.add('offline');
        live.innerHTML = '<span class="live-dot"></span>Disconnected';
        console.error(error);
    }
}

function renderSummary(summary) {
    document.getElementById('activeTotal').innerText = summary.active_total || 0;
    document.getElementById('agentOffline').innerText = summary.agent_offline || 0;
    document.getElementById('serviceDown').innerText = summary.service_down || 0;
    document.getElementById('eodMissing').innerText = summary.eod_missing || 0;
    document.getElementById('healthWarning').innerText = summary.health_warning || 0;
}

function renderAlerts(alerts) {
    let html = '';

    alerts.forEach(alert => {
        html += `
            <tr>
                <td>
                    <a class="store-link" href="/store/${alert.store_code}">
                        ${fmt(alert.store_code)}
                    </a>
                    <div class="store-name">${fmt(alert.store_name)}</div>
                </td>
                <td>${alertBadge(alert.alert_type)}</td>
                <td>${fmt(alert.target)}</td>
                <td>${dateTime(alert.first_seen_at)}</td>
                <td>${durationFrom(alert.first_seen_at, alert.resolved_at)}</td>
                <td>${emailBadge(alert.email_sent)}</td>
                <td>${statusBadge(alert.resolved)}</td>
            </tr>
        `;
    });

    document.getElementById('alertsTable').innerHTML =
        html || '<tr><td colspan="7">Nu există alerte pentru filtrul selectat.</td></tr>';
}

loadAlerts();
setInterval(loadAlerts, 30000);