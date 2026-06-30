from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
import psycopg2
import datetime as dt

API_KEY = "test123"
OFFLINE_AFTER_MINUTES = 5
OK_VALID_HOURS = 12

DB_CONFIG = {
    "host": "127.0.0.1",
    "port": 5432,
    "dbname": "eod_monitor",
    "user": "postgres",
    "password": "1407"
}

app = FastAPI()


class StatusPayload(BaseModel):
    store_code: str
    status: str
    eod_file: str = ""
    message: str = ""
    eod_date: str = None
    schedule_time: str = None

    hostname: str = None
    agent_version: str = None
    os_info: str = None
    uptime_seconds: int = None
    cpu_load_1m: float = None
    ram_total_mb: int = None
    ram_used_mb: int = None
    ram_percent: float = None
    disk_total_gb: float = None
    disk_used_gb: float = None
    disk_percent: float = None


def get_conn():
    return psycopg2.connect(**DB_CONFIG)


def rows_to_dicts(cols, rows):
    result = []

    for row in rows:

        item = {}

        for key, value in zip(cols, row):

            if isinstance(value, (dt.datetime, dt.date)):
                item[key] = value.isoformat()
            else:
                item[key] = value

        result.append(item)

    return result


@app.get("/")
def root():

    return {
        "service": "EOD Monitor API",
        "status": "running"
    }


@app.post("/api/status")
def receive_status(
    payload: StatusPayload,
    x_api_key: str = Header(default=None)
):

    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")

    now = dt.datetime.now()

    ok_valid_until = None

    if payload.status == "OK" and payload.eod_file:
        ok_valid_until = now + dt.timedelta(hours=OK_VALID_HOURS)

    with get_conn() as conn:

        with conn.cursor() as cur:

            cur.execute(
                "SELECT store_code FROM stores WHERE store_code = %s",
                (payload.store_code,)
            )

            if cur.fetchone() is None:
                raise HTTPException(
                    status_code=404,
                    detail="Store not found in database"
                )

            if payload.schedule_time:

                cur.execute("""
                    UPDATE stores
                    SET schedule_time = %s,
                        updated_at = %s
                    WHERE store_code = %s
                """, (
                    payload.schedule_time,
                    now,
                    payload.store_code
                ))

            cur.execute("""
                INSERT INTO current_status (
                    store_code,
                    status,
                    eod_file,
                    message,
                    eod_date,
                    last_heartbeat,
                    updated_at,

                    hostname,
                    agent_version,
                    os_info,
                    uptime_seconds,

                    cpu_load_1m,

                    ram_total_mb,
                    ram_used_mb,
                    ram_percent,

                    disk_total_gb,
                    disk_used_gb,
                    disk_percent,

                    ok_valid_until,
                    last_ok_eod_file,
                    last_ok_eod_date,
                    last_ok_message

                )
                VALUES (
                    %s,%s,%s,%s,
                    %s,%s,%s,

                    %s,%s,%s,%s,

                    %s,

                    %s,%s,%s,

                    %s,%s,%s,

                    %s,%s,%s,%s
                )

                ON CONFLICT (store_code)

                DO UPDATE SET

                    status = EXCLUDED.status,
                    eod_file = EXCLUDED.eod_file,
                    message = EXCLUDED.message,
                    eod_date = EXCLUDED.eod_date,

                    last_heartbeat = EXCLUDED.last_heartbeat,
                    updated_at = EXCLUDED.updated_at,

                    hostname = EXCLUDED.hostname,
                    agent_version = EXCLUDED.agent_version,
                    os_info = EXCLUDED.os_info,
                    uptime_seconds = EXCLUDED.uptime_seconds,

                    cpu_load_1m = EXCLUDED.cpu_load_1m,

                    ram_total_mb = EXCLUDED.ram_total_mb,
                    ram_used_mb = EXCLUDED.ram_used_mb,
                    ram_percent = EXCLUDED.ram_percent,

                    disk_total_gb = EXCLUDED.disk_total_gb,
                    disk_used_gb = EXCLUDED.disk_used_gb,
                    disk_percent = EXCLUDED.disk_percent,

                    ok_valid_until = CASE
                        WHEN EXCLUDED.status = 'OK'
                        THEN EXCLUDED.ok_valid_until
                        ELSE current_status.ok_valid_until
                    END,

                    last_ok_eod_file = CASE
                        WHEN EXCLUDED.status = 'OK'
                        THEN EXCLUDED.eod_file
                        ELSE current_status.last_ok_eod_file
                    END,

                    last_ok_eod_date = CASE
                        WHEN EXCLUDED.status = 'OK'
                        THEN EXCLUDED.eod_date
                        ELSE current_status.last_ok_eod_date
                    END,

                    last_ok_message = CASE
                        WHEN EXCLUDED.status = 'OK'
                        THEN EXCLUDED.message
                        ELSE current_status.last_ok_message
                    END

            """, (

                payload.store_code,
                payload.status,
                payload.eod_file,
                payload.message,

                payload.eod_date,
                now,
                now,

                payload.hostname,
                payload.agent_version,
                payload.os_info,
                payload.uptime_seconds,

                payload.cpu_load_1m,

                payload.ram_total_mb,
                payload.ram_used_mb,
                payload.ram_percent,

                payload.disk_total_gb,
                payload.disk_used_gb,
                payload.disk_percent,

                ok_valid_until,

                payload.eod_file if payload.status == "OK" else None,
                payload.eod_date if payload.status == "OK" else None,
                payload.message if payload.status == "OK" else None
            ))

    return {
        "ok": True,
        "store_code": payload.store_code,
        "saved_at": now.isoformat(),
        "ok_valid_until": ok_valid_until.isoformat() if ok_valid_until else None
    }


