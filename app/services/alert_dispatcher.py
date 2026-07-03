import asyncio
import datetime as dt

from app.core.config import ALERT_DELAY_MINUTES
from app.core.database import get_conn
from app.repositories.alert_repository import (
    get_pending_email_alerts,
    mark_email_sent,
)
from app.services.mail_service import send_email


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

        return is_old_enough(first_seen_at, now)

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
        f"Alertă EOD Monitor\n\n"
        f"Magazin: {store_code} - {store_name}\n"
        f"Host: {host}\n"
        f"Tip alertă: {alert_type}\n"
        f"Target: {target}\n"
        f"Prima apariție: {first_seen_at}\n"
        f"Ultima confirmare: {last_seen_at}\n"
    )

    html_body = f"""
    <html>
        <body style="font-family: Arial, sans-serif; background:#f6f8fb; padding:20px;">
            <div style="max-width:720px; margin:auto; background:#ffffff; border-radius:12px; padding:24px; border:1px solid #e5e7eb;">
                <h2 style="margin-top:0; color:#111827;">EOD Monitor Alert</h2>

                <p style="font-size:15px; color:#374151;">
                    A fost detectată o problemă care persistă de cel puțin {ALERT_DELAY_MINUTES} minute.
                </p>

                <table style="width:100%; border-collapse:collapse; margin-top:18px;">
                    <tr>
                        <td style="padding:8px; border-bottom:1px solid #e5e7eb;"><b>Magazin</b></td>
                        <td style="padding:8px; border-bottom:1px solid #e5e7eb;">{store_code} - {store_name}</td>
                    </tr>
                    <tr>
                        <td style="padding:8px; border-bottom:1px solid #e5e7eb;"><b>Host</b></td>
                        <td style="padding:8px; border-bottom:1px solid #e5e7eb;">{host}</td>
                    </tr>
                    <tr>
                        <td style="padding:8px; border-bottom:1px solid #e5e7eb;"><b>Tip alertă</b></td>
                        <td style="padding:8px; border-bottom:1px solid #e5e7eb;">{alert_type}</td>
                    </tr>
                    <tr>
                        <td style="padding:8px; border-bottom:1px solid #e5e7eb;"><b>Target</b></td>
                        <td style="padding:8px; border-bottom:1px solid #e5e7eb;">{target}</td>
                    </tr>
                    <tr>
                        <td style="padding:8px; border-bottom:1px solid #e5e7eb;"><b>Prima apariție</b></td>
                        <td style="padding:8px; border-bottom:1px solid #e5e7eb;">{first_seen_at}</td>
                    </tr>
                    <tr>
                        <td style="padding:8px;"><b>Ultima confirmare</b></td>
                        <td style="padding:8px;">{last_seen_at}</td>
                    </tr>
                </table>

                <p style="font-size:12px; color:#6b7280; margin-top:22px;">
                    Email generat automat de EOD Monitor.
                </p>
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


async def alert_dispatcher_loop():
    while True:
        try:
            sent = dispatch_alert_emails_once()
            if sent:
                print(f"[alert-dispatcher] sent {sent} email(s)")
        except Exception as e:
            print(f"[alert-dispatcher] error: {e}")

        await asyncio.sleep(ALERT_DISPATCH_INTERVAL_SECONDS)