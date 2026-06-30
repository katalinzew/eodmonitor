from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel
import psycopg2
from psycopg2.extras import Json
import datetime as dt
from io import BytesIO
from typing import Optional
from openpyxl import Workbook
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

API_KEY = "test123"
OFFLINE_AFTER_MINUTES = 5
OK_VALID_HOURS = 12
LATE_GRACE_MINUTES = 30
ALERT_DELAY_MINUTES = 5
API_STARTED_AT = dt.datetime.now()

DB_CONFIG = {
    "host": "127.0.0.1",
    "port": 5432,
    "dbname": "eod_monitor",
    "user": "postgres",
    "password": "1407"
}

SMTP_CONFIG = {
    "host": "remote.smartid.ro",
    "port": 62625,
    "use_tls": True,
    "from": "eod-monitor@smartid.ro",
    "to": [
        "SupportSoftware@smartid.ro",
        "Valentin.SURUGIU@smartid.ro"
    ]
}
app = FastAPI()


class StatusPayload(BaseModel):
    store_code: str
    status: str
    eod_file: str = ""
    message: str = ""
    eod_date: str = None
    eod_file_created_at: Optional[str] = None
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
    services_status: dict = None


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



def alert_color(alert_type):
    colors = {
        "TEST": "#2563eb",
        "EOD_MISSING": "#dc2626",
        "EOD_PROBLEM": "#dc2626",
        "EOD_LATE": "#f59e0b",
        "AGENT_OFFLINE": "#dc2626",
        "SERVICE_DOWN": "#dc2626",
        "SERVICE_UP": "#16a34a",
        "AGENT_ONLINE": "#16a34a",
        "INFO": "#2563eb"
    }

    return colors.get(alert_type, "#111827")


def build_email_template(alert_type, title, subtitle, rows, dashboard_url=None):
    color = alert_color(alert_type)

    rows_html = ""

    for label, value in rows:
        rows_html += """
        <tr>
            <td style="padding:10px 12px;border-bottom:1px solid #e5e7eb;color:#64748b;font-weight:700;width:170px;">
                {label}
            </td>
            <td style="padding:10px 12px;border-bottom:1px solid #e5e7eb;color:#111827;font-weight:600;">
                {value}
            </td>
        </tr>
        """.format(
            label=label,
            value=value if value not in (None, "") else "-"
        )

    button_html = ""

    html = """
<!doctype html>
<html>
<head>
<meta charset="utf-8">
</head>

<body style="margin:0;padding:0;background:#f3f4f6;font-family:Segoe UI,Arial,sans-serif;color:#111827;">

    <div style="max-width:720px;margin:0 auto;padding:24px;">

        <div style="background:#111827;color:white;border-radius:16px 16px 0 0;padding:22px 24px;">
            <div style="font-size:22px;font-weight:900;letter-spacing:-0.4px;">
                EOD Monitor
            </div>
            <div style="font-size:13px;color:#cbd5e1;margin-top:4px;">
                Sistem monitorizare magazine
            </div>
        </div>

        <div style="background:white;border-radius:0 0 16px 16px;border:1px solid #e5e7eb;border-top:0;padding:24px;box-shadow:0 10px 28px rgba(15,23,42,.10);">

            <div style="display:flex;align-items:center;gap:12px;margin-bottom:18px;">
                <div style="width:14px;height:14px;border-radius:999px;background:{color};"></div>
                <div>
                    <div style="font-size:22px;font-weight:900;color:#111827;">
                        {title}
                    </div>
                    <div style="font-size:14px;color:#64748b;margin-top:3px;">
                        {subtitle}
                    </div>
                </div>
            </div>

            <table style="width:100%;border-collapse:collapse;border:1px solid #e5e7eb;border-radius:12px;overflow:hidden;">
                {rows_html}
            </table>


            <div style="margin-top:24px;padding-top:16px;border-top:1px solid #e5e7eb;color:#64748b;font-size:12px;line-height:1.5;">
                Acest email a fost generat automat de EOD Monitor.<br>
                Nu răspunde direct la acest mesaj.
            </div>

        </div>
    </div>

</body>
</html>
""".format(
        color=color,
        title=title,
        subtitle=subtitle,
        rows_html=rows_html,
        button_html=button_html
    )

    return html


def send_email_alert(subject, body_text, body_html=None):
    msg = MIMEMultipart("alternative")

    msg["From"] = SMTP_CONFIG["from"]
    msg["To"] = ", ".join(SMTP_CONFIG["to"])
    msg["Subject"] = subject

    msg.attach(
        MIMEText(
            body_text,
            "plain",
            "utf-8"
        )
    )

    if body_html:
        msg.attach(
            MIMEText(
                body_html,
                "html",
                "utf-8"
            )
        )

    smtp = smtplib.SMTP(
        SMTP_CONFIG["host"],
        SMTP_CONFIG["port"],
        timeout=10
    )

    try:
        if SMTP_CONFIG.get("use_tls"):
            smtp.starttls()

        smtp.sendmail(
            SMTP_CONFIG["from"],
            SMTP_CONFIG["to"],
            msg.as_string()
        )

    finally:
        try:
            smtp.quit()
        except Exception:
            pass



def insert_event(cur, store_code, event_type, old_value, new_value, message, created_at):
    cur.execute("""
        INSERT INTO event_log (
            store_code,
            event_type,
            old_value,
            new_value,
            message,
            created_at
        )
        VALUES (%s, %s, %s, %s, %s, %s)
    """, (
        store_code,
        event_type,
        old_value,
        new_value,
        message,
        created_at
    ))



def normalize_services(value):
    if not value:
        return {}

    if isinstance(value, dict):
        return value

    return {}


def log_service_events(cur, store_code, old_services, new_services, created_at):
    old_services = normalize_services(old_services)
    new_services = normalize_services(new_services)

    for service_name, new_status in new_services.items():
        old_status = old_services.get(service_name)

        if old_status == new_status:
            continue

        if old_status is None:
            event_type = "SERVICE_STATUS"
            if new_status == "active":
                message = "Serviciul {} este activ.".format(service_name)
            else:
                message = "Serviciul {} are status: {}.".format(service_name, new_status)

        elif old_status == "active" and new_status != "active":
            event_type = "SERVICE_DOWN"
            message = "Serviciul {} s-a oprit. Status vechi: {}, status nou: {}.".format(
                service_name,
                old_status,
                new_status
            )

        elif old_status != "active" and new_status == "active":
            event_type = "SERVICE_UP"
            message = "Serviciul {} a revenit activ. Status vechi: {}, status nou: {}.".format(
                service_name,
                old_status,
                new_status
            )

        else:
            event_type = "SERVICE_CHANGE"
            message = "Serviciul {} și-a schimbat statusul din {} în {}.".format(
                service_name,
                old_status,
                new_status
            )

        insert_event(
            cur,
            store_code,
            event_type,
            "{}: {}".format(service_name, old_status),
            "{}: {}".format(service_name, new_status),
            message,
            created_at
        )


def save_eod_history(cur, payload, received_at):
    # EOD history se salveaza doar cand agentul a gasit un fisier JSON real.
    # Daca statusul este MISSING si eod_file este gol, nu bagam rand fals in istoric.
    if not payload.eod_date or not payload.eod_file:
        return

    # Salvam EOD-ul doar pe baza fisierului JSON gasit de agent.
    # eod_file_created_at vine din timestamp-ul numelui fisierului:
    # eodstatusYYYYMMDDHHMMSS.json
    cur.execute("""
        INSERT INTO eod_history (
            store_code,
            eod_date,
            status,
            eod_file,
            message,
            eod_file_created_at,
            received_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (store_code, eod_date, COALESCE(eod_file, ''))
        DO UPDATE SET
            status = EXCLUDED.status,
            message = EXCLUDED.message,
            eod_file_created_at = EXCLUDED.eod_file_created_at,
            received_at = EXCLUDED.received_at
    """, (
        payload.store_code,
        payload.eod_date,
        payload.status,
        payload.eod_file,
        payload.message,
        payload.eod_file_created_at,
        received_at
    ))

def check_offline_events():
    now = dt.datetime.now()

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    cs.store_code,
                    COALESCE(cs.heartbeat_state, 'ONLINE') AS heartbeat_state
                FROM current_status cs
                JOIN stores s
                    ON s.store_code = cs.store_code
                WHERE s.active = true
                  AND cs.last_heartbeat IS NOT NULL
                  AND cs.last_heartbeat < NOW() - (%s * INTERVAL '1 minute')
                  AND COALESCE(cs.heartbeat_state, 'ONLINE') <> 'OFFLINE'
            """, (
                OFFLINE_AFTER_MINUTES,
            ))

            rows = cur.fetchall()

            for store_code, heartbeat_state in rows:
                insert_event(
                    cur,
                    store_code,
                    "HEARTBEAT_OFFLINE",
                    heartbeat_state,
                    "OFFLINE",
                    "Agentul nu a mai trimis heartbeat de peste {} minute.".format(OFFLINE_AFTER_MINUTES),
                    now
                )

                cur.execute("""
                    UPDATE current_status
                    SET heartbeat_state = 'OFFLINE',
                        updated_at = %s
                    WHERE store_code = %s
                """, (
                    now,
                    store_code
                ))


def parse_schedule_time(value):
    try:
        if not value:
            return None

        parts = str(value).split(":")
        if len(parts) < 2:
            return None

        hour = int(parts[0])
        minute = int(parts[1])

        if hour < 0 or hour > 23 or minute < 0 or minute > 59:
            return None

        return dt.time(hour, minute)

    except Exception:
        return None


def is_effective_ok(status, ok_valid_until, now):
    if status == "OK":
        return True

    if status in ("MISSING", "PROBLEM") and ok_valid_until and ok_valid_until > now:
        return True

    return False


def reset_alert(cur, store_code, alert_type, target, now):
    cur.execute("""
        UPDATE alert_state
        SET resolved = TRUE,
            resolved_at = %s,
            last_seen_at = %s
        WHERE store_code = %s
          AND alert_type = %s
          AND target = %s
          AND resolved = FALSE
    """, (
        now,
        now,
        store_code,
        alert_type,
        target
    ))


def register_alert_problem(cur, store_code, alert_type, target, now):
    cur.execute("""
        INSERT INTO alert_state (
            store_code,
            alert_type,
            target,
            first_seen_at,
            last_seen_at,
            email_sent,
            resolved
        )
        VALUES (%s, %s, %s, %s, %s, FALSE, FALSE)
        ON CONFLICT (store_code, alert_type, target)
        DO UPDATE SET
            last_seen_at = EXCLUDED.last_seen_at,
            resolved = FALSE,
            resolved_at = NULL,
            first_seen_at = CASE
                WHEN alert_state.resolved = TRUE
                THEN EXCLUDED.first_seen_at
                ELSE alert_state.first_seen_at
            END,
            email_sent = CASE
                WHEN alert_state.resolved = TRUE
                THEN FALSE
                ELSE alert_state.email_sent
            END,
            email_sent_at = CASE
                WHEN alert_state.resolved = TRUE
                THEN NULL
                ELSE alert_state.email_sent_at
            END
        RETURNING id, first_seen_at, email_sent
    """, (
        store_code,
        alert_type,
        target,
        now,
        now
    ))

    return cur.fetchone()


def mark_alert_email_sent(cur, alert_id, now):
    cur.execute("""
        UPDATE alert_state
        SET email_sent = TRUE,
            email_sent_at = %s
        WHERE id = %s
    """, (
        now,
        alert_id
    ))


def send_alert_email_for_state(cur, store_code, store_name, alert_type, target, first_seen_at, details):
    dashboard_url = "http://10.143.252.2:8000/store/{}".format(store_code)

    if alert_type == "EOD_MISSING":
        title = "EOD lipsă"
        subtitle = "Nu există EOD OK după ora programată + 5 minute."
    elif alert_type == "AGENT_OFFLINE":
        title = "Agent offline"
        subtitle = "Nu s-a primit heartbeat de peste 5 minute."
    elif alert_type == "SERVICE_DOWN":
        title = "Serviciu oprit"
        subtitle = "Serviciul este diferit de active de cel puțin 5 minute."
    else:
        title = alert_type
        subtitle = "Alertă EOD Monitor"

    detail_rows = []
    detail_rows.append(("Prima detectare", first_seen_at.strftime("%d.%m.%Y %H:%M:%S")))

    if target:
        detail_rows.append(("Target", target))

    for label, value in details:
        detail_rows.append((label, value))

    send_monitor_alert(
        alert_type=alert_type,
        title=title,
        subtitle=subtitle,
        store_code=store_code,
        store_name=store_name,
        details=detail_rows,
        dashboard_url=dashboard_url
    )


def maybe_send_alert(cur, store_code, store_name, alert_type, target, now, delay_minutes, details):
    alert_id, first_seen_at, email_sent = register_alert_problem(
        cur,
        store_code,
        alert_type,
        target,
        now
    )

    if email_sent:
        return

    send_after = first_seen_at + dt.timedelta(minutes=delay_minutes)

    if now < send_after:
        return

    try:
        send_alert_email_for_state(
            cur,
            store_code,
            store_name,
            alert_type,
            target,
            first_seen_at,
            details
        )

        mark_alert_email_sent(cur, alert_id, now)

    except Exception as e:
        print("ALERT EMAIL ERROR:", str(e))


def check_alert_states():
    now = dt.datetime.now()

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    s.store_code,
                    s.store_name,
                    s.schedule_time,
                    cs.status,
                    cs.ok_valid_until,
                    cs.last_heartbeat,
                    cs.services_status,
                    cs.message
                FROM stores s
                LEFT JOIN current_status cs
                    ON s.store_code = cs.store_code
                WHERE s.active = TRUE
            """)

            rows = cur.fetchall()

            for row in rows:
                store_code = row[0]
                store_name = row[1]
                schedule_time = row[2]
                status = row[3]
                ok_valid_until = row[4]
                last_heartbeat = row[5]
                services_status = row[6] or {}
                message = row[7]

                # 1. EOD lipsă după schedule_time + 5 minute.
                schedule = parse_schedule_time(schedule_time)

                if schedule:
                    schedule_dt = dt.datetime.combine(now.date(), schedule)
                    alert_dt = schedule_dt + dt.timedelta(minutes=ALERT_DELAY_MINUTES)

                    if now >= alert_dt and not is_effective_ok(status, ok_valid_until, now):
                        maybe_send_alert(
                            cur,
                            store_code,
                            store_name,
                            "EOD_MISSING",
                            "EOD",
                            now,
                            0,
                            [
                                ("Program EOD", schedule_time),
                                ("Status curent", status or "NO_DATA"),
                                ("Mesaj", message or "-")
                            ]
                        )
                    else:
                        reset_alert(cur, store_code, "EOD_MISSING", "EOD", now)

                # 2. Agent offline: heartbeat lipsă peste 5 minute.
                if last_heartbeat and last_heartbeat >= API_STARTED_AT:
                    if last_heartbeat < now - dt.timedelta(minutes=OFFLINE_AFTER_MINUTES):
                        maybe_send_alert(
                            cur,
                            store_code,
                            store_name,
                            "AGENT_OFFLINE",
                            "HEARTBEAT",
                            now,
                            0,
                            [
                                ("Ultim heartbeat", last_heartbeat.strftime("%d.%m.%Y %H:%M:%S")),
                                ("Limită", "{} minute".format(OFFLINE_AFTER_MINUTES))
                            ]
                        )
                    else:
                        reset_alert(cur, store_code, "AGENT_OFFLINE", "HEARTBEAT", now)

                # 3. Serviciu down: doar dacă agentul este recent online.
                agent_recent = last_heartbeat and last_heartbeat >= now - dt.timedelta(minutes=OFFLINE_AFTER_MINUTES)

                if isinstance(services_status, dict) and agent_recent:
                    active_service_targets = set()

                    for service_name, service_status in services_status.items():
                        if service_status != "active":
                            active_service_targets.add(service_name)

                            maybe_send_alert(
                                cur,
                                store_code,
                                store_name,
                                "SERVICE_DOWN",
                                service_name,
                                now,
                                ALERT_DELAY_MINUTES,
                                [
                                    ("Serviciu", service_name),
                                    ("Status serviciu", service_status),
                                    ("Limită", "{} minute".format(ALERT_DELAY_MINUTES))
                                ]
                            )

                    cur.execute("""
                        SELECT target
                        FROM alert_state
                        WHERE store_code = %s
                          AND alert_type = 'SERVICE_DOWN'
                          AND resolved = FALSE
                    """, (
                        store_code,
                    ))

                    existing_targets = [r[0] for r in cur.fetchall()]

                    for target in existing_targets:
                        if target not in active_service_targets:
                            reset_alert(cur, store_code, "SERVICE_DOWN", target, now)