@app.get("/api/dashboard")
def get_dashboard():

    with get_conn() as conn:

        with conn.cursor() as cur:

            cur.execute("""
                SELECT

                    s.store_code,
                    s.store_name,
                    s.host,
                    s.schedule_time,

                    CASE

                        WHEN cs.last_heartbeat IS NULL
                            THEN 'NO_DATA'

                        WHEN cs.last_heartbeat < NOW() - (%s * INTERVAL '1 minute')
                            THEN 'OFFLINE'

                        WHEN cs.status = 'OK'
                            THEN 'OK'

                        WHEN cs.status IN ('MISSING', 'PROBLEM')
                             AND cs.ok_valid_until > NOW()
                            THEN 'OK'

                        ELSE cs.status

                    END AS status,

                    CASE
                        WHEN cs.status IN ('MISSING', 'PROBLEM')
                             AND cs.ok_valid_until > NOW()
                        THEN cs.last_ok_eod_file
                        ELSE cs.eod_file
                    END AS eod_file,

                    CASE
                        WHEN cs.status IN ('MISSING', 'PROBLEM')
                             AND cs.ok_valid_until > NOW()
                        THEN 'OK validat anterior - valabil 12 ore'
                        ELSE cs.message
                    END AS message,

                    CASE
                        WHEN cs.status IN ('MISSING', 'PROBLEM')
                             AND cs.ok_valid_until > NOW()
                        THEN cs.last_ok_eod_date
                        ELSE cs.eod_date
                    END AS eod_date,

                    cs.last_heartbeat,
                    cs.updated_at,
                    cs.ok_valid_until,

                    EXTRACT(
                        EPOCH FROM (
                            NOW() - cs.last_heartbeat
                        )
                    )::INT AS seconds_since_heartbeat,

                    cs.hostname,
                    cs.agent_version,
                    cs.os_info,
                    cs.uptime_seconds,

                    cs.cpu_load_1m,

                    cs.ram_total_mb,
                    cs.ram_used_mb,
                    cs.ram_percent,

                    cs.disk_total_gb,
                    cs.disk_used_gb,
                    cs.disk_percent

                FROM stores s

                LEFT JOIN current_status cs
                    ON s.store_code = cs.store_code

                WHERE s.active = true

                ORDER BY s.store_code

            """, (
                OFFLINE_AFTER_MINUTES,
            ))

            cols = [desc[0] for desc in cur.description]

            rows = cur.fetchall()

    return rows_to_dicts(cols, rows)


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard_page():

    return """
<!doctype html>

<html>

<head>

<meta charset="utf-8">

<title>EOD Dashboard</title>

<style>

body {
    margin:0;
    font-family:Segoe UI,Arial,sans-serif;
    background:#f3f4f6;
    color:#111827;
}

.header {
    background:#111827;
    color:white;
    padding:22px 28px;
}

.container {
    padding:24px;
}

.toolbar {
    display:flex;
    gap:10px;
    margin-bottom:20px;
    flex-wrap:wrap;
}

button {
    border:0;
    border-radius:999px;
    padding:10px 16px;
    cursor:pointer;
    background:white;
    font-weight:700;
    box-shadow:0 3px 10px rgba(0,0,0,.05);
}

button.active {
    background:#2563eb;
    color:white;
}

.grid {
    display:grid;
    grid-template-columns:repeat(auto-fill,minmax(390px,1fr));
    gap:16px;
}

.card {
    background:white;
    border-radius:18px;
    padding:18px;
    box-shadow:0 4px 14px rgba(0,0,0,.06);
    border-left:8px solid #9ca3af;
}

.card.OK { border-left-color:#16a34a; }
.card.PROBLEM { border-left-color:#dc2626; }
.card.MISSING { border-left-color:#f97316; }
.card.OFFLINE { border-left-color:#6b7280; }
.card.NO_DATA { border-left-color:#9ca3af; }

.top {
    display:flex;
    justify-content:space-between;
}

.store {
    font-size:18px;
    font-weight:800;
}

.host {
    color:#6b7280;
    font-size:13px;
    margin-top:4px;
}

.badge {
    border-radius:999px;
    padding:6px 12px;
    font-size:12px;
    font-weight:800;
}

.badge.OK {
    background:#dcfce7;
    color:#166534;
}

.badge.PROBLEM,
.badge.MISSING {
    background:#fee2e2;
    color:#991b1b;
}

.badge.OFFLINE,
.badge.NO_DATA {
    background:#e5e7eb;
    color:#374151;
}

.details {
    margin-top:14px;
    color:#374151;
    font-size:14px;
    line-height:1.5;
}

.metrics {
    margin-top:14px;
    display:grid;
    grid-template-columns:repeat(3,1fr);
    gap:8px;
}

.metric {
    background:#f9fafb;
    border-radius:12px;
    padding:10px;
    font-size:13px;
}

.metric strong {
    display:block;
    font-size:16px;
    margin-top:4px;
}

.small {
    color:#6b7280;
    font-size:12px;
    margin-top:12px;
}

</style>

</head>

<body>

<div class="header">
    <h1>EOD Dashboard</h1>
</div>

<div class="container">

    <div class="toolbar">

        <input
            id="searchBox"
            type="text"
            placeholder="Caută după cod, nume sau IP..."
            oninput="render()"
            style="
                padding:10px 14px;
                border:0;
                border-radius:999px;
                min-width:280px;
                box-shadow:0 3px 10px rgba(0,0,0,.05);
                font-weight:600;
            "
        >

        <button onclick="setFilter('ALL')" id="btnALL" class="active">
            Toate
        </button>

        <button onclick="setFilter('OK')" id="btnOK">
            OK
        </button>

        <button onclick="setFilter('BAD')" id="btnBAD">
            Probleme
        </button>

        <button onclick="setFilter('OFFLINE')" id="btnOFFLINE">
            Offline
        </button>

    </div>

    <div class="grid" id="cards"></div>

</div>

<script>

let allData = [];
let currentFilter = 'ALL';

function setFilter(filter) {

    currentFilter = filter;

    ['ALL','OK','BAD','OFFLINE'].forEach(x => {
        document.getElementById('btn'+x).classList.remove('active');
    });

    document.getElementById('btn'+filter).classList.add('active');

    render();
}

function uptimeText(sec) {

    if (!sec)
        return '-';

    let days = Math.floor(sec / 86400);

    let hours = Math.floor((sec % 86400) / 3600);

    return days + 'z ' + hours + 'h';
}

function pct(x) {

    if (x === null || x === undefined)
        return '-';

    return Number(x).toFixed(1) + '%';
}

function val(x, suffix='') {

    if (x === null || x === undefined)
        return '-';

    return x + suffix;
}

function render() {

    const cards = document.getElementById('cards');

    cards.innerHTML = '';

    let filtered = allData;

    const q = document.getElementById('searchBox').value.toLowerCase().trim();

    if (q) {
        filtered = filtered.filter(x =>
            String(x.store_code || '').toLowerCase().includes(q) ||
            String(x.store_name || '').toLowerCase().includes(q) ||
            String(x.host || '').toLowerCase().includes(q)
        );
    }

    if (currentFilter === 'OK')
        filtered = filtered.filter(x => x.status === 'OK');

    if (currentFilter === 'BAD')
        filtered = filtered.filter(
            x => ['PROBLEM','MISSING'].includes(x.status)
        );

    if (currentFilter === 'OFFLINE')
        filtered = filtered.filter(
            x => ['OFFLINE','NO_DATA'].includes(x.status)
        );

    filtered.forEach(x => {

        const div = document.createElement('div');

        div.className = 'card ' + x.status;

        div.innerHTML = `

            <div class="top">

                <div>

                    <div class="store">
                        ${x.store_code} — ${x.store_name || ''}
                    </div>

                    <div class="host">
                        ${x.host || ''}
                        • Schedule: ${x.schedule_time || '-'}
                    </div>

                </div>

                <div class="badge ${x.status}">
                    ${x.status}
                </div>

            </div>

            <div class="details">

                <strong>Fisier:</strong>
                ${x.eod_file || '-'}<br>

                <strong>Mesaj:</strong>
                ${x.message || '-'}<br>

                <strong>Data EOD:</strong>
                ${x.eod_date || '-'}<br>

                <strong>OK valid pana la:</strong>
                ${x.ok_valid_until || '-'}

            </div>

            <div class="metrics">

                <div class="metric">
                    CPU
                    <strong>${pct(x.cpu_load_1m)}</strong>
                </div>

                <div class="metric">
                    RAM
                    <strong>
                        ${val(x.ram_used_mb, ' MB')}
                        /
                        ${val(x.ram_total_mb, ' MB')}
                    </strong>
                    <div>${pct(x.ram_percent)}</div>
                </div>

                <div class="metric">
                    Disk
                    <strong>
                        ${val(x.disk_used_gb, ' GB')}
                        /
                        ${val(x.disk_total_gb, ' GB')}
                    </strong>
                    <div>${pct(x.disk_percent)}</div>
                </div>

                <div class="metric">
                    Uptime
                    <strong>${uptimeText(x.uptime_seconds)}</strong>
                </div>

                <div class="metric">
                    Agent
                    <strong>${x.agent_version || '-'}</strong>
                </div>

                <div class="metric">
                    Host
                    <strong>${x.hostname || '-'}</strong>
                </div>

            </div>

            <div class="small">

                OS: ${x.os_info || '-'}<br>

                Ultim heartbeat:
                ${x.last_heartbeat || '-'}

            </div>

        `;

        cards.appendChild(div);
    });
}

async function loadDashboard() {

    const res = await fetch('/api/dashboard');

    allData = await res.json();

    render();
}

loadDashboard();

setInterval(loadDashboard, 30000);

</script>

</body>

</html>
"""