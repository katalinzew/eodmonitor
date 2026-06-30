import datetime as dt

from psycopg2.extras import Json
from fastapi import HTTPException

from app.core.database import get_conn
from app.services.status_service import calculate_ok_valid_until


def save_eod_history(cur, payload, received_at):
    if not payload.eod_date or not payload.eod_file:
        return

    cur.execute(
        """
        INSERT INTO eod_history (
            store_code,
            eod_date,
            status,
            eod_file,
            message,
            eod_file_created_at,
            received_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (store_code, eod_date, COALESCE(eod_file, ''))
        DO UPDATE SET
            status = EXCLUDED.status,
            message = EXCLUDED.message,
            eod_file_created_at = EXCLUDED.eod_file_created_at,
            received_at = EXCLUDED.received_at
        """,
        (
            payload.store_code,
            payload.eod_date,
            payload.status,
            payload.eod_file,
            payload.message,
            payload.eod_file_created_at,
            received_at,
        ),
    )


def insert_event(cur, store_code, event_type, old_value, new_value, message, created_at):
    cur.execute(
        """
        INSERT INTO event_log (
            store_code,
            event_type,
            old_value,
            new_value,
            message,
            created_at
        )
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (
            store_code,
            event_type,
            old_value,
            new_value,
            message,
            created_at,
        ),
    )


def save_status(payload):
    now = dt.datetime.now()

    ok_valid_until = calculate_ok_valid_until(
        payload.status,
        payload.eod_file,
        payload.eod_file_created_at,
    )

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT store_code
                FROM stores
                WHERE store_code = %s
                """,
                (payload.store_code,),
            )

            if cur.fetchone() is None:
                raise HTTPException(status_code=404, detail="Store not found in database")

            cur.execute(
                """
                SELECT status, COALESCE(heartbeat_state, 'ONLINE'), services_status
                FROM current_status
                WHERE store_code = %s
                """,
                (payload.store_code,),
            )

            old_row = cur.fetchone()
            old_status = None
            old_heartbeat_state = "ONLINE"

            if old_row:
                old_status = old_row[0]
                old_heartbeat_state = old_row[1]

            if old_heartbeat_state == "OFFLINE":
                insert_event(
                    cur,
                    payload.store_code,
                    "HEARTBEAT_ONLINE",
                    "OFFLINE",
                    "ONLINE",
                    "Agentul a revenit online.",
                    now,
                )

            if payload.schedule_time:
                cur.execute(
                    """
                    UPDATE stores
                    SET schedule_time = %s,
                        updated_at = %s
                    WHERE store_code = %s
                    """,
                    (
                        payload.schedule_time,
                        now,
                        payload.store_code,
                    ),
                )

            cur.execute(
                """
                INSERT INTO current_status (
                    store_code,
                    status,
                    eod_file,
                    message,
                    eod_date,
                    eod_file_created_at,
                    last_heartbeat,
                    updated_at,

                    hostname,
                    agent_version,
                    os_info,
                    uptime_seconds,

                    cpu_load_1m,

                    ram_total_mb,
                    ram_used_mb,
                    ram_percent,

                    disk_total_gb,
                    disk_used_gb,
                    disk_percent,

                    ok_valid_until,
                    last_ok_eod_file,
                    last_ok_eod_date,
                    last_ok_message,
                    heartbeat_state,
                    services_status
                )
                VALUES (
                    %s,%s,%s,%s,%s,%s,
                    %s,%s,
                    %s,%s,%s,%s,
                    %s,
                    %s,%s,%s,
                    %s,%s,%s,
                    %s,
                    %s,%s,%s,
                    %s,
                    %s
                )
                ON CONFLICT (store_code)
                DO UPDATE SET
                    status = EXCLUDED.status,
                    eod_file = EXCLUDED.eod_file,
                    message = EXCLUDED.message,
                    eod_date = EXCLUDED.eod_date,
                    eod_file_created_at = EXCLUDED.eod_file_created_at,
                    last_heartbeat = EXCLUDED.last_heartbeat,
                    updated_at = EXCLUDED.updated_at,

                    hostname = EXCLUDED.hostname,
                    agent_version = EXCLUDED.agent_version,
                    os_info = EXCLUDED.os_info,
                    uptime_seconds = EXCLUDED.uptime_seconds,
                    cpu_load_1m = EXCLUDED.cpu_load_1m,

                    ram_total_mb = EXCLUDED.ram_total_mb,
                    ram_used_mb = EXCLUDED.ram_used_mb,
                    ram_percent = EXCLUDED.ram_percent,

                    disk_total_gb = EXCLUDED.disk_total_gb,
                    disk_used_gb = EXCLUDED.disk_used_gb,
                    disk_percent = EXCLUDED.disk_percent,

                    heartbeat_state = 'ONLINE',
                    services_status = EXCLUDED.services_status,

                    ok_valid_until = CASE
                        WHEN EXCLUDED.status = 'OK'
                        THEN EXCLUDED.ok_valid_until
                        ELSE current_status.ok_valid_until
                    END,

                    last_ok_eod_file = CASE
                        WHEN EXCLUDED.status = 'OK'
                        THEN EXCLUDED.eod_file
                        ELSE current_status.last_ok_eod_file
                    END,

                    last_ok_eod_date = CASE
                        WHEN EXCLUDED.status = 'OK'
                        THEN EXCLUDED.eod_date
                        ELSE current_status.last_ok_eod_date
                    END,

                    last_ok_message = CASE
                        WHEN EXCLUDED.status = 'OK'
                        THEN EXCLUDED.message
                        ELSE current_status.last_ok_message
                    END
                """,
                (
                    payload.store_code,
                    payload.status,
                    payload.eod_file,
                    payload.message,
                    payload.eod_date,
                    payload.eod_file_created_at,

                    now,
                    now,

                    payload.hostname,
                    payload.agent_version,
                    payload.os_info,
                    payload.uptime_seconds,

                    payload.cpu_load_1m,

                    payload.ram_total_mb,
                    payload.ram_used_mb,
                    payload.ram_percent,

                    payload.disk_total_gb,
                    payload.disk_used_gb,
                    payload.disk_percent,

                    ok_valid_until,

                    payload.eod_file if payload.status == "OK" else None,
                    payload.eod_date if payload.status == "OK" else None,
                    payload.message if payload.status == "OK" else None,

                    "ONLINE",
                    Json(payload.services_status or {}),
                ),
            )

            save_eod_history(cur, payload, now)

            if old_status != payload.status:
                if not (old_status == "OK" and payload.status == "MISSING"):
                    insert_event(
                        cur,
                        payload.store_code,
                        "STATUS_CHANGE",
                        old_status,
                        payload.status,
                        f"Status EOD schimbat: {old_status} -> {payload.status}",
                        now,
                    )

    return {
        "ok": True,
        "store_code": payload.store_code,
        "saved_at": now.isoformat(),
        "ok_valid_until": ok_valid_until.isoformat() if ok_valid_until else None,
    }