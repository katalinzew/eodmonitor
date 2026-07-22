import asyncio
import hmac
import io
import zipfile

from fastapi import APIRouter, Header, HTTPException, Query, Request

from app.core.config import API_KEY, MAX_LOG_ARCHIVE_BYTES
from app.repositories.log_collection_repository import (
    LOG_FILES,
    claim_log_collection,
    create_log_collection,
    finish_log_collection,
    get_log_collection,
    get_running_collection,
)
from app.schemas.log_collections import LogCollectionCreate, LogCollectionReport
from app.services.log_mail_service import send_log_archive_email

router = APIRouter()


def require_agent_key(value):
    if not hmac.compare_digest(value or "", API_KEY):
        raise HTTPException(status_code=401, detail="Invalid API key")


@router.post("/api/stores/{store_code}/log-collections", status_code=202)
def queue_log_collection(store_code: str, payload: LogCollectionCreate):
    return create_log_collection(store_code, payload)


@router.get("/api/stores/{store_code}/log-collections/{request_id}")
def log_collection_status(store_code: str, request_id: int):
    return get_log_collection(store_code, request_id)


@router.get("/api/agent-log-collections/next")
def next_log_collection(store_code: str = Query(...), x_api_key: str = Header(default=None)):
    require_agent_key(x_api_key)
    return {"request": claim_log_collection(store_code)}


@router.post("/api/agent-log-collections/report")
def report_log_collection(report: LogCollectionReport, x_api_key: str = Header(default=None)):
    require_agent_key(x_api_key)
    status = report.status.upper()
    return finish_log_collection(report.request_id, report.store_code, status, report.message or "")


@router.post("/api/agent-log-collections/{request_id}/upload")
async def upload_log_collection(
    request_id: int,
    request: Request,
    store_code: str = Query(...),
    x_api_key: str = Header(default=None),
):
    require_agent_key(x_api_key)
    selected_keys = get_running_collection(request_id, store_code)
    body = await request.body()
    if not body or len(body) > MAX_LOG_ARCHIVE_BYTES:
        finish_log_collection(request_id, store_code, "FAILED", "Archive is empty or exceeds size limit")
        raise HTTPException(status_code=413, detail="Archive is empty or exceeds size limit")

    expected_names = {LOG_FILES[key]["filename"] for key in selected_keys}
    try:
        with zipfile.ZipFile(io.BytesIO(body), "r") as archive:
            members = archive.infolist()
            names = [member.filename for member in members]
            if set(names) != expected_names or len(names) != len(expected_names):
                raise ValueError("Archive contents do not match requested logs")
            if any(member.is_dir() or member.file_size > MAX_LOG_ARCHIVE_BYTES for member in members):
                raise ValueError("Invalid archive member")
            if sum(member.file_size for member in members) > MAX_LOG_ARCHIVE_BYTES:
                raise ValueError("Uncompressed archive exceeds size limit")
            if archive.testzip() is not None:
                raise ValueError("Corrupt ZIP archive")
    except (KeyError, ValueError, zipfile.BadZipFile) as error:
        finish_log_collection(request_id, store_code, "FAILED", str(error))
        raise HTTPException(status_code=422, detail=str(error))

    archive_name = "logs_{}_{}.zip".format(store_code, request_id)
    labels = [LOG_FILES[key]["label"] for key in selected_keys]
    try:
        await asyncio.to_thread(send_log_archive_email, store_code, archive_name, body, labels)
    except Exception as error:
        finish_log_collection(request_id, store_code, "FAILED", "Email error: {}".format(error))
        raise HTTPException(status_code=502, detail="Email delivery failed")

    finish_log_collection(request_id, store_code, "SUCCEEDED", "Archive sent by email")
    return {"ok": True, "status": "SUCCEEDED"}
