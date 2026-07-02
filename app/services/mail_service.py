import smtplib
from email.message import EmailMessage

from app.core.config import SMTP_CONFIG


def send_email(subject: str, html_body: str, text_body: str = ""):
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = SMTP_CONFIG["from"]
    msg["To"] = ", ".join(SMTP_CONFIG["to"])

    msg.set_content(text_body or subject)
    msg.add_alternative(html_body, subtype="html")

    with smtplib.SMTP(SMTP_CONFIG["host"], SMTP_CONFIG["port"], timeout=20) as smtp:
        if SMTP_CONFIG.get("use_tls"):
            smtp.starttls()

        smtp.send_message(msg)