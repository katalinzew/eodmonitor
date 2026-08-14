import datetime as dt
import re

from app.services.status_service import parse_datetime


POST_EOD_ALERT_TYPE = "POST_EOD_FILES_MISSING"
POST_EOD_CHECK_DELAY_MINUTES = 5
POST_EOD_EMAIL_HOUR = 6

FDN_FILE = "fdn_mdp"
EXISTENCE_ONLY_FILES = ("vteplu", "vtesf")


def parse_eod_date(value):
    if isinstance(value, dt.date) and not isinstance(value, dt.datetime):
        return value

    try:
        return dt.datetime.strptime(str(value), "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def get_post_eod_check_due_at(eod_completed_at):
    completed_at = parse_datetime(eod_completed_at)
    if not completed_at:
        return None

    return completed_at + dt.timedelta(minutes=POST_EOD_CHECK_DELAY_MINUTES)


def get_post_eod_email_due_at(eod_date):
    business_date = parse_eod_date(eod_date)
    if not business_date:
        return None

    return dt.datetime.combine(
        business_date + dt.timedelta(days=1),
        dt.time(hour=POST_EOD_EMAIL_HOUR),
    )


def should_run_post_eod_check(status, eod_date, eod_completed_at, reported_files, now):
    if status != "OK" or reported_files is None:
        return False

    if not parse_eod_date(eod_date):
        return False

    due_at = get_post_eod_check_due_at(eod_completed_at)
    return bool(due_at and now >= due_at)


def _file_entry(reported_files, name):
    if not isinstance(reported_files, dict):
        return {}

    entry = reported_files.get(name)
    return entry if isinstance(entry, dict) else {}


def evaluate_post_eod_files(reported_files, eod_date):
    business_date = parse_eod_date(eod_date)
    if not business_date:
        raise ValueError("Invalid EOD business date")

    expected_prefix = business_date.strftime("%d%m%y")
    problems = []

    fdn_entry = _file_entry(reported_files, FDN_FILE)
    fdn_exists = fdn_entry.get("exists") is True
    fdn_prefix = fdn_entry.get("date_prefix")
    fdn_prefix = str(fdn_prefix).strip() if fdn_prefix is not None else ""

    if not fdn_exists:
        problems.append("fdn_mdp lipseste")
    elif not re.match(r"^[0-9]{6}$", fdn_prefix):
        problems.append("fdn_mdp nu contine o data DDMMYY valida")
    elif fdn_prefix != expected_prefix:
        problems.append(
            "fdn_mdp are data {0}, asteptat {1}".format(
                fdn_prefix,
                expected_prefix,
            )
        )

    file_results = {
        FDN_FILE: {
            "exists": fdn_exists,
            "date_prefix": fdn_prefix or None,
            "expected_date_prefix": expected_prefix,
        }
    }

    for name in EXISTENCE_ONLY_FILES:
        exists = _file_entry(reported_files, name).get("exists") is True
        file_results[name] = {"exists": exists}
        if not exists:
            problems.append("{0} lipseste".format(name))

    return {
        "passed": not problems,
        "business_date": business_date.isoformat(),
        "files": file_results,
        "problems": problems,
        "details": "; ".join(problems) if problems else "Toate fisierele sunt valide",
    }


def build_post_eod_alert_target(eod_date):
    business_date = parse_eod_date(eod_date)
    if not business_date:
        raise ValueError("Invalid EOD business date")

    return "EOD {0}".format(business_date.isoformat())
