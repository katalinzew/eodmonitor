from app.services.mail_service import send_email


def send_test_email():
    send_email(
        subject="[EOD Monitor] Test mail",
        text_body="Test mail EOD Monitor.",
        html_body="""
        <html>
            <body style="font-family: Arial, sans-serif;">
                <h2>EOD Monitor - Test mail</h2>
                <p>Dacă vezi acest email, configurarea SMTP funcționează.</p>
            </body>
        </html>
        """,
    )