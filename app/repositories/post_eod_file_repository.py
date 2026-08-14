from psycopg2.extras import Json

from app.repositories.alert_repository import upsert_active_alert
from app.services.post_eod_file_service import (
    POST_EOD_ALERT_TYPE,
    build_post_eod_alert_target,
    evaluate_post_eod_files,
    get_post_eod_email_due_at,
    parse_eod_date,
    should_run_post_eod_check,
)
from app.services.status_service import parse_datetime


def post_eod_check_exists(cur, store_code, eod_date):
    cur.execute(
        """
        SELECT 1
        FROM post_eod_file_checks
        WHERE store_code = %s
          AND eod_date = %s
        LIMIT 1
        """,
        (store_code, eod_date),
    )
    return cur.fetchone() is not None


def process_post_eod_file_check(cur, payload, now):
    if not should_run_post_eod_check(
        payload.status,
        payload.eod_date,
        payload.eod_file_created_at,
        payload.post_eod_files,
        now,
    ):
        return None

    business_date = parse_eod_date(payload.eod_date)
    if post_eod_check_exists(cur, payload.store_code, business_date):
        return None

    result = evaluate_post_eod_files(payload.post_eod_files, business_date)
    alert_id = None
    email_due_at = None

    if not result["passed"]:
        alert_id = upsert_active_alert(
            cur,
            payload.store_code,
            POST_EOD_ALERT_TYPE,
            build_post_eod_alert_target(business_date),
            now,
        )
        email_due_at = get_post_eod_email_due_at(business_date)

    cur.execute(
        """
        INSERT INTO post_eod_file_checks (
            store_code,
            eod_date,
            eod_completed_at,
            checked_at,
            result,
            passed,
            details,
            alert_id,
            email_due_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (store_code, eod_date) DO NOTHING
        """,
        (
            payload.store_code,
            business_date,
            parse_datetime(payload.eod_file_created_at),
            now,
            Json(result),
            result["passed"],
            result["details"],
            alert_id,
            email_due_at,
        ),
    )

    return result
