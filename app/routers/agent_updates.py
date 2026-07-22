import hashlib
import hmac
import json
import os

from fastapi import APIRouter, Header, HTTPException, Query
from fastapi.responses import FileResponse

from app.core.config import AGENT_PACKAGES_DIR, API_KEY
from app.repositories.agent_update_repository import (
    get_active_release,
    get_release_file,
    save_deployment_report,
)
from app.schemas.agent_updates import DeploymentReport

router = APIRouter()


def require_agent_key(x_api_key):
    if not hmac.compare_digest(x_api_key or "", API_KEY):
        raise HTTPException(status_code=401, detail="Invalid API key")


def sign_manifest(payload):
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hmac.new(API_KEY.encode("utf-8"), canonical, hashlib.sha256).hexdigest()


@router.get("/api/agent-updates/latest")
def latest_agent_update(
    store_code: str = Query(...),
    current_version: str = Query(default=""),
    x_api_key: str = Header(default=None),
):
    require_agent_key(x_api_key)
    release = get_active_release(store_code)
    if release is None or release["version"] == current_version:
        return {"update_available": False}

    payload = {
        "update_available": True,
        "release_id": release["id"],
        "version": release["version"],
        "files": release["manifest"].get("files") or [],
    }
    payload["signature"] = sign_manifest(payload)
    return payload


@router.get("/api/agent-updates/files/{release_id}/{component}")
def download_agent_component(
    release_id: int,
    component: str,
    x_api_key: str = Header(default=None),
):
    require_agent_key(x_api_key)
    version, file_entry = get_release_file(release_id, component)
    safe_component = os.path.basename(file_entry["source"])
    file_path = os.path.abspath(os.path.join(AGENT_PACKAGES_DIR, version, safe_component))
    release_root = os.path.abspath(os.path.join(AGENT_PACKAGES_DIR, version))
    if os.path.commonpath([release_root, file_path]) != release_root or not os.path.isfile(file_path):
        raise HTTPException(status_code=404, detail="Release file not found")
    return FileResponse(file_path, filename=safe_component)


@router.post("/api/agent-updates/report")
def report_agent_update(
    report: DeploymentReport,
    x_api_key: str = Header(default=None),
):
    require_agent_key(x_api_key)
    return save_deployment_report(report)