@app.get("/")
def root():
    return {
        "service": "EOD Monitor API",
        "status": "running"
    }


@app.post("/api/status")
def receive_status(payload: StatusPayload, x_api_key: str = Header(default=None)):
    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")

    now = dt.datetime.now()
    ok_valid_until = None

    # IMPORTANT:
    # OK valid trebuie calculat din ora fisierului JSON EOD,
    # nu din ora la care API-ul primeste heartbeat-ul.
    #
    # Exemplu:
    # eodstatus20260602230006.json
    # eod_file_created_at = 2026-06-02 23:00:06
    # ok_valid_until = 2026-06-03 11:00:06
    if payload.status == "OK" and payload.eod_file and payload.eod_file_created_at:
        try:
            eod_file_dt = dt.datetime.strptime(
                payload.eod_file_created_at,
                "%Y-%m-%d %H:%M:%S"
            )
            ok_valid_until = eod_file_dt + dt.timedelta(hours=OK_VALID_HOURS)
        except Exception:
            ok_valid_until = now + dt.timedelta(hours=OK_VALID_HOURS)

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT store_code FROM stores WHERE store_code = %s",
                (payload.store_code,)
            )

            if cur.fetchone() is None:
                raise HTTPException(status_code=404, detail="Store not found in database")

            cur.execute("""
                SELECT
                    status,
                    COALESCE(heartbeat_state, 'ONLINE') AS heartbeat_state,
                    services_status
                FROM current_status
                WHERE store_code = %s
            """, (
                payload.store_code,
            ))

            old_row = cur.fetchone()
            old_status = None
            old_heartbeat_state = "ONLINE"
            old_services_status = {}

            if old_row:
                old_status = old_row[0]
                old_heartbeat_state = old_row[1]
                old_services_status = old_row[2] or {}

            if old_heartbeat_state == "OFFLINE":
                insert_event(
                    cur,
                    payload.store_code,
                    "HEARTBEAT_ONLINE",
                    "OFFLINE",
                    "ONLINE",
                    "Agentul a revenit online.",
                    now
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
                    eod_file_created_at,
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
                    last_ok_message,
                    heartbeat_state,
                    services_status
                )
                VALUES (
                    %s,%s,%s,%s,%s,%s,
                    %s,%s,
                    %s,%s,%s,%s,
                    %s,
                    %s,%s,%s,
                    %s,%s,%s,
                    %s,
                    %s,%s,%s,
                    %s,
                    %s
                )
                ON CONFLICT (store_code)
                DO UPDATE SET
                    status = EXCLUDED.status,
                    eod_file = EXCLUDED.eod_file,
                    message = EXCLUDED.message,
                    eod_date = EXCLUDED.eod_date,
                    eod_file_created_at = EXCLUDED.eod_file_created_at,
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

                    heartbeat_state = 'ONLINE',
                    services_status = EXCLUDED.services_status,

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
                payload.eod_file_created_at,

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
                payload.message if payload.status == "OK" else None,

                "ONLINE",
                Json(payload.services_status or {})
            ))

            save_eod_history(cur, payload, now)

            if old_status != payload.status:
                insert_event(
                    cur,
                    payload.store_code,
                    "STATUS_CHANGE",
                    old_status,
                    payload.status,
                    "Status EOD schimbat: {} -> {}".format(old_status, payload.status),
                    now
                )

            log_service_events(
                cur,
                payload.store_code,
                old_services_status,
                payload.services_status or {},
                now
            )

    check_alert_states()

    return {
        "ok": True,
        "store_code": payload.store_code,
        "saved_at": now.isoformat(),
        "ok_valid_until": ok_valid_until.isoformat() if ok_valid_until else None
    }


DASHBOARD_SQL = """
    SELECT
        s.store_code,
        s.store_name,
        s.host,
        s.schedule_time,

        CASE
            WHEN cs.last_heartbeat IS NULL THEN 'NO_DATA'

            WHEN cs.last_heartbeat < NOW() - (%s * INTERVAL '1 minute') THEN 'OFFLINE'

            WHEN cs.status = 'OK' THEN 'OK'

            WHEN cs.status IN ('MISSING', 'PROBLEM')
                 AND cs.ok_valid_until > NOW()
            THEN 'OK'

            WHEN s.schedule_time ~ '^[0-2][0-9]:[0-5][0-9]$'
                 AND NOW() > (CURRENT_DATE + s.schedule_time::time + (%s * INTERVAL '1 minute'))
                 AND NOT (cs.ok_valid_until > NOW())
                 AND COALESCE(cs.status, 'MISSING') <> 'OK'
            THEN 'LATE'

            ELSE COALESCE(cs.status, 'NO_DATA')
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
        cs.eod_file_created_at,
        COALESCE(cs.heartbeat_state, 'ONLINE') AS heartbeat_state,
        cs.services_status,

        EXTRACT(EPOCH FROM (NOW() - cs.last_heartbeat))::INT AS seconds_since_heartbeat,

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
        cs.disk_percent,

        eh.last_eod_status,
        eh.last_eod_file,
        eh.last_eod_message,
        eh.last_eod_date,
        eh.last_eod_at

    FROM stores s
    LEFT JOIN current_status cs
        ON s.store_code = cs.store_code

    LEFT JOIN LATERAL (
        SELECT
            h.status AS last_eod_status,
            h.eod_file AS last_eod_file,
            h.message AS last_eod_message,
            h.eod_date AS last_eod_date,
            h.eod_file_created_at AS last_eod_file_created_at,
            h.received_at AS last_eod_at
        FROM eod_history h
        WHERE h.store_code = s.store_code
        ORDER BY h.received_at DESC
        LIMIT 1
    ) eh ON true

    WHERE s.active = true
"""


@app.get("/api/dashboard")
def get_dashboard():
    check_offline_events()
    check_alert_states()

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(DASHBOARD_SQL + " ORDER BY s.store_code", (
                OFFLINE_AFTER_MINUTES,
                LATE_GRACE_MINUTES
            ))

            cols = [desc[0] for desc in cur.description]
            rows = cur.fetchall()

    return rows_to_dicts(cols, rows)


@app.get("/api/events")
def get_events(limit: int = 100):
    check_offline_events()
    check_alert_states()

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    e.id,
                    e.store_code,
                    s.store_name,
                    e.event_type,
                    e.old_value,
                    e.new_value,
                    e.message,
                    e.created_at
                FROM event_log e
                LEFT JOIN stores s
                    ON e.store_code = s.store_code
                ORDER BY e.id DESC
                LIMIT %s
            """, (limit,))

            cols = [desc[0] for desc in cur.description]
            rows = cur.fetchall()

    return rows_to_dicts(cols, rows)


@app.get("/api/reports/daily")
def daily_report():
    check_offline_events()
    check_alert_states()

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                WITH dashboard AS (
            """ + DASHBOARD_SQL + """
                )
                SELECT
                    COUNT(*) AS total_stores,
                    COUNT(*) FILTER (WHERE status = 'OK') AS ok_count,
                    COUNT(*) FILTER (WHERE status = 'LATE') AS late_count,
                    COUNT(*) FILTER (WHERE status = 'MISSING') AS missing_count,
                    COUNT(*) FILTER (WHERE status = 'PROBLEM') AS problem_count,
                    COUNT(*) FILTER (WHERE status = 'OFFLINE') AS offline_count,
                    COUNT(*) FILTER (WHERE status = 'NO_DATA') AS no_data_count
                FROM dashboard
            """, (
                OFFLINE_AFTER_MINUTES,
                LATE_GRACE_MINUTES
            ))

            cols = [desc[0] for desc in cur.description]
            row = cur.fetchone()

    return dict(zip(cols, row))



@app.get("/api/store/{store_code}")
def get_store_details(store_code: str):
    check_offline_events()
    check_alert_states()

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                WITH dashboard AS (
            """ + DASHBOARD_SQL + """
                )
                SELECT *
                FROM dashboard
                WHERE store_code = %s
                LIMIT 1
            """, (
                OFFLINE_AFTER_MINUTES,
                LATE_GRACE_MINUTES,
                store_code
            ))

            cols = [desc[0] for desc in cur.description]
            row = cur.fetchone()

            if row is None:
                raise HTTPException(status_code=404, detail="Store not found")

            store = rows_to_dicts(cols, [row])[0]

            cur.execute("""
                SELECT
                    e.id,
                    e.store_code,
                    s.store_name,
                    e.event_type,
                    e.old_value,
                    e.new_value,
                    e.message,
                    e.created_at
                FROM event_log e
                LEFT JOIN stores s
                    ON e.store_code = s.store_code
                WHERE e.store_code = %s
                ORDER BY e.id DESC
                LIMIT 100
            """, (store_code,))

            event_cols = [desc[0] for desc in cur.description]
            event_rows = cur.fetchall()
            events = rows_to_dicts(event_cols, event_rows)

            cur.execute("""
                SELECT
                    id,
                    store_code,
                    eod_date,
                    status,
                    eod_file,
                    message,
                    eod_file_created_at,
                    received_at
                FROM eod_history
                WHERE store_code = %s
                ORDER BY received_at DESC
                LIMIT 30
            """, (store_code,))

            eod_cols = [desc[0] for desc in cur.description]
            eod_rows = cur.fetchall()
            eod_history = rows_to_dicts(eod_cols, eod_rows)

    return {
        "store": store,
        "events": events,
        "eod_history": eod_history
    }


@app.get("/store/{store_code}", response_class=HTMLResponse)
def store_page(store_code: str):
    return """
