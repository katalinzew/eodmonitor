import hmac

from fastapi import APIRouter, Header, HTTPException, Query

from app.core.config import API_KEY
from app.repositories.agent_command_repository import (
    claim_next_command,
    create_service_command,
    save_command_report,
)
from app.schemas.agent_commands import ServiceCommandCreate, ServiceCommandReport

router = APIRouter()


def require_agent_key(value):
    if not hmac.compare_digest(value or "", API_KEY):
        raise HTTPException(status_code=401, detail="Invalid API key")


@router.post("/api/stores/{store_code}/service-commands", status_code=202)
def queue_service_command(store_code: str, payload: ServiceCommandCreate):
    return create_service_command(store_code, payload)


@router.get("/api/agent-commands/next")
def next_agent_command(store_code: str = Query(...), x_api_key: str = Header(default=None)):
    require_agent_key(x_api_key)
    return {"command": claim_next_command(store_code)}


@router.post("/api/agent-commands/report")
def report_agent_command(report: ServiceCommandReport, x_api_key: str = Header(default=None)):
    require_agent_key(x_api_key)
    return save_command_report(report)
