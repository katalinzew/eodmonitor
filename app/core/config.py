import datetime as dt
import os

API_KEY = os.getenv("EOD_API_KEY", "test123")
SERVICE_CONTROL_STORES = {
    code.strip()
    for code in os.getenv("EOD_SERVICE_CONTROL_STORES", "5034").split(",")
    if code.strip()
}
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
AGENT_PACKAGES_DIR = os.getenv(
    "EOD_AGENT_PACKAGES_DIR",
    os.path.join(PROJECT_ROOT, "agent_packages"),
)
OFFLINE_AFTER_MINUTES = 5
OK_VALID_HOURS = 10
LATE_GRACE_MINUTES = 30
ALERT_DELAY_MINUTES = 5
API_STARTED_AT = dt.datetime.now()
OFFLINE_CHECK_INTERVAL_SECONDS = 60

DB_CONFIG = {
    "host": "127.0.0.1",
    "port": 5432,
    "dbname": "eod_monitor",
    "user": "postgres",
    "password": "1407",
}

SMTP_CONFIG = {
    "host": "remote.smartid.ro",
    "port": 62625,
    "use_tls": True,
    "from": "eod-monitor@smartid.ro",
    "to": [
        "SupportSoftware@smartid.ro",
        "Valentin.SURUGIU@smartid.ro",
    ],
}