<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Store Details</title>
""" + COMMON_CSS + """
<style>
.details-layout {
    display:grid;
    grid-template-columns: 1fr 1fr;
    gap:16px;
}

.panel {
    background:white;
    border:1px solid #e5e7eb;
    border-radius:13px;
    padding:16px;
    box-shadow:0 6px 18px rgba(15,23,42,.07);
}

.panel h2 {
    margin:0 0 14px;
    font-size:18px;
}

.service-row {
    display:flex;
    justify-content:space-between;
    align-items:center;
    padding:10px 0;
    border-bottom:1px solid #e5e7eb;
}

.service-row:last-child {
    border-bottom:0;
}

.service-name {
    font-weight:800;
}

.service-status {
    border-radius:999px;
    padding:5px 12px;
    font-size:12px;
    font-weight:900;
}

.service-status.active {
    background:#dcfce7;
    color:#15803d;
}

.service-status.bad {
    background:#fee2e2;
    color:#b91c1c;
}


.scroll-box {
    max-height: 320px;
    overflow-y: auto;
    overflow-x: auto;
    border-radius: 10px;
}

.scroll-box::-webkit-scrollbar {
    width: 10px;
    height: 10px;
}

.scroll-box::-webkit-scrollbar-thumb {
    background: #cbd5e1;
    border-radius: 10px;
}

.scroll-box::-webkit-scrollbar-track {
    background: #f1f5f9;
}

@media (max-width: 900px) {
    .details-layout {
        grid-template-columns: 1fr;
    }
}

.event-toolbar {
    background:white;
    border:1px solid #e5e7eb;
    border-radius:12px;
    padding:12px 16px;
    margin-bottom:16px;
    box-shadow:0 6px 18px rgba(15,23,42,.06);
    display:flex;
    gap:10px;
    flex-wrap:wrap;
    align-items:center;
}

.event-pill {
    border:1px solid #cbd5e1;
    border-radius:999px;
    padding:8px 14px;
    font-weight:800;
    background:white;
    cursor:pointer;
}

.event-pill.active {
    background:#2563eb;
    color:white;
    border-color:#2563eb;
}

.status-dot {
    display:inline-block;
    width:10px;
    height:10px;
    border-radius:999px;
    margin-right:6px;
}

