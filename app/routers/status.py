from fastapi import APIRouter, Header, HTTPException

from app.core.config import API_KEY
from app.schemas.status import StatusPayload
from app.repositories.status_repository import save_status

router = APIRouter()


@router.post("/api/status")
def receive_status(payload: StatusPayload, x_api_key: str = Header(default=None)):
    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")

    return save_status(payload)