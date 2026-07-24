import datetime as dt

from fastapi import HTTPException

from app.core.config import SERVICE_CONTROL_STORES, store_feature_enabled
from app.core.database import get_conn


ALLOWED_SERVICES = {
    "sidMETIEXPORT.service",
    "sidStorePack.service",
    "sidTrezor.service",
    "idcreader.service",
}
ALLOWED_ACTIONS = {"start", "stop", "restart"}


def create_service_command(store_code, payload):
    if not store_feature_enabled(store_code, SERVICE_CONTROL_STORES):
        raise HTTPException(status_code=403, detail="Service control is not enabled for this store")
    if payload.service_name not in ALLOWED_SERVICES:
        raise HTTPException(status_code=422, detail="Service is not allowed")
    action = payload.action.lower()
    if action not in ALLOWED_ACTIONS:
        raise HTTPException(status_code=422, detail="Action is not allowed")

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
                INSERT INTO agent_commands (store_code, service_name, action, status)
                VALUES (%s, %s, %s, 'PENDING')
                RETURNING id, created_at
                """,
                (store_code, payload.service_name, action),
            )
            row = cur.fetchone()
    return {"id": row[0], "status": "PENDING", "created_at": row[1]}


def claim_next_command(store_code):
    if not store_feature_enabled(store_code, SERVICE_CONTROL_STORES):
        return None
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE agent_commands
                SET status = 'PENDING', started_at = NULL,
                    message = 'Automatically retried after agent timeout'
                WHERE store_code = %s AND status = 'RUNNING'
                  AND started_at < %s
                """,
                (store_code, dt.datetime.now() - dt.timedelta(minutes=5)),
            )
            cur.execute(
                """
                UPDATE agent_commands
                SET status = 'RUNNING', started_at = %s
                WHERE id = (
                    SELECT id FROM agent_commands
                    WHERE store_code = %s AND status = 'PENDING'
                    ORDER BY created_at, id
                    FOR UPDATE SKIP LOCKED
                    LIMIT 1
                )
                RETURNING id, service_name, action
                """,
                (dt.datetime.now(), store_code),
            )
            row = cur.fetchone()
    if row is None:
        return None
    return {"id": row[0], "service_name": row[1], "action": row[2]}


def save_command_report(report):
    status = report.status.upper()
    if status not in {"SUCCEEDED", "FAILED"}:
        raise HTTPException(status_code=422, detail="Invalid command status")
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE agent_commands
                SET status = %s, message = %s, finished_at = %s
                WHERE id = %s AND store_code = %s AND status = 'RUNNING'
                RETURNING id
                """,
                (status, (report.message or "")[:2000], dt.datetime.now(), report.command_id, report.store_code),
            )
            if cur.fetchone() is None:
                raise HTTPException(status_code=404, detail="Running command not found")
    return {"ok": True}