.status-dot.ok { background:#22c55e; }
.status-dot.warn { background:#f59e0b; }
.status-dot.bad { background:#ef4444; }
.status-dot.gray { background:#64748b; }

.health-ok { color:#15803d; font-weight:900; }
.health-warn { color:#b45309; font-weight:900; }
.health-bad { color:#b91c1c; font-weight:900; }


.alert-card {
    background:white;
    border:1px solid #e5e7eb;
    border-radius:13px;
    padding:16px;
    box-shadow:0 6px 18px rgba(15,23,42,.07);
    border-left:5px solid #dc2626;
    margin-bottom:14px;
}

.alert-title {
    font-size:17px;
    font-weight:900;
    color:#111827;
}

.alert-meta {
    color:#475569;
    font-size:13px;
    margin-top:5px;
    line-height:1.5;
}

.analytics-grid {
    display:grid;
    grid-template-columns:1fr 1fr;
    gap:16px;
}

.analytics-panel {
    background:white;
    border:1px solid #e5e7eb;
    border-radius:13px;
    padding:16px;
    box-shadow:0 6px 18px rgba(15,23,42,.07);
}

.analytics-panel h2 {
    margin:0 0 14px;
    font-size:18px;
}

@media (max-width: 900px) {
    .analytics-grid {
        grid-template-columns:1fr;
    }
}


.service-badge {
    border-radius:999px;
    padding:5px 12px;
    font-size:12px;
    font-weight:900;
    display:inline-block;
}

.service-badge.active {
    background:#dcfce7;
    color:#15803d;
}

.service-badge.failed,
.service-badge.inactive,
.service-badge.timeout,
.service-badge.unknown,
.service-badge.bad {
    background:#fee2e2;
    color:#b91c1c;
}

.export-bar {
    background:white;
    border:1px solid #e5e7eb;
    border-radius:12px;
    padding:12px 16px;
    margin-bottom:16px;
    box-shadow:0 6px 18px rgba(15,23,42,.06);
    display:flex;
    gap:10px;
    flex-wrap:wrap;
    align-items:center;
}

.export-link {
    text-decoration:none;
    background:#111827;
    color:white;
    padding:10px 15px;
    border-radius:8px;
    font-weight:800;
    font-size:14px;
}

.service-row {
    cursor:pointer;
}

.service-row:hover {
    background:#f8fafc;
}


.form-panel {
    background:white;
    border:1px solid #e5e7eb;
    border-radius:13px;
    padding:16px;
    margin-bottom:16px;
    box-shadow:0 6px 18px rgba(15,23,42,.07);
}

.form-grid {
    display:grid;
    grid-template-columns:repeat(auto-fit,minmax(180px,1fr));
    gap:12px;
    align-items:end;
}

.form-field label {
    display:block;
    font-size:13px;
    font-weight:800;
    color:#334155;
    margin-bottom:6px;
}

.form-field input,
.form-field select {
    width:100%;
    height:38px;
    border:1px solid #cbd5e1;
    border-radius:8px;
    padding:0 10px;
    font-size:14px;
    outline:none;
}

.form-field input:focus,
.form-field select:focus {
    border-color:#2563eb;
    box-shadow:0 0 0 3px rgba(37,99,235,.12);
}

.action-btn {
    border:0;
    border-radius:8px;
    padding:9px 14px;
    cursor:pointer;
    font-weight:900;
    font-size:13px;
    margin-right:6px;
}

.action-edit {
    background:#dbeafe;
    color:#1d4ed8;
}

.action-delete {
    background:#fee2e2;
    color:#b91c1c;
}

.action-activate {
    background:#dcfce7;
    color:#15803d;
}

.action-save {
    background:#111827;
    color:white;
}

.action-clear {
    background:#e5e7eb;
    color:#334155;
}

.store-inactive {
    opacity:.55;
}

</style>
</head>
<body>
""" + header_html("Store Details", "dashboard") + """

<div class="container">
    <div id="content"></div>
</div>

<script>
const STORE_CODE = "__STORE_CODE__";

function formatDateOnly(value) {
    if (!value) return '-';
    const d = new Date(value);
    if (isNaN(d)) return value;

    return d.toLocaleDateString('ro-RO', {
        day: '2-digit',
        month: '2-digit',
        year: 'numeric'
    });
}

function formatDateTime(value) {
    if (!value) return '-';
    const d = new Date(value);
    if (isNaN(d)) return value;

    return d.toLocaleString('ro-RO', {
        day: '2-digit',
        month: '2-digit',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit'
    });
}

function pct(x) {
    if (x === null || x === undefined) return '-';
    return Number(x).toFixed(1) + '%';
}

function val(x, suffix='') {
    if (x === null || x === undefined) return '-';
    return x + suffix;
}

function uptimeText(sec) {
    if (!sec) return '-';
    let days = Math.floor(sec / 86400);
    let hours = Math.floor((sec % 86400) / 3600);
    return days + 'z ' + hours + 'h';
}

function serviceClass(status) {
    if (status === 'active') return 'active';
    if (status === 'failed') return 'failed';
    if (status === 'inactive') return 'inactive';
    if (status === 'timeout') return 'timeout';
    if (status === 'unknown') return 'unknown';
    return 'bad';
}

function eventTypeLabel(value) {
    const labels = {
        "HEARTBEAT_OFFLINE": "Agent offline",
        "HEARTBEAT_ONLINE": "Agent online",
        "SERVICE_DOWN": "Serviciu oprit",
        "SERVICE_UP": "Serviciu activ",
        "SERVICE_CHANGE": "Serviciu schimbat",
        "SERVICE_STATUS": "Status serviciu",
        "STATUS_CHANGE": "Status EOD schimbat"
    };

    return labels[value] || value || '-';
}

async function loadServiceHistory(serviceName) {
    const res = await fetch('/api/store/' + STORE_CODE + '/service-history?service=' + encodeURIComponent(serviceName));
    const data = await res.json();

    const box = document.getElementById('serviceHistory');
    const title = document.getElementById('serviceHistoryTitle');

    title.innerText = 'Istoric serviciu: ' + serviceName;

    if (!data.length) {
        box.innerHTML = '<div class="small">Nu există istoric pentru acest serviciu.</div>';
        return;
    }

    let html = `
        <div class="scroll-box">
            <table>
                <thead>
                    <tr>
                        <th>ID</th>
                        <th>Tip</th>
                        <th>Old</th>
                        <th>New</th>
                        <th>Mesaj</th>
                        <th>Creat la</th>
                    </tr>
                </thead>
                <tbody>
    `;

    data.forEach(e => {
        html += `
            <tr>
                <td>${e.id}</td>
                <td>${eventTypeLabel(e.event_type)}</td>
                <td>${e.old_value || '-'}</td>
                <td>${e.new_value || '-'}</td>
                <td>${e.message || '-'}</td>
                <td>${formatDateTime(e.created_at)}</td>
            </tr>
        `;
    });

    html += '</tbody></table></div>';

    box.innerHTML = html;
}


function eventTypeLabel(value) {
    const labels = {
        "HEARTBEAT_OFFLINE": "Agent offline",
        "HEARTBEAT_ONLINE": "Agent online",
        "SERVICE_DOWN": "Serviciu oprit",
        "SERVICE_UP": "Serviciu activ",
        "SERVICE_CHANGE": "Serviciu schimbat",
        "SERVICE_STATUS": "Status serviciu",
        "STATUS_CHANGE": "Status EOD schimbat"
    };

    return labels[value] || value || '-';
}


function cleanMessage(value) {
    if (!value) return '-';

    const map = {
        "Nu exista fisier EOD": "Nu există fișier EOD.",
        "Nu exista niciun fisier EOD": "Nu există niciun fișier EOD.",
        "Nu exista fisier EOD pentru ziua curenta": "Nu există fișier EOD pentru ziua curentă."
    };

    return map[value] || value;
}

async function loadStore() {
    const res = await fetch('/api/store/' + STORE_CODE);
    const data = await res.json();

    const x = data.store;
    const services = x.services_status || {};
    const events = data.events || [];
    const eodHistory = data.eod_history || [];

    document.getElementById('lastUpdate').innerText = formatDateTime(new Date());

    let serviceHtml = '';
    Object.keys(services).sort().forEach(name => {
        const st = services[name] || 'unknown';
        serviceHtml += `
            <div class="service-row" onclick="loadServiceHistory('${name}')">
                <div class="service-name">${name}</div>
                <div class="service-badge ${serviceClass(st)}">${st}</div>
            </div>
        `;
    });

    if (!serviceHtml) {
        serviceHtml = '<div class="small">Nu există servicii raportate încă.</div>';
    }

    let eventsHtml = '';
    events.forEach(e => {
        eventsHtml += `
            <tr>
                <td>${e.id}</td>
                <td>${eventTypeLabel(e.event_type)}</td>
                <td>${e.old_value || '-'}</td>
                <td>${e.new_value || '-'}</td>
                <td>${e.message || ''}</td>
                <td>${formatDateTime(e.created_at)}</td>
            </tr>
        `;
    });

    let eodHtml = '';
    eodHistory.forEach(h => {
        eodHtml += `
            <tr>
                <td>${formatDateOnly(h.eod_date)}</td>
                <td>${h.status || '-'}</td>
                <td>${h.eod_file || '-'}</td>
                <td>${cleanMessage(h.message)}</td>
                <td>${formatDateTime(h.eod_file_created_at)}</td>
                <td>${formatDateTime(h.received_at)}</td>
            </tr>
        `;
    });

    document.getElementById('content').innerHTML = `
        <div class="card ${x.status}">
            <div class="card-top">
                <div>
                    <div class="store"><a href="/store/${x.store_code}" style="color:inherit;text-decoration:none;">${x.store_code} — ${x.store_name || ''}</a></div>
                    <div class="host">${x.host || ''} &nbsp;•&nbsp; Schedule: ${x.schedule_time || '-'}</div>
                </div>
                <div class="badge ${x.status}">${x.status}</div>
            </div>

            <div class="details">
                <strong>Fișier:</strong> ${x.eod_file || '-'}<br>
                <strong>Mesaj:</strong> ${cleanMessage(x.message)}<br>
                <strong>Data EOD:</strong> ${formatDateOnly(x.eod_date)}<br>
                <strong>Ultimul EOD:</strong> ${formatDateTime(x.eod_file_created_at || x.last_eod_file_created_at)}<br>
                <strong>OK valid până la:</strong> ${formatDateTime(x.ok_valid_until)}<br>
                <strong>Ultim heartbeat:</strong> ${formatDateTime(x.last_heartbeat)}
            </div>

            <div class="metrics">
                <div class="metric">CPU<strong>${pct(x.cpu_load_1m)}</strong></div>
                <div class="metric">RAM<strong>${val(x.ram_used_mb, ' MB')} / ${val(x.ram_total_mb, ' MB')}</strong><div class="sub">${pct(x.ram_percent)}</div></div>
                <div class="metric">Disk<strong>${val(x.disk_used_gb, ' GB')} / ${val(x.disk_total_gb, ' GB')}</strong><div class="sub">${pct(x.disk_percent)}</div></div>
                <div class="metric">Uptime<strong>${uptimeText(x.uptime_seconds)}</strong></div>
                <div class="metric">Agent<strong>${x.agent_version || '-'}</strong></div>
                <div class="metric">Host<strong>${x.hostname || '-'}</strong></div>
            </div>

            <div class="small">OS: ${x.os_info || '-'}</div>
        </div>

        <br>

        <div class="details-layout">
            <div class="panel">
                <h2>Servicii monitorizate</h2>
                ${serviceHtml}
            </div>

            <div class="panel">
                <h2>Ultimele evenimente</h2>
                <div class="scroll-box">
                    <table>
                        <thead>
                            <tr>
                                <th>ID</th>
                                <th>Tip</th>
                                <th>Old</th>
                                <th>New</th>
                                <th>Mesaj</th>
                                <th>Creat la</th>
                            </tr>
                        </thead>
                        <tbody>${eventsHtml}</tbody>
                    </table>
                </div>
            </div>
        </div>

        <br>

        <div class="panel">
            <h2 id="serviceHistoryTitle">Istoric serviciu</h2>
            <div id="serviceHistory" class="small">Apasă pe un serviciu ca să vezi istoricul lui.</div>
        </div>

        <br>

        <div class="panel">
            <h2>Istoric EOD</h2>
            <div class="scroll-box">
                <table>
                    <thead>
                        <tr>
                            <th>Data EOD</th>
                            <th>Status</th>
                            <th>Fișier</th>
                            <th>Mesaj</th>
                            <th>Ora din JSON</th>
                            <th>Primit la API</th>
                        </tr>
                    </thead>
                    <tbody>${eodHtml}</tbody>
                </table>
            </div>
        </div>
    `;
}

loadStore();
setInterval(loadStore, 30000);
</script>
</body>
</html>
""".replace("__STORE_CODE__", store_code)





@app.get("/api/health")
def health_report():
    check_offline_events()
    check_alert_states()

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(DASHBOARD_SQL + " ORDER BY s.store_code", (
                OFFLINE_AFTER_MINUTES,
                LATE_GRACE_MINUTES
            ))

            cols = [desc[0] for desc in cur.description]
            rows = cur.fetchall()

    data = rows_to_dicts(cols, rows)

    for item in data:
        services = item.get("services_status") or {}
        service_down = []

        if isinstance(services, dict):
            for name, status in services.items():
                if status != "active":
                    service_down.append(name)

        item["service_down_count"] = len(service_down)
        item["service_down_list"] = service_down

        issues = []

        if item.get("status") in ("OFFLINE", "NO_DATA"):
            issues.append("Agent offline")

        if item.get("disk_percent") is not None and item.get("disk_percent") >= 90:
            issues.append("Disk peste 90%")

        if item.get("ram_percent") is not None and item.get("ram_percent") >= 85:
            issues.append("RAM peste 85%")

        if item.get("cpu_load_1m") is not None and item.get("cpu_load_1m") >= 85:
            issues.append("CPU peste 85%")

        if service_down:
            issues.append("Servicii oprite: " + ", ".join(service_down))

        item["health_issues"] = issues
        item["health_status"] = "OK" if not issues else "PROBLEM"

    return data



@app.get("/api/alerts")
def get_active_alerts():
    check_offline_events()
    check_alert_states()

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    a.id,
                    a.store_code,
                    s.store_name,
                    a.alert_type,
                    a.target,
                    a.first_seen_at,
                    a.last_seen_at,
                    a.email_sent,
                    a.email_sent_at,
                    EXTRACT(EPOCH FROM (NOW() - a.first_seen_at))::INT AS age_seconds
                FROM alert_state a
                LEFT JOIN stores s
                    ON s.store_code = a.store_code
                WHERE a.resolved = FALSE
                ORDER BY a.first_seen_at ASC
            """)

            cols = [desc[0] for desc in cur.description]
            rows = cur.fetchall()

    return rows_to_dicts(cols, rows)


@app.get("/api/analytics/top-problems")
def analytics_top_problems(days: int = 30):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    e.store_code,
                    COALESCE(s.store_name, '') AS store_name,
                    COUNT(*) AS total_events,
                    COUNT(*) FILTER (WHERE e.event_type = 'HEARTBEAT_OFFLINE') AS offline_count,
                    COUNT(*) FILTER (WHERE e.event_type = 'SERVICE_DOWN') AS service_down_count,
                    COUNT(*) FILTER (
                        WHERE e.event_type = 'STATUS_CHANGE'
                          AND e.new_value IN ('MISSING', 'PROBLEM')
                    ) AS eod_problem_count
                FROM event_log e
                LEFT JOIN stores s
                    ON s.store_code = e.store_code
                WHERE e.created_at >= NOW() - (%s * INTERVAL '1 day')
                  AND e.event_type IN ('HEARTBEAT_OFFLINE', 'SERVICE_DOWN', 'STATUS_CHANGE')
                GROUP BY e.store_code, s.store_name
                ORDER BY total_events DESC, e.store_code
                LIMIT 20
            """, (days,))

            store_cols = [desc[0] for desc in cur.description]
            store_rows = cur.fetchall()
            top_stores = rows_to_dicts(store_cols, store_rows)

            cur.execute("""
                SELECT
                    split_part(COALESCE(new_value, old_value, ''), ':', 1) AS service_name,
                    COUNT(*) AS down_count
                FROM event_log
                WHERE created_at >= NOW() - (%s * INTERVAL '1 day')
                  AND event_type = 'SERVICE_DOWN'
                GROUP BY split_part(COALESCE(new_value, old_value, ''), ':', 1)
                ORDER BY down_count DESC, service_name
                LIMIT 20
            """, (days,))

            service_cols = [desc[0] for desc in cur.description]
            service_rows = cur.fetchall()
            top_services = rows_to_dicts(service_cols, service_rows)

            cur.execute("""
                SELECT
                    event_type,
                    COUNT(*) AS event_count
                FROM event_log
                WHERE created_at >= NOW() - (%s * INTERVAL '1 day')
                  AND event_type IN (
                        'HEARTBEAT_OFFLINE',
                        'HEARTBEAT_ONLINE',
                        'SERVICE_DOWN',
                        'SERVICE_UP',
                        'STATUS_CHANGE'
                  )
                GROUP BY event_type
                ORDER BY event_count DESC
            """, (days,))

            type_cols = [desc[0] for desc in cur.description]
            type_rows = cur.fetchall()
            event_types = rows_to_dicts(type_cols, type_rows)

    return {
        "days": days,
        "top_stores": top_stores,
        "top_services": top_services,
        "event_types": event_types
    }




def make_xlsx_response(filename, headers, rows):
    wb = Workbook()
    ws = wb.active
    ws.title = "Export"

    ws.append(headers)

    for row in rows:
        ws.append(row)

    for col in ws.columns:
        max_length = 0
        col_letter = col[0].column_letter

        for cell in col:
            value = "" if cell.value is None else str(cell.value)
            if len(value) > max_length:
                max_length = len(value)

        ws.column_dimensions[col_letter].width = min(max_length + 2, 60)

    output = BytesIO()
    wb.save(output)
    output.seek(0)

    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": "attachment; filename={}".format(filename)
        }
    )


@app.get("/api/store/{store_code}/service-history")
def get_service_history(store_code: str, service: str = ""):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    id,
                    store_code,
                    event_type,
                    old_value,
                    new_value,
                    message,
                    created_at
                FROM event_log
                WHERE store_code = %s
                  AND event_type IN ('SERVICE_STATUS', 'SERVICE_DOWN', 'SERVICE_UP', 'SERVICE_CHANGE')
                  AND (
                        %s = ''
                        OR old_value ILIKE %s
                        OR new_value ILIKE %s
                        OR message ILIKE %s
                  )
                ORDER BY id DESC
                LIMIT 50
            """, (
                store_code,
                service,
                "%" + service + "%",
                "%" + service + "%",
                "%" + service + "%"
            ))

            cols = [desc[0] for desc in cur.description]
            rows = cur.fetchall()

    return rows_to_dicts(cols, rows)


@app.get("/export/events")
def export_events():
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    e.id,
                    e.store_code,
                    COALESCE(s.store_name, '') AS store_name,
                    e.event_type,
                    e.old_value,
                    e.new_value,
                    e.message,
                    e.created_at
                FROM event_log e
                LEFT JOIN stores s
                    ON s.store_code = e.store_code
                ORDER BY e.id DESC
                LIMIT 5000
            """)

            rows = cur.fetchall()

    export_rows = []

    for r in rows:
        export_rows.append([
            r[0],
            r[1],
            r[2],
            r[3],
            r[4],
            r[5],
            r[6],
            r[7].strftime("%d.%m.%Y %H:%M:%S") if r[7] else ""
        ])

    return make_xlsx_response(
        "events_export.xlsx",
        ["ID", "Store Code", "Store Name", "Event Type", "Old", "New", "Message", "Created At"],
        export_rows
    )


@app.get("/export/alerts")
def export_alerts():
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    a.id,
                    a.store_code,
                    COALESCE(s.store_name, '') AS store_name,
                    a.alert_type,
                    a.target,
                    a.first_seen_at,
                    a.last_seen_at,
                    a.email_sent,
                    a.email_sent_at,
                    a.resolved,
                    a.resolved_at
                FROM alert_state a
                LEFT JOIN stores s
                    ON s.store_code = a.store_code
                ORDER BY a.first_seen_at DESC
                LIMIT 5000
            """)

            rows = cur.fetchall()

    export_rows = []

    for r in rows:
        export_rows.append([
            r[0],
            r[1],
            r[2],
            r[3],
            r[4],
            r[5].strftime("%d.%m.%Y %H:%M:%S") if r[5] else "",
            r[6].strftime("%d.%m.%Y %H:%M:%S") if r[6] else "",
            "DA" if r[7] else "NU",
            r[8].strftime("%d.%m.%Y %H:%M:%S") if r[8] else "",
            "DA" if r[9] else "NU",
            r[10].strftime("%d.%m.%Y %H:%M:%S") if r[10] else ""
        ])

    return make_xlsx_response(
        "alerts_export.xlsx",
        [
            "ID", "Store Code", "Store Name", "Alert Type", "Target",
            "First Seen", "Last Seen", "Email Sent", "Email Sent At",
            "Resolved", "Resolved At"
        ],
        export_rows
    )


@app.get("/export/analytics")
def export_analytics(days: int = 30):
    data = analytics_top_problems(days)

    headers = [
        "Store Code",
        "Store Name",
        "Total Events",
        "Offline Count",
        "Service Down Count",
        "EOD Problem Count"
    ]

    rows = []

    for x in data.get("top_stores", []):
        rows.append([
            x.get("store_code"),
            x.get("store_name"),
            x.get("total_events"),
            x.get("offline_count"),
            x.get("service_down_count"),
            x.get("eod_problem_count")
        ])

    return make_xlsx_response(
        "analytics_export.xlsx",
        headers,
        rows
    )



class StorePayload(BaseModel):
    store_code: str
    store_name: str = ""
    host: str = ""
    schedule_time: str = None
    active: bool = True


@app.get("/api/stores")
def api_get_stores():
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    store_code,
                    store_name,
                    host,
                    schedule_time,
                    active,
                    created_at,
                    updated_at
                FROM stores
                ORDER BY store_code
            """)

            cols = [desc[0] for desc in cur.description]
            rows = cur.fetchall()

    return rows_to_dicts(cols, rows)


@app.post("/api/stores")
def api_create_store(payload: StorePayload):
    now = dt.datetime.now()

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO stores (
                    store_code,
                    store_name,
                    host,
                    schedule_time,
                    active,
                    created_at,
                    updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (
                payload.store_code,
                payload.store_name,
                payload.host,
                payload.schedule_time,
                payload.active,
                now,
                now
            ))

    return {
        "ok": True,
        "message": "Magazin adăugat",
        "store_code": payload.store_code
    }


@app.put("/api/stores/{store_code}")
def api_update_store(store_code: str, payload: StorePayload):
    now = dt.datetime.now()

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE stores
                SET store_name = %s,
                    host = %s,
                    schedule_time = %s,
                    active = %s,
                    updated_at = %s
                WHERE store_code = %s
            """, (
                payload.store_name,
                payload.host,
                payload.schedule_time,
                payload.active,
                now,
                store_code
            ))

            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail="Store not found")

    return {
        "ok": True,
        "message": "Magazin actualizat",
        "store_code": store_code
    }


@app.delete("/api/stores/{store_code}")
def api_delete_store(store_code: str):
    # Soft delete: nu ștergem istoricul, doar dezactivăm magazinul.
    now = dt.datetime.now()

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE stores
                SET active = FALSE,
                    updated_at = %s
                WHERE store_code = %s
            """, (
                now,
                store_code
            ))

            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail="Store not found")

    return {
        "ok": True,
        "message": "Magazin dezactivat",
        "store_code": store_code
    }


@app.post("/api/stores/{store_code}/activate")
def api_activate_store(store_code: str):
    now = dt.datetime.now()

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE stores
                SET active = TRUE,
                    updated_at = %s
                WHERE store_code = %s
            """, (
                now,
                store_code
            ))

            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail="Store not found")

    return {
        "ok": True,
        "message": "Magazin activat",
        "store_code": store_code
    }



