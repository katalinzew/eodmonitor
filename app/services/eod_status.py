import datetime as dt

from app.config import OK_VALID_HOURS


def calculate_ok_valid_until(status: str, eod_file: str, eod_file_created_at: str):
    if status != "OK":
        return None

    if not eod_file or not eod_file_created_at:
        return None

    try:
        eod_file_dt = dt.datetime.strptime(
            eod_file_created_at,
            "%Y-%m-%d %H:%M:%S",
        )
        return eod_file_dt + dt.timedelta(hours=OK_VALID_HOURS)
    except Exception:
        return dt.datetime.now() + dt.timedelta(hours=OK_VALID_HOURS)


def is_effective_ok(status, ok_valid_until, now=None):
    if now is None:
        now = dt.datetime.now()

    if status == "OK":
        return True

    if status in ("MISSING", "PROBLEM") and ok_valid_until and ok_valid_until > now:
        return True

    return False


def eod_ttl_message():
    return f"OK validat anterior - valabil {OK_VALID_HOURS} ore"