function fmt(value) {
    return value === null || value === undefined || value === '' ? '-' : value;
}

function pct(value) {
    if (value === null || value === undefined || value === '') return '-';
    return Number(value).toFixed(1) + '%';
}

function dateTime(value) {
    if (!value) return '-';

    const d = new Date(value);

    if (isNaN(d)) {
        return value;
    }

    return d.toLocaleString('ro-RO');
}

function uptime(seconds) {
    if (!seconds) return '-';

    const days = Math.floor(seconds / 86400);
    const hours = Math.floor((seconds % 86400) / 3600);

    return `${days}z ${hours}h`;
}

function severityClass(value, warnAt, badAt) {
    if (value === null || value === undefined || value === '') return 'ok';

    const num = Number(value);

    if (num >= badAt) return 'bad';
    if (num >= warnAt) return 'warn';

    return 'ok';
}

function bigBar(label, value, warnAt, badAt) {
    const cls = severityClass(value, warnAt, badAt);
    const width = value === null || value === undefined || value === '' ? 0 : Math.min(Number(value), 100);

    return `
        <div class="big-metric">
            <div class="big-metric-top">
                <span>${label}</span>
                <strong>${pct(value)}</strong>
            </div>
            <div class="big-bar">
                <div class="big-bar-fill ${cls}" style="width:${width}%"></div>
            </div>
        </div>
    `;
}

function eventLabel(type) {
    const labels = {
        "HEARTBEAT_OFFLINE": "Agent offline",
        "HEARTBEAT_ONLINE": "Agent online",
        "SERVICE_DOWN": "Serviciu oprit",
        "SERVICE_UP": "Serviciu activ",
        "SERVICE_CHANGE": "Serviciu schimbat",
        "SERVICE_STATUS": "Status serviciu",
        "STATUS_CHANGE": "Status EOD schimbat"
    };

    return labels[type] || type || '-';
}

function cleanMessage(value) {
    if (!value) return '-';

    const map = {
        "Nu exista fisier EOD": "Nu există fișier EOD.",
        "Nu exista niciun fisier EOD": "Nu există niciun fișier EOD.",
        "Nu exista fisier EOD pentru ziua curenta": "Nu există fișier EOD pentru ziua curentă.",
        "EOD_ENDED_OK": "EOD finalizat cu succes."
    };

    return map[value] || value;
}

function renderServices(services) {
    let html = '';

    Object.keys(services).sort().forEach(name => {
        const status = services[name] || 'unknown';
        const cls = status === 'active' ? 'ok' : 'bad';

        html += `
            <div class="service-chip ${cls}">
                <span>${name}</span>
                <strong>${status}</strong>
            </div>
        `;
    });

    return html || '<div class="small">Nu există servicii raportate.</div>';
}

function renderTimeline(events) {
    let html = '';

    events.forEach(event => {
        const type = event.event_type || '';

        const cls = type.includes('DOWN') || type.includes('OFFLINE') ? 'bad'
            : type.includes('UP') || type.includes('ONLINE') ? 'ok'
            : 'info';

        html += `
            <div class="timeline-item ${cls}">
                <div class="timeline-dot"></div>
                <div>
                    <div class="timeline-title">${eventLabel(event.event_type)}</div>
                    <div class="timeline-msg">${fmt(event.message)}</div>
                    <div class="small">${dateTime(event.created_at)}</div>
                </div>
            </div>
        `;
    });

    return html || '<div class="small">Nu există evenimente.</div>';
}

function renderHistory(history) {
    let html = '';

    history.forEach(row => {
        const status = row.status || 'NO_DATA';

        html += `
            <tr>
                <td>${fmt(row.eod_date)}</td>
                <td><span class="badge ${status}">${fmt(status)}</span></td>
                <td>${fmt(row.eod_file)}</td>
                <td>${cleanMessage(row.message)}</td>
                <td>${dateTime(row.eod_file_created_at)}</td>
            </tr>
        `;
    });

    return html || `
        <tr>
            <td colspan="5" class="small">Nu există istoric EOD.</td>
        </tr>
    `;
}

async function loadStore() {
    const live = document.getElementById('liveState');

    try {
        live.classList.remove('offline');
        live.innerHTML = '<span class="live-dot"></span>Refreshing';

        const response = await fetch('/api/store/' + STORE_CODE);

        if (!response.ok) {
            throw new Error('HTTP ' + response.status);
        }

        const data = await response.json();

        const store = data.store;
        const services = store.services_status || {};
        const events = data.events || [];
        const history = data.eod_history || [];

        document.getElementById('storeContent').innerHTML = `
            <section class="store-hero">
                <div>
                    <div class="hero-eyebrow">Store node</div>
                    <h1>${fmt(store.store_code)} — ${fmt(store.store_name)}</h1>
                    <p>${fmt(store.host)} • ${fmt(store.hostname)} • ${fmt(store.os_info)}</p>
                </div>

                <span class="badge ${store.status}">${fmt(store.status)}</span>
            </section>

            <section class="details-grid">
                <div class="details-card">
                    <div class="details-title">EOD Status</div>
                    <div class="details-main">${fmt(store.status)}</div>
                    <div class="small">Fișier: ${fmt(store.eod_file)}</div>
                    <div class="small">Mesaj: ${cleanMessage(store.message)}</div>
                    <div class="small">Valid până la: ${dateTime(store.ok_valid_until)}</div>
                </div>

                <div class="details-card">
                    <div class="details-title">Agent</div>
                    <div class="details-main">${fmt(store.heartbeat_state)}</div>
                    <div class="small">Heartbeat: ${dateTime(store.last_heartbeat)}</div>
                    <div class="small">Versiune: ${fmt(store.agent_version)}</div>
                    <div class="small">Uptime: ${uptime(store.uptime_seconds)}</div>
                </div>

                <div class="details-card">
                    <div class="details-title">System Resources</div>
                    ${bigBar('CPU', store.cpu_load_1m, 70, 90)}
                    ${bigBar('RAM', store.ram_percent, 75, 90)}
                    ${bigBar('Disk', store.disk_percent, 80, 90)}
                </div>
            </section>

            <section class="details-grid two">
                <div class="details-card">
                    <div class="details-title">Services</div>
                    <div class="service-list">${renderServices(services)}</div>
                </div>

                <div class="details-card">
                    <div class="details-title">Timeline</div>
                    <div class="timeline-scroll">
                        <div class="timeline">${renderTimeline(events)}</div>
                    </div>
                </div>
            </section>

            <section class="details-card">
                <div class="details-title">EOD History</div>
                <div class="history-scroll">
                    <table>
                        <thead>
                            <tr>
                                <th>Data</th>
                                <th>Status</th>
                                <th>Fișier</th>
                                <th>Mesaj</th>
                                <th>Ora JSON</th>
                            </tr>
                        </thead>
                        <tbody>${renderHistory(history)}</tbody>
                    </table>
                </div>
            </section>
        `;

        live.classList.remove('offline');
        live.innerHTML = '<span class="live-dot"></span>Live';

    } catch (error) {
        live.classList.add('offline');
        live.innerHTML = '<span class="live-dot"></span>Disconnected';
        console.error(error);

        document.getElementById('storeContent').innerHTML = `
            <div class="loading-card">
                Nu s-au putut încărca datele pentru magazinul ${STORE_CODE}.
            </div>
        `;
    }
}

loadStore();
setInterval(loadStore, 30000);