COMMON_CSS = """
<style>
* {
    box-sizing: border-box;
}

body {
    margin: 0;
    font-family: "Segoe UI", Arial, sans-serif;
    background: #f6f8fb;
    color: #0f172a;
}

.header {
    height: 64px;
    background: linear-gradient(135deg, #020617, #0f172a);
    color: white;
    display: flex;
    align-items: center;
    padding: 0 16px;
    box-shadow: 0 8px 30px rgba(15,23,42,.22);
}

.header-title {
    display: flex;
    align-items: center;
    gap: 10px;
    min-width: auto;
    flex-shrink: 0;
}

.header-title .icon {
    font-size: 24px;
}

.header-title h1 {
    margin: 0;
    font-size: 22px;
    font-weight: 900;
    letter-spacing: -.5px;
}

.nav-menu {
    display: flex;
    justify-content: flex-start;
    gap: 10px;
    margin-left: 28px;
    flex: 1;
}

.nav-btn {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    text-decoration: none;
    color: white;
    background: rgba(255,255,255,.09);
    border: 1px solid rgba(255,255,255,.13);
    padding: 10px 18px;
    border-radius: 8px;
    font-weight: 800;
    font-size: 14px;
    box-shadow: inset 0 1px 0 rgba(255,255,255,.08);
}

.nav-btn.active {
    background: linear-gradient(135deg, #1d4ed8, #2563eb);
    box-shadow: 0 10px 22px rgba(37,99,235,.35);
}

.header-right {
    min-width: 250px;
    text-align: right;
    font-size: 13px;
    color: #f8fafc;
}

.container {
    padding: 18px 18px 28px;
}

.summary-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    gap: 14px;
    margin-bottom: 16px;
}

.summary-card {
    min-height: 96px;
    background: white;
    border-radius: 12px;
    padding: 14px 16px;
    box-shadow: 0 6px 18px rgba(15,23,42,.07);
    border: 1px solid #e5e7eb;
    display: flex;
    align-items: center;
    gap: 13px;
}

.summary-icon {
    width: 52px;
    height: 52px;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 24px;
    font-weight: 900;
    flex-shrink: 0;
}

.summary-card.total .summary-icon { background:#dbeafe; color:#2563eb; }
.summary-card.ok .summary-icon { background:#dcfce7; color:#16a34a; }
.summary-card.late .summary-icon { background:#fef3c7; color:#f59e0b; }
.summary-card.bad .summary-icon { background:#fee2e2; color:#ef4444; }
.summary-card.offline .summary-icon { background:#e5e7eb; color:#64748b; }

.summary-label {
    color:#334155;
    font-size:14px;
    font-weight:700;
    text-transform: none;
}

.summary-value {
    font-size:25px;
    font-weight:900;
    margin-top:5px;
    line-height: 1;
}

.summary-card.total .summary-value { color:#2563eb; }
.summary-card.ok .summary-value { color:#16a34a; }
.summary-card.late .summary-value { color:#f59e0b; }
.summary-card.bad .summary-value { color:#ef4444; }
.summary-card.offline .summary-value { color:#64748b; }

.summary-percent {
    margin-top: 4px;
    color: #475569;
    font-size: 13px;
}

.toolbar-panel {
    background: white;
    border: 1px solid #e5e7eb;
    border-radius: 12px;
    padding: 12px 16px;
    margin-bottom: 16px;
    box-shadow: 0 6px 18px rgba(15,23,42,.06);
    display: flex;
    align-items: center;
    gap: 14px;
}

.search-wrap {
    position: relative;
    width: 475px;
    max-width: 100%;
}

.search-wrap .search-icon {
    position: absolute;
    left: 15px;
    top: 8px;
    color:#64748b;
    font-size: 18px;
}

.search-input {
    width: 100%;
    height: 38px;
    border: 1px solid #cbd5e1;
    border-radius: 8px;
    padding: 0 14px 0 42px;
    font-size: 14px;
    outline: none;
    color:#0f172a;
}

.search-input:focus {
    border-color:#2563eb;
    box-shadow: 0 0 0 3px rgba(37,99,235,.12);
}

.filter-buttons {
    margin-left: auto;
    display: flex;
    gap: 16px;
    flex-wrap: wrap;
}

button {
    min-width: 82px;
    border: 1px solid #cbd5e1;
    border-radius: 8px;
    padding: 9px 18px;
    cursor: pointer;
    background: white;
    color:#0f172a;
    font-weight: 800;
    font-size: 14px;
    box-shadow: 0 3px 10px rgba(15,23,42,.04);
}

button.active {
    border-color:#2563eb;
    background: linear-gradient(135deg, #1d4ed8, #2563eb);
    color:white;
    box-shadow: 0 10px 20px rgba(37,99,235,.28);
}

button.ok-btn { color:#15803d; }
button.bad-btn { color:#dc2626; }
button.late-btn { color:#ea580c; }
button.offline-btn { color:#475569; }

.grid {
    display:grid;
    grid-template-columns:repeat(auto-fill,minmax(410px,1fr));
    gap:16px;
}

.card {
    background:white;
    border-radius:13px;
    padding:16px 16px 14px;
    box-shadow:0 6px 18px rgba(15,23,42,.07);
    border:1px solid #e5e7eb;
    border-left:5px solid #94a3b8;
}

.card.OK { border-left-color:#22c55e; }
.card.PROBLEM { border-left-color:#ef4444; }
.card.MISSING { border-left-color:#ef4444; }
.card.LATE { border-left-color:#eab308; }
.card.OFFLINE { border-left-color:#64748b; }
.card.NO_DATA { border-left-color:#94a3b8; }

.card-top {
    display:flex;
    justify-content:space-between;
    gap:12px;
    align-items:flex-start;
    margin-bottom: 14px;
}

.store {
    font-size:17px;
    font-weight:900;
    letter-spacing: -.2px;
    color:#020617;
}

.host {
    color:#475569;
    font-size:13px;
    margin-top:5px;
}

.badge {
    border-radius:999px;
    padding:6px 14px;
    font-size:12px;
    font-weight:900;
    line-height: 1;
}

.badge.OK {
    background:#dcfce7;
    color:#15803d;
}

.badge.PROBLEM,
.badge.MISSING {
    background:#fee2e2;
    color:#b91c1c;
}

.badge.LATE {
    background:#fef3c7;
    color:#c2410c;
}

.badge.OFFLINE,
.badge.NO_DATA {
    background:#e5e7eb;
    color:#334155;
}

.details {
    margin-top: 8px;
    color:#1e293b;
    font-size:13px;
    line-height:1.5;
}

.details strong {
    font-weight:900;
}

.text-ok { color:#15803d; font-weight:900; }
.text-late { color:#ea580c; font-weight:900; }
.text-bad { color:#dc2626; font-weight:900; }

.metrics {
    margin-top:14px;
    display:grid;
    grid-template-columns:repeat(3,1fr);
    border-top:1px solid #e5e7eb;
    border-bottom:1px solid #e5e7eb;
}

.metric {
    min-height: 66px;
    padding:10px 10px;
    font-size:12px;
    color:#334155;
    border-right:1px solid #e5e7eb;
}

.metric:nth-child(3),
.metric:nth-child(6) {
    border-right:0;
}

.metric:nth-child(-n+3) {
    border-bottom:1px solid #e5e7eb;
}

.metric strong {
    display:block;
    color:#0f172a;
    font-size:14px;
    margin-top:5px;
    font-weight:900;
}

.metric .sub {
    margin-top: 4px;
    color:#475569;
    font-size: 13px;
}

.small {
    color:#475569;
    font-size:12px;
    margin-top:12px;
    line-height:1.5;
}

table {
    width:100%;
    border-collapse:collapse;
    background:white;
    border-radius:14px;
    overflow:hidden;
    box-shadow:0 8px 24px rgba(15,23,42,.08);
}

th,td {
    padding:13px;
    border-bottom:1px solid #e5e7eb;
    text-align:left;
    font-size:14px;
}

th {
    background:#0f172a;
    color:white;
}

@media (max-width: 1200px) {
    .summary-grid {
        grid-template-columns: repeat(2, 1fr);
    }

    .header {
        height:auto;
        flex-direction: column;
        align-items:flex-start;
        gap:15px;
        padding:18px;
    }

    .header-title,
    .header-right {
        min-width:0;
    }

    .header-right {
        text-align:left;
    }

    .nav-menu {
        justify-content:flex-start;
    }
}

@media (max-width: 760px) {
    .summary-grid {
        grid-template-columns: 1fr;
    }

    .grid {
        grid-template-columns: 1fr;
    }

    .toolbar-panel {
        flex-direction: column;
        align-items: stretch;
    }

    .filter-buttons {
        margin-left:0;
    }
}
</style>
"""


def nav_html(active):
    dash = "active" if active == "dashboard" else ""
    stores = "active" if active == "stores" else ""
    alerts = "active" if active == "alerts" else ""
    events = "active" if active == "events" else ""
    health = "active" if active == "health" else ""
    analytics = "active" if active == "analytics" else ""

    return """
    <div class="nav-menu">
        <a href="/dashboard" class="nav-btn {dash}">🏠 Dashboard</a>
        <a href="/stores" class="nav-btn {stores}">🏬 Stores</a>
        <a href="/alerts" class="nav-btn {alerts}">⚠ Alerts</a>
        <a href="/events" class="nav-btn {events}">▣ Event Log</a>
        <a href="/health" class="nav-btn {health}">❤ Health</a>
        <a href="/analytics" class="nav-btn {analytics}">▧ Analytics</a>
    </div>
    """.format(
        dash=dash,
        stores=stores,
        alerts=alerts,
        events=events,
        health=health,
        analytics=analytics
    )


def header_html(title, active):
    return """
<div class="header">
    <div class="header-title">
        <div class="icon">▱</div>
        <h1>{title}</h1>
    </div>
    {nav}
    <div class="header-right">
        ⟳ Ultima actualizare: <span id="lastUpdate">-</span>
    </div>
</div>
    """.format(
        title=title,
        nav=nav_html(active)
    )



