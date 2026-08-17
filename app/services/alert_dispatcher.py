import asyncio
import datetime as dt
from html import escape

from app.core.config import ALERT_DELAY_MINUTES, POST_EOD_FILE_CHECKS_ENABLED
from app.core.database import get_conn
from app.repositories.alert_repository import (
    get_pending_email_alerts,
    get_pending_post_eod_email_alerts,
    mark_email_sent,
    mark_email_sent_and_resolve,
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


def build_post_eod_alert_email(alert):
    (
        alert_id,
        store_code,
        store_name,
        host,
        alert_type,
        target,
        first_seen_at,
        last_seen_at,
        email_sent,
        resolved,
        resolved_at,
        eod_date,
        checked_at,
        details,
        email_due_at,
    ) = alert

    store_label = "{0} - {1}".format(store_code, store_name or "-")
    state_label = "Rezolvată" if resolved else "Activă la ora trimiterii"
    state_detail = (
        "Rezolvată la {0}".format(resolved_at)
        if resolved and resolved_at
        else "Problema detectată era încă activă la pregătirea emailului"
    )
    subject = "[EOD Monitor] Fișiere de vânzări - {0} - EOD {1}".format(
        store_code,
        eod_date,
    )

    text_body = (
        "EOD Monitor - Verificare fișiere de vânzări\n\n"
        "Magazin: {0}\n"
        "Host: {1}\n"
        "Data EOD: {2}\n"
        "Verificat la: {3}\n"
        "Probleme: {4}\n"
        "Status la trimiterea emailului: {5}\n"
        "{6}\n"
    ).format(
        store_label,
        host or "-",
        eod_date,
        checked_at,
        details,
        state_label,
        state_detail,
    )

    html_body = """
    <html>
    <body style="margin:0;padding:0;background:#070b14;font-family:Arial,sans-serif;color:#e5eefb;">
        <div style="max-width:640px;margin:0 auto;padding:18px;background:#07111f;">
            <div style="background:#0f172a;border:1px solid #263247;border-radius:18px;overflow:hidden;">
                <div style="padding:18px 22px;border-bottom:1px solid #263247;">
                    <div style="font-size:22px;font-weight:900;color:#ffffff;">EOD Monitor</div>
                    <div style="font-size:13px;color:#94a3b8;margin-top:3px;">Verificare fișiere de vânzări</div>
                </div>
                <div style="padding:22px;">
                    <div style="display:inline-block;padding:6px 11px;border-radius:999px;background:#3b1620;border:1px solid #7f1d2d;color:#fecaca;font-size:11px;font-weight:900;">
                        PROBLEMĂ DETECTATĂ DUPĂ EOD
                    </div>
                    <h2 style="margin:16px 0 6px;font-size:22px;color:#ffffff;">Magazin {store_code}</h2>
                    <p style="margin:0 0 18px;color:#cbd5e1;font-size:14px;">
                        Validarea fișierelor de vânzări a eșuat la 5 minute după finalizarea EOD.
                    </p>
                    <table style="width:100%;border-collapse:collapse;background:#080f1f;border:1px solid #263247;font-size:13px;">
                        <tr><td style="padding:11px 13px;color:#94a3b8;border-bottom:1px solid #263247;width:38%;">Magazin</td><td style="padding:11px 13px;color:#ffffff;font-weight:800;border-bottom:1px solid #263247;">{store_label}</td></tr>
                        <tr><td style="padding:11px 13px;color:#94a3b8;border-bottom:1px solid #263247;">Host</td><td style="padding:11px 13px;color:#e0f2fe;font-weight:800;border-bottom:1px solid #263247;">{host}</td></tr>
                        <tr><td style="padding:11px 13px;color:#94a3b8;border-bottom:1px solid #263247;">Data EOD</td><td style="padding:11px 13px;color:#ffffff;font-weight:800;border-bottom:1px solid #263247;">{eod_date}</td></tr>
                        <tr><td style="padding:11px 13px;color:#94a3b8;border-bottom:1px solid #263247;">Verificat la</td><td style="padding:11px 13px;color:#ffffff;font-weight:800;border-bottom:1px solid #263247;">{checked_at}</td></tr>
                        <tr><td style="padding:11px 13px;color:#94a3b8;border-bottom:1px solid #263247;">Probleme</td><td style="padding:11px 13px;color:#fecaca;font-weight:900;border-bottom:1px solid #263247;">{details}</td></tr>
                        <tr><td style="padding:11px 13px;color:#94a3b8;">Status</td><td style="padding:11px 13px;color:#ffffff;font-weight:800;">{state_label}</td></tr>
                    </table>
                    <div style="margin-top:16px;padding:12px 14px;border-radius:14px;background:#0c2c3b;border:1px solid #155e75;color:#bae6fd;font-size:12px;">
                        Acest email raportează problema detectată după EOD. Alerta este închisă automat după trimiterea reușită a emailului.
                    </div>
                </div>
            </div>
        </div>
    </body>
    </html>
    """.format(
        store_code=escape(str(store_code)),
        store_label=escape(store_label),
        host=escape(str(host or "-")),
        eod_date=escape(str(eod_date)),
        checked_at=escape(str(checked_at)),
        details=escape(str(details or "-")),
        state_label=escape(state_label),
    )

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

    if POST_EOD_FILE_CHECKS_ENABLED:
        with get_conn() as conn:
            with conn.cursor() as cur:
                post_eod_alerts = get_pending_post_eod_email_alerts(cur, now)

                for alert in post_eod_alerts:
                    alert_id = alert[0]
                    subject, html_body, text_body = build_post_eod_alert_email(alert)

                    send_email(
                        subject=subject,
                        html_body=html_body,
                        text_body=text_body,
                    )

                    mark_email_sent_and_resolve(cur, alert_id, now)
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
