import datetime as dt

from app.core.config import OK_VALID_HOURS, OFFLINE_AFTER_MINUTES


def parse_datetime(value):
    if not value:
        return None

    if isinstance(value, dt.datetime):
        return value

    try:
        return dt.datetime.fromisoformat(str(value))
    except Exception:
        return None


def calculate_ok_valid_until(status, eod_file, eod_file_created_at):
    if status != "OK":
        return None

    if not eod_file or not eod_file_created_at:
        return None

    file_dt = parse_datetime(eod_file_created_at)

    if not file_dt:
        file_dt = dt.datetime.now()

    return file_dt + dt.timedelta(hours=OK_VALID_HOURS)


def get_eod_alert_due_at(schedule_time, now=None):
    if now is None:
        now = dt.datetime.now()

    if not schedule_time:
        return None

    try:
        schedule = dt.datetime.strptime(str(schedule_time), "%H:%M").time()
    except (TypeError, ValueError):
        return None

    return dt.datetime.combine(now.date(), schedule)


def is_eod_alert_due(schedule_time, now=None):
    if now is None:
        now = dt.datetime.now()

    due_at = get_eod_alert_due_at(schedule_time, now)
    return due_at is None or now >= due_at


def is_eod_ttl_valid(ok_valid_until, now=None):
    if now is None:
        now = dt.datetime.now()

    valid_until = parse_datetime(ok_valid_until)

    return bool(valid_until and valid_until > now)


def get_effective_eod_status(raw_status, ok_valid_until, now=None):
    """
    Statusul efectiv pentru dashboard.

    Regula importantă:
    Dacă statusul brut devine MISSING/PROBLEM, dar ultimul OK este încă în TTL,
    magazinul rămâne OK vizual.
    """

    if now is None:
        now = dt.datetime.now()

    if raw_status == "OK":
        return "OK"

    if raw_status in ("MISSING", "PROBLEM") and is_eod_ttl_valid(ok_valid_until, now):
        return "OK"

    return raw_status or "NO_DATA"


def get_heartbeat_status(last_heartbeat, now=None):
    if now is None:
        now = dt.datetime.now()

    heartbeat_dt = parse_datetime(last_heartbeat)

    if not heartbeat_dt:
        return "NO_DATA"

    if heartbeat_dt < now - dt.timedelta(minutes=OFFLINE_AFTER_MINUTES):
        return "OFFLINE"

    return "ONLINE"


def get_overall_status(raw_status, ok_valid_until, last_heartbeat, now=None):
    """
    Status final pentru afișare.

    Agent offline are prioritate pentru overall status,
    dar EOD-ul poate fi în continuare valid separat.
    """

    if now is None:
        now = dt.datetime.now()

    heartbeat_status = get_heartbeat_status(last_heartbeat, now)

    if heartbeat_status == "OFFLINE":
        return "OFFLINE"

    if heartbeat_status == "NO_DATA":
        return "NO_DATA"

    return get_effective_eod_status(raw_status, ok_valid_until, now)


def should_hide_status_event(event_type, old_value, new_value, ok_valid_until=None, now=None):
    """
    Ascunde evenimente zgomotoase din timeline.

    Exemplu:
    OK -> MISSING după miezul nopții nu este problemă dacă TTL-ul este încă valid.
    """

    if now is None:
        now = dt.datetime.now()

    if event_type == "STATUS_CHANGE" and old_value == "OK" and new_value == "MISSING":
        if ok_valid_until is None:
            return True

        return is_eod_ttl_valid(ok_valid_until, now)

    return False


def ttl_message():
    return f"OK validat anterior - valabil {OK_VALID_HOURS} ore"
