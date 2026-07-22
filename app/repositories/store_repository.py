from fastapi import HTTPException

from app.core.config import (
    LATE_GRACE_MINUTES,
    LOG_COLLECTION_STORES,
    OFFLINE_AFTER_MINUTES,
    SERVICE_CONTROL_STORES,
)
from app.core.database import get_conn
from app.repositories.dashboard_repository import DASHBOARD_SQL, rows_to_dicts
from app.repositories.log_collection_repository import available_logs


def get_store_details(store_code: str):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                WITH dashboard AS (
            """
                + DASHBOARD_SQL
                + """
                )
                SELECT *
                FROM dashboard
                WHERE store_code = %s
                LIMIT 1
                """,
                (
                    OFFLINE_AFTER_MINUTES,
                    LATE_GRACE_MINUTES,
                    store_code,
                ),
            )

            cols = [desc[0] for desc in cur.description]
            row = cur.fetchone()

            if row is None:
                raise HTTPException(status_code=404, detail="Store not found")

            store = rows_to_dicts(cols, [row])[0]

            cur.execute(
                """
                SELECT
                    e.id,
                    e.store_code,
                    s.store_name,
                    e.event_type,
                    e.old_value,
                    e.new_value,
                    e.message,
                    e.created_at
                FROM event_log e
                LEFT JOIN stores s
                    ON e.store_code = s.store_code
                WHERE e.store_code = %s
                  AND NOT (
                      e.event_type = 'STATUS_CHANGE'
                      AND e.old_value = 'OK'
                      AND e.new_value = 'MISSING'
                  )
                ORDER BY e.id DESC
                LIMIT 100
                """,
                (store_code,),
            )

            event_cols = [desc[0] for desc in cur.description]
            event_rows = cur.fetchall()
            events = rows_to_dicts(event_cols, event_rows)

            cur.execute(
                """
                SELECT
                    id,
                    store_code,
                    eod_date,
                    status,
                    eod_file,
                    message,
                    eod_file_created_at,
                    received_at
                FROM eod_history
                WHERE store_code = %s
                ORDER BY received_at DESC
                LIMIT 30
                """,
                (store_code,),
            )

            eod_cols = [desc[0] for desc in cur.description]
            eod_rows = cur.fetchall()
            eod_history = rows_to_dicts(eod_cols, eod_rows)

    return {
        "store": store,
        "events": events,
        "eod_history": eod_history,
        "service_control_enabled": store_code in SERVICE_CONTROL_STORES,
        "log_collection_enabled": store_code in LOG_COLLECTION_STORES,
        "available_logs": available_logs() if store_code in LOG_COLLECTION_STORES else [],
    }
