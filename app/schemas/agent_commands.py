from typing import Optional

from pydantic import BaseModel


class ServiceCommandCreate(BaseModel):
    service_name: str
    action: str


class ServiceCommandReport(BaseModel):
    store_code: str
    command_id: int
    status: str
    message: Optional[str] = ""
