const STORE_CODE = document.getElementById('storePage').dataset.storeCode;
const STATUS_CLASSES = ['OK', 'LATE', 'PROBLEM', 'MISSING', 'OFFLINE', 'NO_DATA'];
const escapeHtml = value => String(value ?? '').replace(/[&<>'"]/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' }[char]));
const fmt = value => value === null || value === undefined || value === '' ? '-' : escapeHtml(value);

function safeStatus(value) {
    return STATUS_CLASSES.includes(value) ? value : 'NO_DATA';
}

function parseDate(value) {
    if (!value) return null;
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? null : date;
}

function dateTime(value) {
    const date = parseDate(value);
    return date ? date.toLocaleString('ro-RO', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' }) : fmt(value);
}

function eventDate(value) {
    const date = parseDate(value);
    if (!date) return { time: '-', date: fmt(value) };
    return {
        time: date.toLocaleTimeString('ro-RO', { hour: '2-digit', minute: '2-digit' }),
        date: date.toLocaleDateString('ro-RO', { day: '2-digit', month: '2-digit', year: 'numeric' })
    };
}

function uptime(seconds) {
    const value = Number(seconds);
    if (!Number.isFinite(value) || value < 0) return '-';
    const days = Math.floor(value / 86400);
    const hours = Math.floor((value % 86400) / 3600);
    const minutes = Math.floor((value % 3600) / 60);
    return `${days ? `${days}z ` : ''}${hours}h ${minutes}m`;
}

function cleanMessage(value) {
    const messages = {
        'Nu exista fisier EOD': 'Nu există fișier EOD.',
        'Nu exista niciun fisier EOD': 'Nu există niciun fișier EOD.',
        'Nu exista fisier EOD pentru ziua curenta': 'Nu există fișier EOD pentru ziua curentă.',
        EOD_ENDED_OK: 'EOD finalizat cu succes.'
    };
    return fmt(messages[value] || value);
}

function statusBadge(status, label = status) {
    return `<span class="status-badge ${safeStatus(status)}">${fmt(label || 'NO_DATA')}</span>`;
}

function resourceMetric(label, value, warnAt, badAt) {
    const number = Number(value);
    const width = Number.isFinite(number) ? Math.min(100, Math.max(0, number)) : 0;
    const severity = !Number.isFinite(number) ? '' : number >= badAt ? 'bad' : number >= warnAt ? 'warn' : '';
    const display = Number.isFinite(number) ? `${number.toFixed(1)}%` : '-';
    return `<div class="resource-metric"><div class="resource-top"><span>${label}</span><strong>${display}</strong></div><div class="resource-bar"><div class="resource-fill ${severity}" style="width:${width}%"></div></div></div>`;
}

function renderServices(services, controlEnabled) {
    const entries = services && typeof services === 'object' ? Object.entries(services) : [];
    if (!entries.length) return '<div class="empty-state">Nu există servicii raportate.</div>';
    return entries.sort(([a], [b]) => a.localeCompare(b)).map(([name, value]) => {
        const active = String(value).toLowerCase() === 'active';
        const controls = controlEnabled ? `<div class="service-actions"><button type="button" data-service="${fmt(name)}" data-action="start">Start</button><button type="button" data-service="${fmt(name)}" data-action="stop">Stop</button><button type="button" data-service="${fmt(name)}" data-action="restart">Restart</button></div>` : '';
        return `<div class="service-row"><div class="service-summary"><span class="service-name" title="${fmt(name)}">${fmt(name)}</span><span class="service-state ${active ? 'active' : 'failed'}">${active ? '✓ Active' : '✕ Failed'}</span></div>${controls}</div>`;
    }).join('');
}

function normalizedEvent(event) {
    const type = event.event_type || '';
    if (type === 'HEARTBEAT_OFFLINE') return { label: 'AGENT_OFFLINE', tone: 'bad' };
    if (type === 'HEARTBEAT_ONLINE') return { label: 'AGENT_ONLINE', tone: 'ok' };
    if (type === 'SERVICE_DOWN') return { label: 'SERVICE_DOWN', tone: 'bad' };
    if (type === 'SERVICE_UP') return { label: 'SERVICE_UP', tone: 'ok' };
    if (type === 'HEALTH_WARNING') return { label: 'HEALTH_WARNING', tone: 'warn' };
    if (type === 'STATUS_CHANGE') {
        const next = String(event.new_value || '').toUpperCase();
        return next === 'OK' ? { label: 'EOD_OK', tone: 'ok' } : { label: 'EOD_MISSING', tone: next === 'LATE' ? 'warn' : 'bad' };
    }
    return { label: type || 'EVENT', tone: 'info' };
}

function renderTimeline(events) {
    if (!events.length) return '<div class="empty-state">Nu există evenimente.</div>';
    return [...events]
        .sort((a, b) => (parseDate(b.created_at)?.getTime() || 0) - (parseDate(a.created_at)?.getTime() || 0))
        .map(event => {
            const kind = normalizedEvent(event);
            const when = eventDate(event.created_at);
            return `<article class="timeline-event ${kind.tone}"><time class="event-when"><strong>${when.time}</strong><small>${when.date}</small></time><div class="event-content"><span class="event-badge">${kind.label}</span><div class="event-message">${cleanMessage(event.message)}</div></div></article>`;
        }).join('');
}

function renderHistory(history) {
    if (!history.length) return '<tr><td colspan="4" class="empty-state">Nu există istoric EOD.</td></tr>';
    return history.map(row => `<tr><td>${fmt(row.eod_date)}</td><td>${statusBadge(row.status)}</td><td>${dateTime(row.received_at)}</td><td>${cleanMessage(row.message)}</td></tr>`).join('');
}

function renderStore(data) {
    const store = data.store || {};
    const services = store.services_status || {};
    const events = data.events || [];
    const history = data.eod_history || [];
    const status = safeStatus(store.status);
    const heartbeatStatus = String(store.heartbeat_state || '').toUpperCase() === 'ONLINE' ? 'OK' : 'OFFLINE';

    document.getElementById('storeContent').innerHTML = `
        <section class="store-titlebar">
            <div class="store-identity"><h1>${fmt(store.store_code)} · ${fmt(store.store_name)}</h1><span>${fmt(store.host)} · ${fmt(store.hostname)}</span></div>
            <div class="status-group">${data.log_collection_enabled ? '<button type="button" class="collect-logs-button" data-open-log-modal>Collect Logs</button>' : ''}${statusBadge(status, `Overall ${status}`)}${statusBadge(heartbeatStatus, `Agent ${store.heartbeat_state || 'NO_DATA'}`)}</div>
        </section>
        <div class="store-layout">
            <div class="store-column primary-column">
                <article class="store-card overview-card"><header class="card-head"><h2>Overview</h2><small>Identitate și stare curentă</small></header><div class="overview-grid">
                    <div class="data-item"><span>Store Code</span><strong>${fmt(store.store_code)}</strong></div>
                    <div class="data-item name-item"><span>Store Name</span><strong>${fmt(store.store_name)}</strong></div>
                    <div class="data-item status-item"><span>Overall Status</span><strong>${statusBadge(status)}</strong></div>
                    <div class="data-item"><span>Hostname</span><strong>${fmt(store.hostname)}</strong></div>
                    <div class="data-item"><span>IP</span><strong>${fmt(store.host)}</strong></div>
                    <div class="data-item"><span>Agent Version</span><strong>${fmt(store.agent_version)}</strong></div>
                    <div class="data-item"><span>Uptime</span><strong>${uptime(store.uptime_seconds)}</strong></div>
                    <div class="data-item"><span>Ultimul heartbeat</span><strong>${dateTime(store.last_heartbeat)}</strong></div>
                </div></article>
                <article class="store-card"><header class="card-head"><h2>System Resources</h2><small>Utilizare curentă</small></header><div class="resource-grid">${resourceMetric('CPU', store.cpu_load_1m, 70, 90)}${resourceMetric('RAM', store.ram_percent, 75, 90)}${resourceMetric('Disk', store.disk_percent, 80, 90)}</div></article>
                <article class="store-card"><header class="card-head"><h2>Services</h2><small>${data.service_control_enabled ? 'Control remote activ' : `${Object.keys(services).length} raportate`}</small></header><div class="services-list">${renderServices(services, data.service_control_enabled)}</div><div class="command-feedback" id="commandFeedback" aria-live="polite"></div></article>
                <article class="store-card"><header class="card-head"><h2>Timeline</h2><small>${events.length} evenimente · cele mai noi primele</small></header><div class="timeline-scroll"><div class="timeline-list">${renderTimeline(events)}</div></div></article>
            </div>
            <aside class="store-column secondary-column">
                <article class="store-card"><header class="card-head"><h2>EOD</h2>${statusBadge(status)}</header><div class="fact-list">
                    <div class="fact-row"><span>Status EOD</span><strong>${fmt(status)}</strong></div>
                    <div class="fact-row"><span>Ultimul EOD</span><strong>${dateTime(store.eod_file_created_at || store.eod_date)}</strong></div>
                    <div class="fact-row"><span>Valid Until (TTL)</span><strong>${dateTime(store.ok_valid_until)}</strong></div>
                    <div class="fact-row"><span>Schedule</span><strong>${fmt(store.schedule_time)}</strong></div>
                    <div class="fact-row message-row"><span>Mesaj</span><strong>${cleanMessage(store.message)}</strong></div>
                </div></article>
                <article class="store-card"><header class="card-head"><h2>Store Information</h2><small>Detalii nod</small></header><div class="fact-list">
                    <div class="fact-row"><span>Cod</span><strong>${fmt(store.store_code)}</strong></div><div class="fact-row"><span>Nume</span><strong>${fmt(store.store_name)}</strong></div><div class="fact-row"><span>Hostname</span><strong>${fmt(store.hostname)}</strong></div><div class="fact-row"><span>IP</span><strong>${fmt(store.host)}</strong></div><div class="fact-row"><span>Program EOD</span><strong>${fmt(store.schedule_time)}</strong></div><div class="fact-row"><span>Versiune agent</span><strong>${fmt(store.agent_version)}</strong></div><div class="fact-row"><span>Ultimul heartbeat</span><strong>${dateTime(store.last_heartbeat)}</strong></div>
                </div></article>
                <article class="store-card"><header class="card-head"><h2>EOD History</h2><small>Ultimele ${history.length} înregistrări</small></header><div class="history-scroll"><table class="history-table"><thead><tr><th>Date</th><th>Status</th><th>Received</th><th>Message</th></tr></thead><tbody>${renderHistory(history)}</tbody></table></div></article>
            </aside>
        </div>`;
    renderLogOptions(data.available_logs || []);
}

function renderLogOptions(logs) {
    document.getElementById('logOptions').innerHTML = logs.map(log => `
        <label class="log-option">
            <input type="checkbox" name="logKey" value="${fmt(log.key)}" checked>
            <span><strong>${fmt(log.label)}</strong><small>${fmt(log.filename)}</small></span>
        </label>`).join('');
}

function setLogStatus(message, tone = '') {
    const status = document.getElementById('logRequestStatus');
    status.textContent = message;
    status.className = `log-request-status ${tone}`.trim();
}

function openLogModal() {
    const modal = document.getElementById('logModal');
    modal.hidden = false;
    document.body.classList.add('modal-open');
    setLogStatus('');
}

function closeLogModal() {
    document.getElementById('logModal').hidden = true;
    document.body.classList.remove('modal-open');
}

async function waitForLogCollection(requestId) {
    for (let attempt = 0; attempt < 30; attempt += 1) {
        await new Promise(resolve => setTimeout(resolve, 4000));
        const response = await fetch(`/api/stores/${encodeURIComponent(STORE_CODE)}/log-collections/${requestId}`, { cache: 'no-store' });
        if (!response.ok) throw new Error(`Status HTTP ${response.status}`);
        const data = await response.json();
        if (data.status === 'PENDING') setLogStatus('Cererea așteaptă să fie preluată de agent...');
        if (data.status === 'RUNNING') setLogStatus('Agentul arhivează și încarcă logurile...');
        if (data.status === 'SUCCEEDED') {
            setLogStatus('Arhiva a fost trimisă prin email.', 'success');
            return;
        }
        if (data.status === 'FAILED') throw new Error(data.message || 'Colectarea logurilor a eșuat');
    }
    throw new Error('Agentul nu a finalizat cererea în timpul așteptat');
}

async function submitLogCollection(event) {
    event.preventDefault();
    const keys = [...document.querySelectorAll('input[name="logKey"]:checked')].map(input => input.value);
    if (!keys.length) {
        setLogStatus('Selectează cel puțin un fișier.', 'error');
        return;
    }
    const submit = document.getElementById('collectLogsSubmit');
    submit.disabled = true;
    setLogStatus('Se creează cererea...');
    try {
        const response = await fetch(`/api/stores/${encodeURIComponent(STORE_CODE)}/log-collections`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ log_keys: keys })
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(data.detail || `HTTP ${response.status}`);
        await waitForLogCollection(data.id);
    } catch (error) {
        setLogStatus(error.message, 'error');
    } finally {
        submit.disabled = false;
    }
}

