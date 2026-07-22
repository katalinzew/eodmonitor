from app.services.mail_service import send_email


def send_log_archive_email(store_code, archive_name, archive_bytes, selected_labels):
    labels = ", ".join(selected_labels)
    subject = "[EOD Monitor] Logs magazin {}".format(store_code)
    send_email(
        subject=subject,
        text_body="Loguri colectate pentru magazinul {}: {}".format(store_code, labels),
        html_body=(
            "<html><body style='font-family:Arial,sans-serif'>"
            "<h2>EOD Monitor - Logs magazin {}</h2>"
            "<p>Arhiva atașată conține: {}.</p>"
            "</body></html>"
        ).format(store_code, labels),
        attachments=[{
            "content": archive_bytes,
            "filename": archive_name,
            "maintype": "application",
            "subtype": "zip",
        }],
    )
