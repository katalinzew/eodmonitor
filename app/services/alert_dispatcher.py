import asyncio
import datetime as dt

from app.core.config import ALERT_DELAY_MINUTES
from app.core.database import get_conn
from app.repositories.alert_repository import (
    get_pending_email_alerts,
    mark_email_sent,
)
from app.services.mail_service import send_email
from app.services.status_service import get_eod_alert_due_at, is_eod_alert_due


ALERT_DISPATCH_INTERVAL_SECONDS = 60


def is_old_enough(first_seen_at, now):
    return first_seen_at <= now - dt.timedelta(minutes=ALERT_DELAY_MINUTES)


def should_send_alert_email(alert, now):
    (
        alert_id,
        store_code,
        store_name,
        host,
        schedule_time,
        alert_type,
        target,
        first_seen_at,
        last_seen_at,
        email_sent,
    ) = alert

    if email_sent:
        return False

    if alert_type in ("AGENT_OFFLINE", "SERVICE_DOWN", "HEALTH_WARNING"):
        return is_old_enough(first_seen_at, now)

    if alert_type == "EOD_MISSING":
        if first_seen_at.date() != now.date():
            return False

        if not is_eod_alert_due(schedule_time, now):
            return False

        schedule_due_at = get_eod_alert_due_at(schedule_time, now)
        email_delay_started_at = max(
            first_seen_at,
            schedule_due_at or first_seen_at,
        )
        return is_old_enough(email_delay_started_at, now)

    return False


def build_alert_email(alert):
    (
        alert_id,
        store_code,
        store_name,
        host,
        schedule_time,
        alert_type,
        target,
        first_seen_at,
        last_seen_at,
        email_sent,
    ) = alert

    subject = f"[EOD Monitor] {alert_type} - {store_code} - {target}"

    text_body = (
        f"EOD Monitor Alert\n\n"
        f"Magazin: {store_code} - {store_name}\n"
        f"Host: {host}\n"
        f"Tip alertă: {alert_type}\n"
        f"Target: {target}\n"
        f"Prima apariție: {first_seen_at}\n"
        f"Ultima confirmare: {last_seen_at}\n"
    )

    html_body = f"""
    <html>
    <body style="margin:0;padding:0;background:#070b14;font-family:Arial,sans-serif;color:#e5eefb;">
        <div style="max-width:640px;margin:0 auto;padding:18px;
            background:radial-gradient(circle at top left, rgba(34,211,238,.18), transparent 35%),
                       radial-gradient(circle at top right, rgba(59,130,246,.16), transparent 35%),
                       linear-gradient(135deg,#020617,#07111f);">

            <div style="background:rgba(15,23,42,.92);border:1px solid rgba(148,163,184,.18);
                border-radius:18px;overflow:hidden;box-shadow:0 22px 60px rgba(0,0,0,.45);">

                <div style="padding:18px 22px;border-bottom:1px solid rgba(148,163,184,.18);
                    background:linear-gradient(135deg,rgba(34,211,238,.12),transparent 45%);">
                    <div style="font-size:22px;font-weight:900;color:#ffffff;">
                        EOD Monitor
                    </div>
                    <div style="font-size:13px;color:#94a3b8;margin-top:3px;">
                        Sistem monitorizare magazine
                    </div>
                </div>

                <div style="padding:22px;">
                    <div style="display:inline-block;padding:6px 11px;border-radius:999px;
                        background:rgba(239,68,68,.14);border:1px solid rgba(239,68,68,.35);
                        color:#fecaca;font-size:11px;font-weight:900;">
                        ALERTĂ ACTIVĂ
                    </div>

                    <h2 style="margin:16px 0 6px;font-size:24px;color:#ffffff;">
                        {alert_type}
                    </h2>

                    <p style="margin:0 0 18px;color:#cbd5e1;font-size:14px;">
                        Problema persistă de cel puțin {ALERT_DELAY_MINUTES} minute.
                    </p>

                    <table style="width:100%;border-collapse:collapse;background:rgba(2,6,23,.55);
                        border:1px solid rgba(148,163,184,.16);border-radius:14px;overflow:hidden;font-size:13px;">
                        <tr>
                            <td style="padding:11px 13px;color:#94a3b8;border-bottom:1px solid rgba(148,163,184,.14);width:38%;">Magazin</td>
                            <td style="padding:11px 13px;color:#ffffff;font-weight:800;border-bottom:1px solid rgba(148,163,184,.14);">{store_code} - {store_name}</td>
                        </tr>
                        <tr>
                            <td style="padding:11px 13px;color:#94a3b8;border-bottom:1px solid rgba(148,163,184,.14);">Host</td>
                            <td style="padding:11px 13px;color:#e0f2fe;font-weight:800;border-bottom:1px solid rgba(148,163,184,.14);">{host}</td>
                        </tr>
                        <tr>
                            <td style="padding:11px 13px;color:#94a3b8;border-bottom:1px solid rgba(148,163,184,.14);">Tip alertă</td>
                            <td style="padding:11px 13px;color:#fecaca;font-weight:900;border-bottom:1px solid rgba(148,163,184,.14);">{alert_type}</td>
                        </tr>
                        <tr>
                            <td style="padding:11px 13px;color:#94a3b8;border-bottom:1px solid rgba(148,163,184,.14);">Target</td>
                            <td style="padding:11px 13px;color:#ffffff;font-weight:800;border-bottom:1px solid rgba(148,163,184,.14);">{target}</td>
                        </tr>
                        <tr>
                            <td style="padding:11px 13px;color:#94a3b8;border-bottom:1px solid rgba(148,163,184,.14);">Prima apariție</td>
                            <td style="padding:11px 13px;color:#ffffff;font-weight:800;border-bottom:1px solid rgba(148,163,184,.14);">{first_seen_at}</td>
                        </tr>
                        <tr>
                            <td style="padding:11px 13px;color:#94a3b8;">Ultima confirmare</td>
                            <td style="padding:11px 13px;color:#ffffff;font-weight:800;">{last_seen_at}</td>
                        </tr>
                    </table>

                    <div style="margin-top:16px;padding:12px 14px;border-radius:14px;
                        background:rgba(8,145,178,.16);border:1px solid rgba(34,211,238,.35);
                        color:#bae6fd;font-size:12px;">
                        Email generat automat de EOD Monitor. Nu este necesar reply.
                    </div>
                </div>
            </div>

            <div style="text-align:center;color:#64748b;font-size:11px;margin-top:12px;">
                EOD Monitor · Operational Alerting
            </div>
        </div>
    </body>
    </html>
    """

    return subject, html_body, text_body