@app.get("/stores", response_class=HTMLResponse)
def stores_page():
    return """
<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Store Management</title>
""" + COMMON_CSS + """
</head>
<body>
""" + header_html("Store Management", "stores") + """

<div class="container">

    <div class="form-panel">
        <h2 style="margin:0 0 14px;font-size:18px;">Adaugă / editează magazin</h2>

        <div class="form-grid">
            <div class="form-field">
                <label>Cod magazin</label>
                <input id="store_code" placeholder="ex: 5034">
            </div>

            <div class="form-field">
                <label>Nume magazin</label>
                <input id="store_name" placeholder="ex: Carrefour Craiova">
            </div>

            <div class="form-field">
                <label>Host / IP</label>
                <input id="host" placeholder="ex: 10.143.x.x">
            </div>

            <div class="form-field">
                <label>Schedule EOD</label>
                <input id="schedule_time" placeholder="ex: 23:00">
            </div>

            <div class="form-field">
                <label>Status</label>
                <select id="active">
                    <option value="true">Activ</option>
                    <option value="false">Inactiv</option>
                </select>
            </div>

            <div>
                <button class="action-btn action-save" onclick="saveStore()">Salvează</button>
                <button class="action-btn action-clear" onclick="clearForm()">Curăță</button>
            </div>
        </div>

        <div class="small" id="formMessage"></div>
    </div>

    <div class="toolbar-panel">
        <div class="search-wrap">
            <span class="search-icon">⌕</span>
            <input
                id="searchBox"
                class="search-input"
                type="text"
                placeholder="Caută magazin după cod, nume sau IP..."
                oninput="renderStores()"
            >
        </div>

        <div class="filter-buttons">
            <button onclick="setStoreFilter('ALL')" id="sfALL" class="active">Toate</button>
            <button onclick="setStoreFilter('ACTIVE')" id="sfACTIVE">Active</button>
            <button onclick="setStoreFilter('INACTIVE')" id="sfINACTIVE">Inactive</button>
        </div>
    </div>

    <div class="scroll-box" style="max-height:680px;">
        <table>
            <thead>
                <tr>
                    <th>Cod</th>
                    <th>Nume</th>
                    <th>Host / IP</th>
                    <th>Schedule</th>
                    <th>Activ</th>
                    <th>Updated</th>
                    <th>Acțiuni</th>
                </tr>
            </thead>
            <tbody id="rows"></tbody>
        </table>
    </div>

</div>

<script>
let storesData = [];
let editingStoreCode = null;
let storeFilter = 'ALL';

function formatDateTime(value) {
    if (!value) return '-';

    const d = new Date(value);
    if (isNaN(d)) return value;

    return d.toLocaleString('ro-RO', {
        day:'2-digit',
        month:'2-digit',
        year:'numeric',
        hour:'2-digit',
        minute:'2-digit',
        second:'2-digit'
    });
}

function setStoreFilter(value) {
    storeFilter = value;

    ['ALL','ACTIVE','INACTIVE'].forEach(x => {
        document.getElementById('sf' + x).classList.remove('active');
    });

    document.getElementById('sf' + value).classList.add('active');

    renderStores();
}

function clearForm() {
    editingStoreCode = null;

    document.getElementById('store_code').value = '';
    document.getElementById('store_code').disabled = false;
    document.getElementById('store_name').value = '';
    document.getElementById('host').value = '';
    document.getElementById('schedule_time').value = '';
    document.getElementById('active').value = 'true';
    document.getElementById('formMessage').innerText = '';
}

function editStore(code) {
    const x = storesData.find(s => s.store_code === code);

    if (!x) return;

    editingStoreCode = code;

    document.getElementById('store_code').value = x.store_code || '';
    document.getElementById('store_code').disabled = true;
    document.getElementById('store_name').value = x.store_name || '';
    document.getElementById('host').value = x.host || '';
    document.getElementById('schedule_time').value = x.schedule_time || '';
    document.getElementById('active').value = x.active ? 'true' : 'false';

    window.scrollTo({ top: 0, behavior: 'smooth' });
}

async function saveStore() {
    const payload = {
        store_code: document.getElementById('store_code').value.trim(),
        store_name: document.getElementById('store_name').value.trim(),
        host: document.getElementById('host').value.trim(),
        schedule_time: document.getElementById('schedule_time').value.trim() || null,
        active: document.getElementById('active').value === 'true'
    };

    if (!payload.store_code) {
        document.getElementById('formMessage').innerText = 'Codul magazinului este obligatoriu.';
        return;
    }

    const url = editingStoreCode ? '/api/stores/' + editingStoreCode : '/api/stores';
    const method = editingStoreCode ? 'PUT' : 'POST';

    const res = await fetch(url, {
        method: method,
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(payload)
    });

    const data = await res.json();

    if (!res.ok) {
        document.getElementById('formMessage').innerText = data.detail || 'Eroare la salvare.';
        return;
    }

    document.getElementById('formMessage').innerText = data.message || 'Salvat.';
    clearForm();
    await loadStores();
}

async function deactivateStore(code) {
    if (!confirm('Sigur vrei să dezactivezi magazinul ' + code + '? Istoricul NU se șterge.')) {
        return;
    }

    const res = await fetch('/api/stores/' + code, {
        method: 'DELETE'
    });

    const data = await res.json();

    if (!res.ok) {
        alert(data.detail || 'Eroare la dezactivare.');
        return;
    }

    await loadStores();
}

async function activateStore(code) {
    const res = await fetch('/api/stores/' + code + '/activate', {
        method: 'POST'
    });

    const data = await res.json();

    if (!res.ok) {
        alert(data.detail || 'Eroare la activare.');
        return;
    }

    await loadStores();
}

function renderStores() {
    const rows = document.getElementById('rows');
    rows.innerHTML = '';

    const q = document.getElementById('searchBox').value.toLowerCase().trim();

    let data = storesData;

    if (q) {
        data = data.filter(x =>
            String(x.store_code || '').toLowerCase().includes(q) ||
            String(x.store_name || '').toLowerCase().includes(q) ||
            String(x.host || '').toLowerCase().includes(q)
        );
    }

    if (storeFilter === 'ACTIVE') {
        data = data.filter(x => x.active);
    }

    if (storeFilter === 'INACTIVE') {
        data = data.filter(x => !x.active);
    }

    data.forEach(x => {
        const tr = document.createElement('tr');

        if (!x.active) {
            tr.className = 'store-inactive';
        }

        tr.innerHTML = `
            <td><strong>${x.store_code}</strong></td>
            <td>${x.store_name || '-'}</td>
            <td>${x.host || '-'}</td>
            <td>${x.schedule_time || '-'}</td>
            <td>${x.active ? '<span class="health-ok">DA</span>' : '<span class="health-bad">NU</span>'}</td>
            <td>${formatDateTime(x.updated_at)}</td>
            <td>
                <button class="action-btn action-edit" onclick="editStore('${x.store_code}')">Edit</button>
                ${
                    x.active
                    ? `<button class="action-btn action-delete" onclick="deactivateStore('${x.store_code}')">Dezactivează</button>`
                    : `<button class="action-btn action-activate" onclick="activateStore('${x.store_code}')">Activează</button>`
                }
                <a class="action-btn action-clear" style="text-decoration:none;" href="/store/${x.store_code}">Detalii</a>
            </td>
        `;

        rows.appendChild(tr);
    });
}

async function loadStores() {
    const res = await fetch('/api/stores');
    storesData = await res.json();

    document.getElementById('lastUpdate').innerText = formatDateTime(new Date());

    renderStores();
}

loadStores();
setInterval(loadStores, 30000);
</script>
</body>
</html>
"""




@app.get("/dashboard", response_class=HTMLResponse)
def dashboard_page():
    return """
<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>EOD Dashboard</title>
""" + COMMON_CSS + """
</head>

<body>
""" + header_html("EOD Dashboard", "dashboard") + """

<div class="container">

    <div class="summary-grid">
        <div class="summary-card total">
            <div class="summary-icon">▣</div>
            <div>
                <div class="summary-label">Total magazine</div>
                <div class="summary-value" id="sumTotal">0</div>
                <div class="summary-percent" id="sumTotalPct">100%</div>
            </div>
        </div>

        <div class="summary-card ok">
            <div class="summary-icon">✓</div>
            <div>
                <div class="summary-label">OK</div>
                <div class="summary-value" id="sumOk">0</div>
                <div class="summary-percent" id="sumOkPct">0%</div>
            </div>
        </div>

        <div class="summary-card late">
            <div class="summary-icon">◔</div>
            <div>
                <div class="summary-label">LATE</div>
                <div class="summary-value" id="sumLate">0</div>
                <div class="summary-percent" id="sumLatePct">0%</div>
            </div>
        </div>

        <div class="summary-card bad">
            <div class="summary-icon">!</div>
            <div>
                <div class="summary-label">PROBLEME</div>
                <div class="summary-value" id="sumBad">0</div>
                <div class="summary-percent" id="sumBadPct">0%</div>
            </div>
        </div>

        <div class="summary-card offline">
            <div class="summary-icon">⌁</div>
            <div>
                <div class="summary-label">OFFLINE / NO DATA</div>
                <div class="summary-value" id="sumOffline">0</div>
                <div class="summary-percent" id="sumOfflinePct">0%</div>
            </div>
        </div>

        <div class="summary-card bad">
            <div class="summary-icon">⚙</div>
            <div>
                <div class="summary-label">SERVICE ISSUES</div>
                <div class="summary-value" id="sumServiceIssues">0</div>
                <div class="summary-percent" id="sumServiceIssuesPct">0%</div>
            </div>
        </div>

        <div class="summary-card bad">
            <div class="summary-icon">⚠</div>
            <div>
                <div class="summary-label">ALERTE ACTIVE</div>
                <div class="summary-value" id="sumAlerts">0</div>
                <div class="summary-percent">active</div>
            </div>
        </div>
    </div>

    <div class="toolbar-panel">
        <div class="search-wrap">
            <span class="search-icon">⌕</span>
            <input
                id="searchBox"
                class="search-input"
                type="text"
                placeholder="Caută după cod, nume sau IP..."
                oninput="render()"
            >
        </div>

        <div class="filter-buttons">
            <button onclick="setFilter('ALL')" id="btnALL" class="active">Toate</button>
            <button onclick="setFilter('OK')" id="btnOK" class="ok-btn">OK</button>
            <button onclick="setFilter('BAD')" id="btnBAD" class="bad-btn">Probleme</button>
            <button onclick="setFilter('LATE')" id="btnLATE" class="late-btn">Late</button>
            <button onclick="setFilter('OFFLINE')" id="btnOFFLINE" class="offline-btn">Offline</button>
        </div>
    </div>

    <div class="grid" id="cards"></div>

</div>

<script>
let allData = [];
let currentFilter = 'ALL';

function setFilter(filter) {
    currentFilter = filter;

    ['ALL','OK','BAD','LATE','OFFLINE'].forEach(x => {
        document.getElementById('btn'+x).classList.remove('active');
    });

    document.getElementById('btn'+filter).classList.add('active');

    render();
}

function formatPercentValue(value, total) {
    if (!total) return '0%';
    return ((value / total) * 100).toFixed(1) + '%';
}

function formatDateOnly(value) {
    if (!value) return '-';

    const d = new Date(value);
    if (isNaN(d)) return value;

    return d.toLocaleDateString('ro-RO', {
        day: '2-digit',
        month: '2-digit',
        year: 'numeric'
    });
}

function formatDateTime(value) {
    if (!value) return '-';

    const d = new Date(value);
    if (isNaN(d)) return value;

    return d.toLocaleString('ro-RO', {
        day: '2-digit',
        month: '2-digit',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit'
    });
}

function uptimeText(sec) {
    if (!sec) return '-';
    let days = Math.floor(sec / 86400);
    let hours = Math.floor((sec % 86400) / 3600);
    return days + 'z ' + hours + 'h';
}

function pct(x) {
    if (x === null || x === undefined) return '-';
    return Number(x).toFixed(1) + '%';
}

function val(x, suffix='') {
    if (x === null || x === undefined) return '-';
    return x + suffix;
}

function statusTextClass(status) {
    if (status === 'OK') return 'text-ok';
    if (status === 'LATE' || status === 'MISSING') return 'text-late';
    if (status === 'PROBLEM') return 'text-bad';
    return '';
}

function updateSummary() {
    const total = allData.length;
    const ok = allData.filter(x => x.status === 'OK').length;
    const late = allData.filter(x => x.status === 'LATE').length;
    const bad = allData.filter(x => ['PROBLEM','MISSING'].includes(x.status)).length;
    const offline = allData.filter(x => ['OFFLINE','NO_DATA'].includes(x.status)).length;
    const serviceIssues = allData.filter(x => {
        const services = x.services_status || {};
        return Object.keys(services).some(k => services[k] !== 'active');
    }).length;

    document.getElementById('sumTotal').innerText = total;
    document.getElementById('sumOk').innerText = ok;
    document.getElementById('sumLate').innerText = late;
    document.getElementById('sumBad').innerText = bad;
    document.getElementById('sumOffline').innerText = offline;
    document.getElementById('sumServiceIssues').innerText = serviceIssues;

    document.getElementById('sumTotalPct').innerText = total ? '100%' : '0%';
    document.getElementById('sumOkPct').innerText = formatPercentValue(ok, total);
    document.getElementById('sumLatePct').innerText = formatPercentValue(late, total);
    document.getElementById('sumBadPct').innerText = formatPercentValue(bad, total);
    document.getElementById('sumOfflinePct').innerText = formatPercentValue(offline, total);
    document.getElementById('sumServiceIssuesPct').innerText = formatPercentValue(serviceIssues, total);
}


function cleanMessage(value) {
    if (!value) return '-';

    const map = {
        "Nu exista fisier EOD": "Nu există fișier EOD.",
        "Nu exista niciun fisier EOD": "Nu există niciun fișier EOD.",
        "Nu exista fisier EOD pentru ziua curenta": "Nu există fișier EOD pentru ziua curentă."
    };

    return map[value] || value;
}

function render() {
    updateSummary();

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

    if (currentFilter === 'OK') {
        filtered = filtered.filter(x => x.status === 'OK');
    }

    if (currentFilter === 'BAD') {
        filtered = filtered.filter(x => ['PROBLEM','MISSING'].includes(x.status));
    }

    if (currentFilter === 'LATE') {
        filtered = filtered.filter(x => x.status === 'LATE');
    }

    if (currentFilter === 'OFFLINE') {
        filtered = filtered.filter(x => ['OFFLINE','NO_DATA'].includes(x.status));
    }

    filtered.forEach(x => {
        const div = document.createElement('div');
        div.className = 'card ' + x.status;

        const cls = statusTextClass(x.status);

        div.innerHTML = `
            <div class="card-top">
                <div>
                    <div class="store"><a href="/store/${x.store_code}" style="color:inherit;text-decoration:none;">${x.store_code} — ${x.store_name || ''}</a></div>
                    <div class="host">${x.host || ''} &nbsp;•&nbsp; Schedule: ${x.schedule_time || '-'}</div>
                </div>
                <div class="badge ${x.status}">${x.status}</div>
            </div>

            <div class="details">
                <strong>Fișier:</strong> <span class="${cls}">${x.eod_file || '-'}</span><br>
                <strong>Mesaj:</strong> ${cleanMessage(x.message)}<br>
                <strong>Data EOD:</strong> <span class="${cls}">${formatDateOnly(x.eod_date)}</span><br>
                <strong>Ultimul EOD:</strong> ${formatDateTime(x.eod_file_created_at || x.last_eod_file_created_at)}<br>
                <strong>OK valid până la:</strong> ${formatDateTime(x.ok_valid_until)}
            </div>

            <div class="metrics">
                <div class="metric">CPU<strong>${pct(x.cpu_load_1m)}</strong></div>
                <div class="metric">RAM<strong>${val(x.ram_used_mb, ' MB')} / ${val(x.ram_total_mb, ' MB')}</strong><div class="sub">${pct(x.ram_percent)}</div></div>
                <div class="metric">Disk<strong>${val(x.disk_used_gb, ' GB')} / ${val(x.disk_total_gb, ' GB')}</strong><div class="sub">${pct(x.disk_percent)}</div></div>
                <div class="metric">Uptime<strong>${uptimeText(x.uptime_seconds)}</strong></div>
                <div class="metric">Agent<strong>${x.agent_version || '-'}</strong></div>
                <div class="metric">Host<strong>${x.hostname || '-'}</strong></div>
            </div>

            <div class="small">
                OS: ${x.os_info || '-'}<br>
                Ultim heartbeat: ${formatDateTime(x.last_heartbeat)}
            </div>
        `;

        cards.appendChild(div);
    });
}

async function loadDashboard() {
    const res = await fetch('/api/dashboard');
    allData = await res.json();

    try {
        const alertRes = await fetch('/api/alerts');
        const alerts = await alertRes.json();
        document.getElementById('sumAlerts').innerText = alerts.length || 0;
    } catch (e) {
        document.getElementById('sumAlerts').innerText = '-';
    }

    document.getElementById('lastUpdate').innerText = formatDateTime(new Date());
    render();
}

loadDashboard();
setInterval(loadDashboard, 30000);
</script>

</body>
</html>
"""


