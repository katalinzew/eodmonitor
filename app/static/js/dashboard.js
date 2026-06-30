let dashboardData = [];
let activeFilter = 'ALL';

function fmt(value) {
    return value === null || value === undefined || value === '' ? '-' : value;
}

function pct(value) {
    if (value === null || value === undefined || value === '') return '-';
    return Number(value).toFixed(1) + '%';
}

function timeOnly(value) {
    if (!value) return '-';
    const d = new Date(value);
    if (isNaN(d)) return value;

    return d.toLocaleTimeString('ro-RO', {
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit'
    });
}

function dateTime(value) {
    if (!value) return '-';
    const d = new Date(value);
    if (isNaN(d)) return value;
    return d.toLocaleString('ro-RO');
}

function statusRank(status) {
    const ranks = {
        'OFFLINE': 1,
        'NO_DATA': 2,
        'PROBLEM': 3,
        'MISSING': 4,
        'LATE': 5,
        'OK': 9
    };

    return ranks[status] || 6;
}

function bucket(status) {
    if (status === 'OK') return 'OK';
    if (status === 'OFFLINE' || status === 'NO_DATA') return 'OFFLINE';
    return 'PROBLEM';
}

function setFilter(filter) {
    activeFilter = filter;

    document.querySelectorAll('.filter-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.filter === filter);
    });

    renderDashboard();
}

function severityClass(value, warnAt, badAt) {
    if (value === null || value === undefined || value === '') return 'ok';

    const num = Number(value);

    if (num >= badAt) return 'bad';
    if (num >= warnAt) return 'warn';

    return 'ok';
}

function bar(value, warnAt, badAt) {
    const cls = severityClass(value, warnAt, badAt);
    const width = value === null || value === undefined || value === '' ? 0 : Math.min(Number(value), 100);

    return `
        <div class="mini-bar">
            <div class="mini-bar-fill ${cls}" style="width:${width}%"></div>
        </div>
    `;
}

function matchesSearch(item, query) {
    if (!query) return true;

    const text = [
        item.store_code,
        item.store_name,
        item.host,
        item.hostname,
        item.status
    ].join(' ').toLowerCase();

    return text.includes(query.toLowerCase());
}

function goToStore(storeCode) {
    window.location.href = `/store/${storeCode}`;
}

function renderDashboard() {
    const query = document.getElementById('searchInput').value.trim();

    let ok = 0;
    let problem = 0;
    let offline = 0;

    dashboardData.forEach(item => {
        const group = bucket(item.status || 'NO_DATA');

        if (group === 'OK') ok++;
        else if (group === 'OFFLINE') offline++;
        else problem++;
    });

    let data = [...dashboardData].sort((a, b) => {
        const diff = statusRank(a.status) - statusRank(b.status);
        if (diff !== 0) return diff;
        return String(a.store_code || '').localeCompare(String(b.store_code || ''));
    });

    data = data.filter(item => {
        const group = bucket(item.status || 'NO_DATA');
        if (activeFilter !== 'ALL' && group !== activeFilter) return false;
        return matchesSearch(item, query);
    });

    let html = '';

    data.forEach(item => {
        const status = item.status || 'NO_DATA';

        html += `
            <div class="store-card status-${status}" onclick="goToStore('${item.store_code}')">
                <div class="store-head">
                    <div>
                        <div class="node-code">${fmt(item.store_code)}</div>
                        <div class="node-name">${fmt(item.store_name)}</div>
                    </div>

                    <span class="status-pill ${status}">
                        <span></span>${status}
                    </span>
                </div>

                <div class="node-line">
                    <span class="node-icon">▣</span>
                    <span>${fmt(item.host)}</span>
                </div>

                <div class="resource-list">
                    <div class="resource-row">
                        <span>CPU</span>
                        ${bar(item.cpu_load_1m, 70, 90)}
                        <strong>${pct(item.cpu_load_1m)}</strong>
                    </div>

                    <div class="resource-row">
                        <span>RAM</span>
                        ${bar(item.ram_percent, 75, 90)}
                        <strong>${pct(item.ram_percent)}</strong>
                    </div>

                    <div class="resource-row">
                        <span>Disk</span>
                        ${bar(item.disk_percent, 80, 90)}
                        <strong>${pct(item.disk_percent)}</strong>
                    </div>
                </div>

                <div class="card-footer">
                    <span>Heartbeat</span>
                    <strong>${timeOnly(item.last_heartbeat)}</strong>
                    <span class="details-link">Details →</span>
                </div>
            </div>
        `;
    });

    document.getElementById('totalStores').innerText = dashboardData.length;
    document.getElementById('okStores').innerText = ok;
    document.getElementById('problemStores').innerText = problem;
    document.getElementById('offlineStores').innerText = offline;

    document.getElementById('storeGrid').innerHTML = html || '<div class="loading-card">Nu există rezultate.</div>';
}

async function loadDashboard() {
    const live = document.getElementById('liveState');

    try {
        live.classList.remove('offline');
        live.innerHTML = '<span class="live-dot"></span>Refreshing';

        const response = await fetch('/api/dashboard');

        if (!response.ok) {
            throw new Error('HTTP ' + response.status);
        }

        dashboardData = await response.json();

        document.getElementById('lastUpdate').innerText = dateTime(new Date());

        live.classList.remove('offline');
        live.innerHTML = '<span class="live-dot"></span>Live';

        renderDashboard();

    } catch (error) {
        live.classList.add('offline');
        live.innerHTML = '<span class="live-dot"></span>Disconnected';
        console.error(error);
    }
}

loadDashboard();
setInterval(loadDashboard, 30000);