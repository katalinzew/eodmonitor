import datetime as dt

from fastapi import HTTPException

from app.core.database import get_conn


def get_active_release(store_code):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT active
                FROM stores
                WHERE store_code = %s
                """,
                (store_code,),
            )
            store = cur.fetchone()
            if store is None:
                raise HTTPException(status_code=404, detail="Store not found")
            if not store[0]:
                return None

            cur.execute(
                """
                SELECT id, version, manifest
                FROM agent_releases
                WHERE active = TRUE
                ORDER BY created_at DESC, id DESC
                LIMIT 1
                """
            )
            row = cur.fetchone()
            if row is None:
                return None
            return {"id": row[0], "version": row[1], "manifest": row[2]}


def get_release_file(release_id, component):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT version, manifest
                FROM agent_releases
                WHERE id = %s AND active = TRUE
                """,
                (release_id,),
            )
            row = cur.fetchone()
            if row is None:
                raise HTTPException(status_code=404, detail="Release not found")

    manifest = row[1] or {}
    files = manifest.get("files") or []
    file_entry = next((item for item in files if item.get("component") == component), None)
    if file_entry is None:
        raise HTTPException(status_code=404, detail="Component not found")
    return row[0], file_entry


def save_deployment_report(report):
    allowed_statuses = {"DOWNLOADING", "INSTALLED", "FAILED", "ROLLED_BACK"}
    if report.status not in allowed_statuses:
        raise HTTPException(status_code=422, detail="Invalid deployment status")

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO agent_deployments (
                    release_id, store_code, status, message,
                    current_version, updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (release_id, store_code)
                DO UPDATE SET
                    status = EXCLUDED.status,
                    message = EXCLUDED.message,
                    current_version = EXCLUDED.current_version,
                    updated_at = EXCLUDED.updated_at
                """,
                (
                    report.release_id,
                    report.store_code,
                    report.status,
                    report.message[:2000],
                    report.current_version,
                    dt.datetime.now(),
                ),
            )
    return {"ok": True}