def dispatch_alert_emails_once():
    now = dt.datetime.now()
    sent_count = 0

    with get_conn() as conn:
        with conn.cursor() as cur:
            alerts = get_pending_email_alerts(cur)

            for alert in alerts:
                if not should_send_alert_email(alert, now):
                    continue

                alert_id = alert[0]
                subject, html_body, text_body = build_alert_email(alert)

                send_email(
                    subject=subject,
                    html_body=html_body,
                    text_body=text_body,
                )

                mark_email_sent(cur, alert_id, now)
                sent_count += 1

    return sent_count

def send_alert_now(alert_id):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    a.id,
                    a.store_code,
                    s.store_name,
                    s.host,
                    s.schedule_time,
                    a.alert_type,
                    a.target,
                    a.first_seen_at,
                    a.last_seen_at,
                    a.email_sent
                FROM alert_state a
                LEFT JOIN stores s
                    ON s.store_code = a.store_code
                WHERE a.id = %s
                """,
                (alert_id,),
            )

            alert = cur.fetchone()

            if not alert:
                return False

            subject, html_body, text_body = build_alert_email(alert)

            send_email(
                subject=subject,
                html_body=html_body,
                text_body=text_body,
            )

            return True

async def alert_dispatcher_loop():
    while True:
        try:
            sent = await asyncio.to_thread(dispatch_alert_emails_once)
            if sent:
                print(f"[alert-dispatcher] sent {sent} email(s)")
        except Exception as e:
            print(f"[alert-dispatcher] error: {e}")

        await asyncio.sleep(ALERT_DISPATCH_INTERVAL_SECONDS)