async function queueServiceCommand(button) {
    const service = button.dataset.service;
    const action = button.dataset.action;
    if (!window.confirm(`${action.toUpperCase()} ${service}?`)) return;
    const feedback = document.getElementById('commandFeedback');
    button.disabled = true;
    feedback.textContent = `Se trimite comanda ${action}...`;
    feedback.className = 'command-feedback visible';
    try {
        const response = await fetch(`/api/stores/${encodeURIComponent(STORE_CODE)}/service-commands`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ service_name: service, action })
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(data.detail || `HTTP ${response.status}`);
        feedback.textContent = `Comanda ${action} a fost pusă în coadă. Agentul o va prelua în maximum 60 secunde.`;
        setTimeout(loadStore, 65000);
    } catch (error) {
        feedback.textContent = `Comanda nu a putut fi trimisă: ${error.message}`;
        feedback.classList.add('error');
    } finally {
        button.disabled = false;
    }
}

async function loadAlertCount() {
    try {
        const response = await fetch('/api/alerts?status=ACTIVE&alert_type=ALL&search=', { cache: 'no-store' });
        if (!response.ok) return;
        const data = await response.json();
        document.getElementById('navAlertCount').textContent = data.summary?.active_total || 0;
    } catch (error) {
        console.error('Alert count error:', error);
    }
}