@app.get("/events", response_class=HTMLResponse)
def events_page():
    return """
<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>EOD Event Log</title>
""" + COMMON_CSS + """
</head>
<body>
""" + header_html("EOD Event Log", "events") + """

<div class="container">
    <div class="event-toolbar">
        <button class="event-pill active" onclick="setEventFilter('ALL')" id="evALL">Toate</button>
        <button class="event-pill" onclick="setEventFilter('HEARTBEAT')" id="evHEARTBEAT">Agent offline/online</button>
        <button class="event-pill" onclick="setEventFilter('SERVICE')" id="evSERVICE">Servicii</button>
        <button class="event-pill" onclick="setEventFilter('STATUS_CHANGE')" id="evSTATUS_CHANGE">EOD status</button>
        <button class="event-pill" onclick="setEventFilter('BAD')" id="evBAD">Probleme</button>
        <a class="export-link" href="/export/events">Export Events</a>
    </div>

    <div class="scroll-box" style="max-height:650px;">
        <table>
            <thead>
                <tr>
                    <th>ID</th>
                    <th>Magazin</th>
                    <th>Tip</th>
                    <th>Old</th>
                    <th>New</th>
                    <th>Mesaj</th>
                    <th>Creat la</th>
                </tr>
            </thead>
            <tbody id="rows"></tbody>
        </table>
    </div>
</div>

<script>
let allEvents = [];
let eventFilter = 'ALL';

function formatDateTime(value) {
    if (!value) return '-';

    const d = new Date(value);
    if (isNaN(d)) return value;

    return d.toLocaleString('ro-RO', {
        day: '2-digit',
        month: '2-digit',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit'
    });
}

function eventTypeLabel(value) {
    const labels = {
        "HEARTBEAT_OFFLINE": "Agent offline",
        "HEARTBEAT_ONLINE": "Agent online",
        "SERVICE_DOWN": "Serviciu oprit",
        "SERVICE_UP": "Serviciu activ",
        "SERVICE_CHANGE": "Serviciu schimbat",
        "SERVICE_STATUS": "Status serviciu",
        "STATUS_CHANGE": "Status EOD schimbat"
    };

    return labels[value] || value || '-';
}

function setEventFilter(value) {
    eventFilter = value;

    ['ALL','HEARTBEAT','SERVICE','STATUS_CHANGE','BAD'].forEach(x => {
        document.getElementById('ev' + x).classList.remove('active');
    });

    document.getElementById('ev' + value).classList.add('active');

    renderEvents();
}

function matchEvent(x) {
    if (eventFilter === 'ALL') return true;

    if (eventFilter === 'HEARTBEAT') {
        return ['HEARTBEAT_OFFLINE','HEARTBEAT_ONLINE'].includes(x.event_type);
    }

    if (eventFilter === 'SERVICE') {
        return String(x.event_type || '').startsWith('SERVICE_');
    }

    if (eventFilter === 'STATUS_CHANGE') {
        return x.event_type === 'STATUS_CHANGE';
    }

    if (eventFilter === 'BAD') {
        return ['HEARTBEAT_OFFLINE','SERVICE_DOWN','SERVICE_CHANGE'].includes(x.event_type)
            || String(x.new_value || '').includes('MISSING')
            || String(x.new_value || '').includes('PROBLEM');
    }

    return true;
}

function renderEvents() {
    const rows = document.getElementById('rows');
    rows.innerHTML = '';

    allEvents.filter(matchEvent).forEach(x => {
        const tr = document.createElement('tr');

        tr.innerHTML = `
            <td>${x.id}</td>
            <td>${x.store_code || ''} — ${x.store_name || ''}</td>
            <td>${eventTypeLabel(x.event_type)}</td>
            <td>${x.old_value || '-'}</td>
            <td>${x.new_value || '-'}</td>
            <td>${x.message || ''}</td>
            <td>${formatDateTime(x.created_at)}</td>
        `;

        rows.appendChild(tr);
    });
}

async function loadEvents() {
    const res = await fetch('/api/events?limit=500');
    allEvents = await res.json();

    document.getElementById('lastUpdate').innerText = formatDateTime(new Date());

    renderEvents();
}

loadEvents();
setInterval(loadEvents, 30000);
</script>
</body>
</html>
"""


@app.get("/reports/daily", response_class=HTMLResponse)
def daily_report_page():
    return """
<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>EOD Daily Report</title>
""" + COMMON_CSS + """
</head>
<body>
""" + header_html("Daily EOD Report", "daily") + """

<div class="container">
    <div class="summary-grid">
        <div class="summary-card total"><div class="summary-icon">▣</div><div><div class="summary-label">Total magazine</div><div class="summary-value" id="total">0</div><div class="summary-percent">100%</div></div></div>
        <div class="summary-card ok"><div class="summary-icon">✓</div><div><div class="summary-label">OK</div><div class="summary-value" id="ok">0</div><div class="summary-percent" id="okPct">0%</div></div></div>
        <div class="summary-card late"><div class="summary-icon">◔</div><div><div class="summary-label">LATE</div><div class="summary-value" id="late">0</div><div class="summary-percent" id="latePct">0%</div></div></div>
        <div class="summary-card bad"><div class="summary-icon">!</div><div><div class="summary-label">MISSING</div><div class="summary-value" id="missing">0</div><div class="summary-percent" id="missingPct">0%</div></div></div>
        <div class="summary-card bad"><div class="summary-icon">!</div><div><div class="summary-label">PROBLEM</div><div class="summary-value" id="problem">0</div><div class="summary-percent" id="problemPct">0%</div></div></div>
        <div class="summary-card offline"><div class="summary-icon">⌁</div><div><div class="summary-label">OFFLINE</div><div class="summary-value" id="offline">0</div><div class="summary-percent" id="offlinePct">0%</div></div></div>
        <div class="summary-card offline"><div class="summary-icon">⌁</div><div><div class="summary-label">NO DATA</div><div class="summary-value" id="nodata">0</div><div class="summary-percent" id="nodataPct">0%</div></div></div>
    </div>
</div>

<script>
function formatDateTime(value) {
    if (!value) return '-';

    const d = new Date(value);
    if (isNaN(d)) return value;

    return d.toLocaleString('ro-RO', {
        day: '2-digit',
        month: '2-digit',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit'
    });
}

function percent(value, total) {
    if (!total) return '0%';
    return ((value / total) * 100).toFixed(1) + '%';
}

async function loadReport() {
    const res = await fetch('/api/reports/daily');
    const x = await res.json();

    const total = x.total_stores || 0;

    document.getElementById('lastUpdate').innerText = formatDateTime(new Date());

    document.getElementById('total').innerText = total;
    document.getElementById('ok').innerText = x.ok_count || 0;
    document.getElementById('late').innerText = x.late_count || 0;
    document.getElementById('missing').innerText = x.missing_count || 0;
    document.getElementById('problem').innerText = x.problem_count || 0;
    document.getElementById('offline').innerText = x.offline_count || 0;
    document.getElementById('nodata').innerText = x.no_data_count || 0;

    document.getElementById('okPct').innerText = percent(x.ok_count || 0, total);
    document.getElementById('latePct').innerText = percent(x.late_count || 0, total);
    document.getElementById('missingPct').innerText = percent(x.missing_count || 0, total);
    document.getElementById('problemPct').innerText = percent(x.problem_count || 0, total);
    document.getElementById('offlinePct').innerText = percent(x.offline_count || 0, total);
    document.getElementById('nodataPct').innerText = percent(x.no_data_count || 0, total);
}

loadReport();
setInterval(loadReport, 30000);
</script>
</body>
</html>
"""



