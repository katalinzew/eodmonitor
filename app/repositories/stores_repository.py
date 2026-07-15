import datetime as dt

from fastapi import HTTPException
from psycopg2 import IntegrityError

from app.core.database import get_conn
from app.repositories.dashboard_repository import rows_to_dicts


def ensure_store_exists(cur, store_code):
    cur.execute(
        """
        SELECT store_code
        FROM stores
        WHERE store_code = %s
        """,
        (store_code,),
    )

    return cur.fetchone() is not None


def update_store_schedule(cur, store_code, schedule_time, updated_at):
    if not schedule_time:
        return

    cur.execute(
        """
        UPDATE stores
        SET schedule_time = %s,
            updated_at = %s
        WHERE store_code = %s
        """,
        (
            schedule_time,
            updated_at,
            store_code,
        ),
    )


def list_stores():
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    s.store_code,
                    s.store_name,
                    s.host,
                    cs.hostname,
                    s.schedule_time,
                    s.active,
                    s.created_at,
                    s.updated_at
                FROM stores s
                LEFT JOIN current_status cs ON cs.store_code = s.store_code
                ORDER BY s.store_code
                """
            )
            columns = [desc[0] for desc in cur.description]
            return rows_to_dicts(columns, cur.fetchall())


def create_store(payload):
    now = dt.datetime.now()
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO stores (
                        store_code, store_name, host, schedule_time,
                        active, created_at, updated_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        payload.store_code,
                        payload.store_name,
                        payload.host,
                        payload.schedule_time,
                        payload.active,
                        now,
                        now,
                    ),
                )
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="Store code already exists") from exc

    return {"ok": True, "store_code": payload.store_code}


def update_store(store_code, payload):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE stores
                SET store_name = %s,
                    host = %s,
                    schedule_time = %s,
                    active = %s,
                    updated_at = %s
                WHERE store_code = %s
                """,
                (
                    payload.store_name,
                    payload.host,
                    payload.schedule_time,
                    payload.active,
                    dt.datetime.now(),
                    store_code,
                ),
            )
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail="Store not found")

    return {"ok": True, "store_code": store_code}


def set_store_active(store_code, active):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE stores
                SET active = %s,
                    updated_at = %s
                WHERE store_code = %s
                """,
                (active, dt.datetime.now(), store_code),
            )
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail="Store not found")

    return {"ok": True, "store_code": store_code, "active": active}
