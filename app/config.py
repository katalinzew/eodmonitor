import datetime as dt

API_KEY = "test123"
OFFLINE_AFTER_MINUTES = 5
OK_VALID_HOURS = 10
LATE_GRACE_MINUTES = 30
ALERT_DELAY_MINUTES = 5
API_STARTED_AT = dt.datetime.now()

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