@app.get("/health", response_class=HTMLResponse)
def health_page():
    return """
<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Health Dashboard</title>
""" + COMMON_CSS + """
</head>
<body>
""" + header_html("Health Dashboard", "health") + """

<div class="container">
    <div class="event-toolbar">
        <button class="event-pill active" onclick="setHealthFilter('ALL')" id="hfALL">Toate</button>
        <button class="event-pill" onclick="setHealthFilter('PROBLEM')" id="hfPROBLEM">Doar probleme</button>
        <button class="event-pill" onclick="setHealthFilter('SERVICES')" id="hfSERVICES">Servicii oprite</button>
        <button class="event-pill" onclick="setHealthFilter('RESOURCE')" id="hfRESOURCE">Resurse mari</button>
    </div>

    <div class="scroll-box" style="max-height:700px;">
        <table>
            <thead>
                <tr>
                    <th>Magazin</th>
                    <th>Status</th>
                    <th>CPU</th>
                    <th>RAM</th>
                    <th>Disk</th>
                    <th>Uptime</th>
                    <th>Servicii oprite</th>
                    <th>Probleme</th>
                </tr>
            </thead>
            <tbody id="rows"></tbody>
        </table>
    </div>
</div>

<script>
let healthData = [];
let healthFilter = 'ALL';

function pct(x) {
    if (x === null || x === undefined) return '-';
    return Number(x).toFixed(1) + '%';
}

function uptimeText(sec) {
    if (!sec) return '-';
    let days = Math.floor(sec / 86400);
    let hours = Math.floor((sec % 86400) / 3600);
    return days + 'z ' + hours + 'h';
}

function clsByPct(x, warn, bad) {
    if (x === null || x === undefined) return '';
    if (Number(x) >= bad) return 'health-bad';
    if (Number(x) >= warn) return 'health-warn';
    return 'health-ok';
}

function setHealthFilter(value) {
    healthFilter = value;

    ['ALL','PROBLEM','SERVICES','RESOURCE'].forEach(x => {
        document.getElementById('hf' + x).classList.remove('active');
    });

    document.getElementById('hf' + value).classList.add('active');

    renderHealth();
}

function matchHealth(x) {
    if (healthFilter === 'ALL') return true;
    if (healthFilter === 'PROBLEM') return x.health_status === 'PROBLEM';
    if (healthFilter === 'SERVICES') return Number(x.service_down_count || 0) > 0;
    if (healthFilter === 'RESOURCE') {
        return Number(x.disk_percent || 0) >= 90
            || Number(x.ram_percent || 0) >= 85
            || Number(x.cpu_load_1m || 0) >= 85;
    }
    return true;
}

function renderHealth() {
    const rows = document.getElementById('rows');
    rows.innerHTML = '';

    healthData.filter(matchHealth).forEach(x => {
        const tr = document.createElement('tr');

        const issues = (x.health_issues || []).join('<br>') || '-';
        const statusClass = x.health_status === 'OK' ? 'health-ok' : 'health-bad';

        tr.innerHTML = `
            <td><a href="/store/${x.store_code}" style="color:inherit;text-decoration:none;font-weight:900;">${x.store_code} — ${x.store_name || ''}</a></td>
            <td class="${statusClass}">${x.health_status || '-'}</td>
            <td class="${clsByPct(x.cpu_load_1m, 70, 85)}">${pct(x.cpu_load_1m)}</td>
            <td class="${clsByPct(x.ram_percent, 75, 85)}">${pct(x.ram_percent)}</td>
            <td class="${clsByPct(x.disk_percent, 80, 90)}">${pct(x.disk_percent)}</td>
            <td>${uptimeText(x.uptime_seconds)}</td>
            <td>${x.service_down_count || 0}</td>
            <td>${issues}</td>
        `;

        rows.appendChild(tr);
    });
}

async function loadHealth() {
    const res = await fetch('/api/health');
    healthData = await res.json();

    document.getElementById('lastUpdate').innerText =
        new Date().toLocaleString('ro-RO', {
            day:'2-digit',
            month:'2-digit',
            year:'numeric',
            hour:'2-digit',
            minute:'2-digit',
            second:'2-digit'
        });

    renderHealth();
}

loadHealth();
setInterval(loadHealth, 30000);
</script>
</body>
</html>
"""




def send_monitor_alert(alert_type, title, subtitle, store_code=None, store_name=None, details=None, dashboard_url=None):
    details = details or []

    rows = []

    if store_code:
        rows.append(("Magazin", "{} - {}".format(store_code, store_name or "")))

    rows.append(("Tip alertă", alert_type))

    for label, value in details:
        rows.append((label, value))

    rows.append(("Ora alertă", dt.datetime.now().strftime("%d.%m.%Y %H:%M:%S")))

    subject = "[EOD Monitor] {}".format(title)

    if store_code:
        subject += " - {}".format(store_code)

    body_text = "EOD Monitor Alert\n\n{}\n\n{}\n".format(
        title,
        subtitle
    )

    for label, value in rows:
        body_text += "\n{}: {}".format(label, value)

    if dashboard_url:
        body_text += "\n\nDashboard:\n{}".format(dashboard_url)

    body_html = build_email_template(
        alert_type=alert_type,
        title=title,
        subtitle=subtitle,
        rows=rows,
        dashboard_url=dashboard_url
    )

    send_email_alert(
        subject,
        body_text,
        body_html
    )


@app.get("/alerts", response_class=HTMLResponse)
def alerts_page():
    return """
<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Alert Center</title>
""" + COMMON_CSS + """
</head>
<body>
""" + header_html("Alert Center", "alerts") + """

<div class="container">

    <div class="event-toolbar">
        <button class="event-pill active" onclick="setAlertFilter('ALL')" id="alALL">Toate</button>
        <button class="event-pill" onclick="setAlertFilter('EOD_MISSING')" id="alEOD_MISSING">EOD</button>
        <button class="event-pill" onclick="setAlertFilter('AGENT_OFFLINE')" id="alAGENT_OFFLINE">Agent</button>
        <button class="event-pill" onclick="setAlertFilter('SERVICE_DOWN')" id="alSERVICE_DOWN">Servicii</button>
        <a class="export-link" href="/export/alerts">Export Alerts</a>
    </div>

    <div id="alerts"></div>
</div>

<script>
let allAlerts = [];
let alertFilter = 'ALL';

function formatDateTime(value) {
    if (!value) return '-';
    const d = new Date(value);
    if (isNaN(d)) return value;
    return d.toLocaleString('ro-RO', {
        day:'2-digit', month:'2-digit', year:'numeric',
        hour:'2-digit', minute:'2-digit', second:'2-digit'
    });
}

function ageText(sec) {
    if (!sec) return '-';
    const m = Math.floor(sec / 60);
    const h = Math.floor(m / 60);
    const mm = m % 60;
    if (h > 0) return h + 'h ' + mm + 'm';
    return m + 'm';
}

function alertLabel(value) {
    const labels = {
        "EOD_MISSING": "EOD lipsă",
        "AGENT_OFFLINE": "Agent offline",
        "SERVICE_DOWN": "Serviciu oprit"
    };
    return labels[value] || value;
}

function setAlertFilter(value) {
    alertFilter = value;

    ['ALL','EOD_MISSING','AGENT_OFFLINE','SERVICE_DOWN'].forEach(x => {
        document.getElementById('al' + x).classList.remove('active');
    });

    document.getElementById('al' + value).classList.add('active');

    renderAlerts();
}

function renderAlerts() {
    const box = document.getElementById('alerts');
    box.innerHTML = '';

    const data = allAlerts.filter(x => alertFilter === 'ALL' || x.alert_type === alertFilter);

    if (!data.length) {
        box.innerHTML = `
            <div class="alert-card" style="border-left-color:#16a34a;">
                <div class="alert-title">Nu există alerte active</div>
                <div class="alert-meta">Totul este în regulă pentru filtrul selectat.</div>
            </div>
        `;
        return;
    }

    data.forEach(x => {
        const div = document.createElement('div');
        div.className = 'alert-card';

        div.innerHTML = `
            <div class="alert-title">
                <a href="/store/${x.store_code}" style="color:inherit;text-decoration:none;">
                    ${alertLabel(x.alert_type)} — ${x.store_code} ${x.store_name || ''}
                </a>
            </div>
            <div class="alert-meta">
                <strong>Target:</strong> ${x.target || '-'}<br>
                <strong>Prima detectare:</strong> ${formatDateTime(x.first_seen_at)}<br>
                <strong>Ultima verificare:</strong> ${formatDateTime(x.last_seen_at)}<br>
                <strong>Durată:</strong> ${ageText(x.age_seconds)}<br>
                <strong>Email trimis:</strong> ${x.email_sent ? 'DA' : 'NU'} ${x.email_sent_at ? '(' + formatDateTime(x.email_sent_at) + ')' : ''}
            </div>
        `;

        box.appendChild(div);
    });
}

async function loadAlerts() {
    const res = await fetch('/api/alerts');
    allAlerts = await res.json();

    document.getElementById('lastUpdate').innerText = formatDateTime(new Date());

    renderAlerts();
}

loadAlerts();
setInterval(loadAlerts, 30000);
</script>
</body>
</html>
"""


@app.get("/analytics", response_class=HTMLResponse)
def analytics_page():
    return """
<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Analytics</title>
""" + COMMON_CSS + """
</head>
<body>
""" + header_html("Analytics", "analytics") + """

<div class="container">
    <div class="export-bar"><a class="export-link" href="/export/analytics">Export Analytics</a></div>
    <div class="analytics-grid">
        <div class="analytics-panel">
            <h2>Top magazine cu probleme - ultimele 30 zile</h2>
            <div class="scroll-box" style="max-height:620px;">
                <table>
                    <thead>
                        <tr>
                            <th>Magazin</th>
                            <th>Total</th>
                            <th>Offline</th>
                            <th>Service down</th>
                            <th>EOD probleme</th>
                        </tr>
                    </thead>
                    <tbody id="topStores"></tbody>
                </table>
            </div>
        </div>

        <div class="analytics-panel">
            <h2>Top servicii care cad - ultimele 30 zile</h2>
            <div class="scroll-box" style="max-height:300px;">
                <table>
                    <thead>
                        <tr>
                            <th>Serviciu</th>
                            <th>Căderi</th>
                        </tr>
                    </thead>
                    <tbody id="topServices"></tbody>
                </table>
            </div>

            <br>

            <h2>Tipuri evenimente</h2>
            <div class="scroll-box" style="max-height:260px;">
                <table>
                    <thead>
                        <tr>
                            <th>Eveniment</th>
                            <th>Total</th>
                        </tr>
                    </thead>
                    <tbody id="eventTypes"></tbody>
                </table>
            </div>
        </div>
    </div>
</div>

<script>
function formatDateTime(value) {
    if (!value) return '-';
    const d = new Date(value);
    if (isNaN(d)) return value;
    return d.toLocaleString('ro-RO', {
        day:'2-digit', month:'2-digit', year:'numeric',
        hour:'2-digit', minute:'2-digit', second:'2-digit'
    });
}

function eventLabel(value) {
    const labels = {
        "HEARTBEAT_OFFLINE": "Agent offline",
        "HEARTBEAT_ONLINE": "Agent online",
        "SERVICE_DOWN": "Serviciu oprit",
        "SERVICE_UP": "Serviciu activ",
        "STATUS_CHANGE": "Status EOD schimbat"
    };
    return labels[value] || value || '-';
}

async function loadAnalytics() {
    const res = await fetch('/api/analytics/top-problems?days=30');
    const data = await res.json();

    document.getElementById('lastUpdate').innerText = formatDateTime(new Date());

    const topStores = document.getElementById('topStores');
    topStores.innerHTML = '';

    (data.top_stores || []).forEach(x => {
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td><a href="/store/${x.store_code}" style="color:inherit;text-decoration:none;font-weight:900;">${x.store_code} — ${x.store_name || ''}</a></td>
            <td class="health-bad">${x.total_events || 0}</td>
            <td>${x.offline_count || 0}</td>
            <td>${x.service_down_count || 0}</td>
            <td>${x.eod_problem_count || 0}</td>
        `;
        topStores.appendChild(tr);
    });

    const topServices = document.getElementById('topServices');
    topServices.innerHTML = '';

    (data.top_services || []).forEach(x => {
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td>${x.service_name || '-'}</td>
            <td class="health-bad">${x.down_count || 0}</td>
        `;
        topServices.appendChild(tr);
    });

    const eventTypes = document.getElementById('eventTypes');
    eventTypes.innerHTML = '';

    (data.event_types || []).forEach(x => {
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td>${eventLabel(x.event_type)}</td>
            <td>${x.event_count || 0}</td>
        `;
        eventTypes.appendChild(tr);
    });
}

loadAnalytics();
setInterval(loadAnalytics, 30000);
</script>
</body>
</html>
"""



@app.get("/test-email")
def test_email():
    try:
        now_text = dt.datetime.now().strftime("%d.%m.%Y %H:%M:%S")

        subject = "[EOD Monitor] TEST EMAIL"

        body_text = """
EOD Monitor - Test Email

Acesta este un email de test.
Serverul EOD Monitor funcționează corect.

Ora test:
{}
        """.format(
            now_text
        )

        body_html = build_email_template(
            alert_type="TEST",
            title="Test email",
            subtitle="Serverul EOD Monitor funcționează corect.",
            rows=[
                ("Tip alertă", "TEST"),
                ("Status", "SMTP funcțional"),
                ("Ora test", now_text),
                ("Destinatar", ", ".join(SMTP_CONFIG["to"])),
                ("SMTP server", "{}:{}".format(SMTP_CONFIG["host"], SMTP_CONFIG["port"]))
            ],
            dashboard_url="http://10.143.252.2:8000/dashboard"
        )

        send_email_alert(
            subject,
            body_text,
            body_html
        )

        return {
            "ok": True,
            "message": "Test email HTML trimis"
        }

    except Exception as e:
        print("TEST EMAIL ERROR:", str(e))

        return {
            "ok": False,
            "error": str(e)
        }
