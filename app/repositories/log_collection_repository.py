import datetime as dt

from fastapi import HTTPException
from psycopg2.extras import Json

from app.core.config import LOG_COLLECTION_STORES, store_feature_enabled
from app.core.database import get_conn


LOG_FILES = {
    "meti_export": {"label": "METI Export", "filename": "meti_export.log"},
    "storepack": {"label": "StorePack", "filename": "storepack.log"},
    "trezor": {"label": "Trezor", "filename": "trezor.log"},
    "srvdemon": {"label": "Server daemon", "filename": "srvdemon.log"},
    "ars_daemon": {"label": "ArsPluMnt daemon", "filename": "daemon_ArsPluMnt.log"},
    "ars_general": {"label": "ArsPluMnt general", "filename": "general.log"},
}


def available_logs():
    return [{"key": key, **value} for key, value in LOG_FILES.items()]


def create_log_collection(store_code, payload):
    if not store_feature_enabled(store_code, LOG_COLLECTION_STORES):
        raise HTTPException(status_code=403, detail="Log collection is not enabled for this store")
    keys = list(dict.fromkeys(payload.log_keys))
    if not keys or any(key not in LOG_FILES for key in keys):
        raise HTTPException(status_code=422, detail="Select at least one allowed log")

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT active FROM stores WHERE store_code = %s", (store_code,))
            store = cur.fetchone()
            if store is None:
                raise HTTPException(status_code=404, detail="Store not found")
            if not store[0]:
                raise HTTPException(status_code=409, detail="Store is inactive")
            cur.execute(
                """
                INSERT INTO log_collection_requests (store_code, log_keys, status)
                VALUES (%s, %s, 'PENDING')
                RETURNING id, created_at
                """,
                (store_code, Json(keys)),
            )
            row = cur.fetchone()
    return {"id": row[0], "status": "PENDING", "created_at": row[1]}


def claim_log_collection(store_code):
    if not store_feature_enabled(store_code, LOG_COLLECTION_STORES):
        return None
    now = dt.datetime.now()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE log_collection_requests
                SET status = 'PENDING', started_at = NULL,
                    message = 'Automatically retried after agent timeout'
                WHERE store_code = %s AND status = 'RUNNING'
                  AND started_at < %s
                """,
                (store_code, now - dt.timedelta(minutes=10)),
            )
            cur.execute(
                """
                UPDATE log_collection_requests
                SET status = 'RUNNING', started_at = %s
                WHERE id = (
                    SELECT id FROM log_collection_requests
                    WHERE store_code = %s AND status = 'PENDING'
                    ORDER BY created_at, id
                    FOR UPDATE SKIP LOCKED
                    LIMIT 1
                )
                RETURNING id, log_keys
                """,
                (now, store_code),
            )
            row = cur.fetchone()
    return None if row is None else {"id": row[0], "log_keys": row[1] or []}


def get_running_collection(request_id, store_code):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT log_keys FROM log_collection_requests
                WHERE id = %s AND store_code = %s AND status = 'RUNNING'
                """,
                (request_id, store_code),
            )
            row = cur.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Running log collection not found")
    return row[0] or []


def finish_log_collection(request_id, store_code, status, message):
    if status not in {"SUCCEEDED", "FAILED"}:
        raise HTTPException(status_code=422, detail="Invalid collection status")
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE log_collection_requests
                SET status = %s, message = %s, finished_at = %s
                WHERE id = %s AND store_code = %s
                  AND status IN ('RUNNING', 'FAILED')
                RETURNING id
                """,
                (status, (message or "")[:2000], dt.datetime.now(), request_id, store_code),
            )
            if cur.fetchone() is None:
                raise HTTPException(status_code=404, detail="Log collection not found")
    return {"ok": True}


def get_log_collection(store_code, request_id):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, status, message, created_at, started_at, finished_at
                FROM log_collection_requests
                WHERE id = %s AND store_code = %s
                """,
                (request_id, store_code),
            )
            row = cur.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Log collection not found")
    return dict(zip(("id", "status", "message", "created_at", "started_at", "finished_at"), row))