async function loadStore() {
    const live = document.getElementById('liveState');
    try {
        live.classList.remove('offline');
        live.innerHTML = '<span class="live-dot"></span>Refreshing';
        const response = await fetch(`/api/store/${encodeURIComponent(STORE_CODE)}`, { cache: 'no-store' });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        renderStore(await response.json());
        document.getElementById('lastUpdate').textContent = dateTime(new Date());
        live.innerHTML = '<span class="live-dot"></span>Live';
    } catch (error) {
        live.classList.add('offline');
        live.innerHTML = '<span class="live-dot"></span>Disconnected';
        document.getElementById('storeContent').innerHTML = `<div class="loading-card">Nu s-au putut încărca datele pentru magazinul ${fmt(STORE_CODE)}.</div>`;
        console.error('Store load error:', error);
    }
}

async function loadPage() {
    await Promise.allSettled([loadStore(), loadAlertCount()]);
}

document.getElementById('refreshButton').addEventListener('click', loadPage);
document.getElementById('storeContent').addEventListener('click', event => {
    if (event.target.closest('[data-open-log-modal]')) openLogModal();
    const button = event.target.closest('button[data-service][data-action]');
    if (button) queueServiceCommand(button);
});
document.getElementById('logCollectionForm').addEventListener('submit', submitLogCollection);
document.getElementById('logModal').addEventListener('click', event => {
    if (event.target.closest('[data-close-log-modal]')) closeLogModal();
});
document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && !document.getElementById('logModal').hidden) closeLogModal();
});
loadPage();
setInterval(loadPage, 30000);
